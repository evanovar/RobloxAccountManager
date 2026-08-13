"""
utils/ui.py
The v2.5.0 rewrite is finally complete.
"""

from __future__ import annotations

import collections
import ctypes
from ctypes import wintypes
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser

from utils.app_paths import get_app_dir, get_data_dir, get_resource_path
from utils.version import APP_VERSION

_ROOT_DIR = get_app_dir()
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import psutil
import requests

from PySide6.QtCore import (
    QEvent, QObject, QPoint, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QAction, QColor, QCursor, QFont, QIcon, QPainter, QPainterPath,
    QKeySequence, QPalette, QPixmap, QPolygon, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox,
    QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QStackedWidget, QSystemTrayIcon,
    QTabWidget, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QToolButton, QVBoxLayout, QWidget,
)

from classes import RobloxAccountManager
from classes.encryption import EncryptionConfig, PasswordEncryption
from classes.operation_result import OperationResult, ensure_result
from classes.roblox_api import RobloxAPI

import features.account_actions as actions
import features.account_creator as account_creator_mod
import features.auto_rejoin as ar
import features.avatars as avatars
import features.cookie_validator as cookie_validator_mod
import features.chromium as chromium_mod
import features.diagnostics as diagnostics
import features.favorites as favorites_mod
import features.groups as groups
import features.headless_manager as headless_manager_mod
import features.presence as presence_mod
import features.roblox_downloader as roblox_downloader_mod
import features.roblox_settings as roblox_settings_mod
import features.updater as updater_mod
import features.webhook as webhook
import features.websocket_server as ws_mod
import features.window_grid as window_grid_mod
import features.window_renamer as window_renamer_mod
import features.windows_startup as windows_startup_mod


class _DragDropFilter(QObject):
    reorder_requested = Signal(int, int) # (from_row, insert_before_row)
    HOLD_MS = 800 # hold duration before drag starts (ms)
    CANCEL_PX = 8 # pixel slop before hold is cancelled

    def __init__(self, list_widget: "QListWidget", get_avatar=None, parent=None):
        super().__init__(parent)
        self._list = list_widget
        self._get_avatar = get_avatar # Callable[[str], QPixmap|None] | None

        self._press_pos = QPoint()
        self._press_row = -1
        self._username = ""

        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold_confirmed)

        self._dragging = False
        self._drag_row = -1
        self._drop_row = -1 # insert-before index (0 = top)

        self._float_win: QFrame | None = None # floating window with username + avatar
        self._viewport = list_widget.viewport() # avoid calling viewport() on a deleted C++ object at teardown

        self._indicator = QFrame(self._viewport)
        self._indicator.setFixedHeight(2)
        self._indicator.setStyleSheet("background: #0078D7; border: none;")
        self._indicator.hide()

    def eventFilter(self, obj, event):
        if obj is not self._viewport:
            return False
        t = event.type()
        if t == QEvent.Type.MouseButtonPress:
            return self._on_press(event)
        if t == QEvent.Type.MouseMove:
            return self._on_move(event)
        if t == QEvent.Type.MouseButtonRelease:
            return self._on_release(event)
        return False

    def _on_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        local_pos = event.position().toPoint()
        item = self._list.itemAt(local_pos)
        if item is None:
            return False
        username = item.data(Qt.ItemDataRole.UserRole)
        if not username:
            return False
        self._press_pos = event.globalPosition().toPoint()
        self._press_row = self._list.row(item)
        self._username = username
        self._hold_timer.start(self.HOLD_MS)
        return False

    def _on_hold_confirmed(self):
        self._dragging = True
        self._drag_row = self._press_row
        self._drop_row = self._press_row

        cursor_pos = QCursor.pos()
        self._create_float(self._username, cursor_pos)

        if self._get_avatar:
            pix = self._get_avatar(self._username)
            if pix and not pix.isNull():
                self.update_float_avatar(pix)

        self._list.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _on_move(self, event) -> bool:
        gpos = event.globalPosition().toPoint()

        if not self._dragging:
            if self._hold_timer.isActive() and not self._press_pos.isNull():
                if (gpos - self._press_pos).manhattanLength() > self.CANCEL_PX:
                    self._hold_timer.stop()
            return False

        if self._float_win: # Move floating window
            self._float_win.move(gpos.x() + 4, gpos.y() + 4)

        self._drop_row = self._compute_drop_row(event.position().toPoint()) # compute drop-before row from local pos
        self._show_indicator(self._drop_row)
        return True # consume during drag

    def _on_release(self, event) -> bool:
        self._hold_timer.stop()

        if not self._dragging:
            return False

        self._dragging = False
        self._list.unsetCursor()

        if self._float_win:
            self._float_win.hide()
        self._indicator.hide()

        from_row = self._drag_row
        to_row = self._drop_row

        self._drag_row = -1
        self._drop_row = -1

        if to_row >= 0 and from_row >= 0 and from_row != to_row:
            self.reorder_requested.emit(from_row, to_row)

        return True

    def _create_float(self, username: str, initial_pos: "QPoint | None" = None):
        if self._float_win:
            self._float_win.hide()
            self._float_win.deleteLater()

        win = QFrame(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        win.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        win.setStyleSheet("""
            QFrame {
                background: #1E1E1E;
                border: 1px solid #3A3A3A;
                border-radius: 6px;
            }
            QLabel { background: transparent; color: #EDEDED; }
        """)

        h = QHBoxLayout(win)
        h.setContentsMargins(8, 6, 12, 6)
        h.setSpacing(8)

        # Avatar slot
        av_lbl = QLabel()
        av_lbl.setFixedSize(22, 22)
        av_lbl.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        )
        av_lbl.setStyleSheet(
            "background: #2A2A2A; border-radius: 11px;"
        )
        h.addWidget(av_lbl)
        self._float_av = av_lbl

        name = QLabel(username)
        name.setStyleSheet("font-size: 12px; font-weight: 600;")
        h.addWidget(name)

        win.adjustSize()
        if initial_pos is not None:
            win.move(initial_pos.x() + 4, initial_pos.y() + 4)
        self._float_win = win
        win.show()

    def update_float_avatar(self, pixmap: "QPixmap"):
        if self._float_win and self._float_av:
            scaled = pixmap.scaled(
                22, 22,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._float_av.setPixmap(scaled)
            self._float_av.setStyleSheet("background: transparent;")


    def _compute_drop_row(self, local_pos) -> int:
        count = self._list.count()
        if count == 0:
            return 0

        for row in range(count):
            item = self._list.item(row)
            if item is None:
                continue
            rect = self._list.visualItemRect(item)
            mid = rect.top() + rect.height() // 2
            if local_pos.y() < mid:
                return row

        return count # below last item

    def _show_indicator(self, insert_before: int):
        count = self._list.count()
        if count == 0:
            self._indicator.hide()
            return

        if insert_before <= 0:
            rect = self._list.visualItemRect(self._list.item(0))
            y = rect.top()
        elif insert_before >= count:
            rect = self._list.visualItemRect(self._list.item(count - 1))
            y = rect.bottom()
        else:
            rect = self._list.visualItemRect(self._list.item(insert_before))
            y = rect.top()

        w = self._list.viewport().width()
        self._indicator.setGeometry(0, y - 1, w, 2)
        self._indicator.raise_()
        self._indicator.show()

    def abort(self):
        self._hold_timer.stop()
        self._dragging = False
        self._drag_row = -1
        self._drop_row = -1
        self._list.unsetCursor()
        if self._float_win:
            self._float_win.hide()
            self._float_win.deleteLater()
            self._float_win = None
        self._indicator.hide()

    def cleanup(self):
        self.abort()


class _ComboRightClickFilter(QObject):
    # Right-clicking a QComboBox popup normally closes it before a context
    # menu can show. Consuming the press here keeps the popup open underneath.
    right_clicked = Signal(QPoint)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(event.pos())
            return True
        return False


# Thread to Qt signal bridge
class _Bridge(QObject):
    account_added = Signal(object) # OperationResult from add-account worker
    account_creator_done = Signal(bool, str) # (success, summary) from account creator
    game_name_ready = Signal(str) # display text for current-place label
    launch_done = Signal(object) # OperationResult from any join/launch worker
    avatar_ready = Signal(str, object) # (username, image_bytes) from avatar worker
    rejoin_status = Signal(str, str) # (account, status_str) from rejoin worker
    afk_tooltip = Signal(str, int, int) # (message, x, y) pass None to hide
    mr_download_done = Signal(bool) # (success) from download_handle64 worker
    chromium_progress = Signal(int, str) # (percent 0-100, label text) from chromium download
    chromium_done = Signal(object) # OperationResult from Chromium download
    chromium_status = Signal(object) # OperationResult from latest build check
    roblox_download_progress = Signal(int, str) # (percent 0-100, current operation)
    roblox_download_done = Signal(bool, str, str) # (success, result_type, message)
    presence_update = Signal(object) # set[str] of online usernames
    cookie_validated = Signal(str, str) # (username, status) from validator worker
    update_available = Signal(str) # (latest_version) from update check worker
    update_progress = Signal(int) # (pct 0-100) from auto download worker
    update_done = Signal(bool, str) # (success, error_msg) from auto download worker
    join_place_resolved = Signal(object) # dict payload from Place ID resolution worker
    recent_game_saved = Signal() # a recent-game entry was written and needs a list refresh
    favorite_place_resolved = Signal(object) # dict payload from Save Current Game resolution
    headless_update = Signal(object) # list[dict] of running Roblox processes from Headless Manager scan
    headless_avatar_ready = Signal(int, object) # (pid, image_bytes) from Headless Manager avatar worker
    roblox_settings_loaded = Signal(object) # OperationResult from Roblox settings load
    roblox_settings_applied = Signal(object) # OperationResult from Roblox settings apply
    roblox_settings_auto_applied = Signal(object) # OperationResult from Roblox settings Auto Apply
    console_wakeup = Signal()


BG = "#0E0E0E"
PANEL = "#151515"
INPUT = "#1A1A1A"
TEXT = "#EDEDED"
MUTED = "#AAAAAA"
LINE = "#242424"
SELECT = "#2A2A2A"
NOTE = "#D6BB7D"
FG_ACCENT = "#0078D7"

_dropdown_arrow_cache: dict[str, str] = {}


def _dropdown_arrow_icon_path(color: str) -> str:
    cached = _dropdown_arrow_cache.get(color)
    if cached and os.path.exists(cached):
        return cached

    path = os.path.join(tempfile.gettempdir(), f"ram_dropdown_arrow_{color.strip('#')}.png")
    if not os.path.exists(path):
        pix = QPixmap(10, 10)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygon([QPoint(1, 3), QPoint(9, 3), QPoint(5, 8)]))
        painter.end()
        pix.save(path, "PNG")

    _dropdown_arrow_cache[color] = path
    return path

class _FloatingTooltip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._label = QLabel("", self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                background-color: {PANEL};
                border: 1px solid {LINE};
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._label)

        self._update_timer = QTimer(self)
        self._update_timer.setInterval(150)
        self._update_timer.timeout.connect(self._follow_cursor)

        self.hide()

    def show_message(self, message: str, x: int, y: int):
        if not message:
            self._update_timer.stop()
            super().hide()
            return
        self._label.setText(message)
        self.adjustSize()
        self._place_at(x, y)
        super().show()
        self._update_timer.start()

    def hide(self):
        self._update_timer.stop()
        super().hide()

    def _place_at(self, x: int, y: int):
        sx, sy = x + 20, y + 20
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            sx = min(sx, geo.right()  - self.width()  - 8)
            sy = min(sy, geo.bottom() - self.height() - 8)
            sx = max(sx, geo.left() + 8)
            sy = max(sy, geo.top()  + 8)
        self.move(sx, sy)

    def _follow_cursor(self):
        if not self.isVisible():
            self._update_timer.stop()
            return
        try:

            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            self._place_at(pt.x, pt.y)
        except Exception:
            pass

class _HotkeyCaptureButton(QPushButton):
    recording_started = Signal()
    recording_canceled = Signal()
    sequence_changed = Signal(str)

    _MODIFIER_KEYS = {
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
    }

    def __init__(self, sequence: str, parent=None):
        super().__init__(parent)
        self._sequence = sequence or window_grid_mod.DEFAULT_HOTKEY
        self._recording = False
        self._pending_sequence = ""
        self._pending_key = 0
        self.setText(self._sequence)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self._begin_recording)

    def set_sequence(self, sequence: str) -> None:
        self._sequence = sequence or window_grid_mod.DEFAULT_HOTKEY
        if not self._recording:
            self.setText(self._sequence)

    def _begin_recording(self) -> None:
        if self._recording:
            return
        self._recording = True
        self._pending_sequence = ""
        self._pending_key = 0
        self.setText("Recording...")
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.grabKeyboard()
        self.recording_started.emit()

    def _finish_recording(self) -> None:
        sequence = self._pending_sequence
        self._recording = False
        self._pending_sequence = ""
        self._pending_key = 0
        self.releaseKeyboard()
        self._sequence = sequence
        self.setText(sequence)
        self.sequence_changed.emit(sequence)

    def _cancel_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        self._pending_sequence = ""
        self._pending_key = 0
        self.releaseKeyboard()
        self.setText(self._sequence)
        self.recording_canceled.emit()

    def keyPressEvent(self, event) -> None:
        if not self._recording:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            event.accept()
            return

        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._cancel_recording()
            event.accept()
            return
        if key in self._MODIFIER_KEYS:
            event.accept()
            return

        sequence = QKeySequence(event.keyCombination()).toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if sequence:
            self._pending_sequence = sequence
            self._pending_key = key
            self.setText("Release to assign")
        event.accept()

    def keyReleaseEvent(self, event) -> None:
        if not self._recording:
            super().keyReleaseEvent(event)
            return
        if (
            self._pending_sequence
            and event.key() == self._pending_key
        ):
            self._finish_recording()
        event.accept()

    def focusOutEvent(self, event) -> None:
        if self._recording:
            self._cancel_recording()
        super().focusOutEvent(event)

class AccountManagerUIQt(QMainWindow): # Main Window
    def __init__(self, manager, icon_path: str | None = None):
        super().__init__()
        self.manager = manager
        self.manager.set_pre_launch_hook(
            roblox_settings_mod.apply_saved_customizations
        )
        self._last_operation_error = ("", 0.0)
        self._chromium_download_active = False
        self._roblox_settings_records: dict[str, dict] = {}
        self._roblox_settings_pending: dict[str, str] = {}
        self._roblox_settings_file_hash = ""
        self._roblox_settings_editor_active = False
        self._roblox_settings_loading = False
        self._roblox_settings_applying = False
        self._roblox_settings_show_load_error = False
        self._roblox_settings_config: dict[str, object] = {}
        self._roblox_settings_pending_config: dict[str, object] = {}
        self._roblox_settings_auto_applying = False
        self._roblox_settings_startup_reload = True
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        self._tray_exit_requested = False
        self._tray_restore_maximized = False
        self._shutdown_cleanup_done = False
        self._window_grid_hotkey_registered = False
        self._window_grid_hotkey_hwnd = 0
        self._diagnostics_heartbeat = QTimer(self)
        self._diagnostics_heartbeat.setInterval(5000)
        self._diagnostics_heartbeat.timeout.connect(diagnostics.pulse_ui)
        self._diagnostics_heartbeat.start()

        for candidate in [
            os.path.join(get_data_dir(), "icon.ico"),
            icon_path,
            get_resource_path("icon.ico"),
        ]:
            if candidate and os.path.exists(candidate):
                self._icon_path = candidate
                break
        else:
            self._icon_path = None

        self._drag_pos = QPoint()
        self._game_name_timer = QTimer(self)
        self._game_name_timer.setSingleShot(True)
        self._game_name_timer.timeout.connect(self._do_fetch_game_name)

        self._console_queue = (
            sys.stdout._console_queue
            if isinstance(sys.stdout, webhook.WebhookStdoutInterceptor)
            else collections.deque(maxlen=2000)
        )

        # Thread to Qt signal bridge
        self._bridge = _Bridge()
        self._bridge.account_added.connect(self._on_add_done_main)
        self._bridge.account_creator_done.connect(self._on_account_creator_done)
        self._bridge.launch_done.connect(self._on_launch_and_refresh)
        self._bridge.avatar_ready.connect(self._on_avatar_ready)
        self._bridge.rejoin_status.connect(self._on_rejoin_status)
        self._bridge.afk_tooltip.connect(self._on_afk_tooltip_signal)
        self._bridge.mr_download_done.connect(self._update_mr_h64_status)
        self._bridge.chromium_progress.connect(self._on_chromium_progress)
        self._bridge.chromium_done.connect(self._on_chromium_done)
        self._bridge.chromium_status.connect(self._on_chromium_status)
        self._bridge.roblox_download_progress.connect(self._on_roblox_download_progress)
        self._bridge.roblox_download_done.connect(self._on_roblox_download_done)
        self._bridge.presence_update.connect(self._on_presence_update)
        self._bridge.cookie_validated.connect(self._on_cookie_validated)
        self._bridge.console_wakeup.connect(self._drain_console_queue)
        if isinstance(sys.stdout, webhook.WebhookStdoutInterceptor):
            sys.stdout.set_console_wakeup(self._bridge.console_wakeup.emit)
        self._bridge.update_available.connect(self._on_update_available)
        self._bridge.join_place_resolved.connect(self._on_join_place_resolved)
        self._bridge.recent_game_saved.connect(self._refresh_recent_games)
        self._bridge.favorite_place_resolved.connect(self._on_favorite_place_resolved)
        self._bridge.headless_update.connect(self._on_headless_update)
        self._bridge.headless_avatar_ready.connect(self._on_headless_avatar_ready)
        self._bridge.roblox_settings_loaded.connect(self._on_roblox_settings_loaded)
        self._bridge.roblox_settings_applied.connect(self._on_roblox_settings_applied)
        self._bridge.roblox_settings_auto_applied.connect(
            self._on_roblox_settings_auto_applied
        )

        # Account Activity Monitor
        self._presence_mod = presence_mod
        self._presence_scanner = None
        self._presence_dots: dict[str, QLabel] = {}
        self._online_usernames: set[str] = set()
        self._activity_snapshot: dict[str, dict] = {}
        self._activity_widgets: dict[str, QWidget] = {}
        self._activity_labels: dict[str, tuple[QLabel, QLabel]] = {}

        # Roblox Window Renamer
        self._window_renamer: window_renamer_mod.RobloxWindowRenamer | None = None

        # Cookie Validator
        self._cv_mod = cookie_validator_mod
        self._cv_validator = None
        self._invalid_badges: dict[str, QLabel] = {}
        self._account_avatar_containers: dict[str, QWidget] = {}
        self._account_name_labels: dict[str, QLabel] = {}
        self._account_rows: dict[str, QWidget] = {}
        self._placeholder_pixmaps: dict[int, QPixmap] = {}

        self._avatar_labels: dict[str, QLabel] = {}
        self._current_group: str | None = None
        self._group_bar_lay: QHBoxLayout | None = None

        self._ar_configs: dict = ar.load_configs() # {username: config_dict}
        self._ar_workers: dict[str, ar.AutoRejoinWorker] = {} # {username: worker}
        self._ar_list: QListWidget | None = None
        self._headless_manager: headless_manager_mod.HeadlessManager | None = None
        self._headless_latest_rows: list[dict] = []
        self._headless_avatar_labels: dict[int, QLabel] = {}
        self._headless_status_labels: dict[int, QLabel] = {}

        # WebSocket server
        self._ws_server: ws_mod.WebSocketServer | None = ws_mod.WebSocketServer(
            manager=self.manager,
            ar_workers=self._ar_workers,
            ar_configs=self._ar_configs,
            get_settings=actions.load_ui_settings,
            refresh_ui_callback=lambda: self._bridge.account_added.emit(
                OperationResult.success()
            ),
        )

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle("Evanovar's Roblox Account Manager")
        self.setFixedSize(640, 520)
        if self._icon_path:
            try:
                self.setWindowIcon(QIcon(self._icon_path))
            except Exception:
                pass

        self._apply_stylesheet()
        self._build_ui()
        self._setup_system_tray()

        _data_folder = get_data_dir()
        _enc_cfg = EncryptionConfig(os.path.join(_data_folder, "encryption_config.json"))
        self._setup_needed = not _enc_cfg.is_setup_complete()
        if self._setup_needed:
            for b in self._normal_nav_btns:
                b.hide()
            self._setup_nav_btn.show()
            self._setup_nav_btn.setChecked(True)
            self._page_stack.setCurrentIndex(7)

        self._bridge.game_name_ready.connect(self._game_name_label.setText)

        self._refresh_account_list()
        self._refresh_recent_games()
        self._update_encryption_badge()
        # Apply persisted settings that affect widgets built in _build_ui
        S = actions.load_ui_settings()
        discord_settings = S.get("discord_webhook", {})
        if (
            discord_settings.get("enabled", False)
            and discord_settings.get("screenshot_enabled", False)
        ):
            webhook.start_screenshot_loop(
                lambda: actions.get_ui_setting("discord_webhook", {})
            )
        self._place_id_edit.setCurrentText(S.get("last_place_id", ""))
        self._private_server_edit.setText(S.get("last_private_server", ""))

        if S.get("last_place_id"):
            self._schedule_game_name_fetch()
            
        if S.get("enable_multi_select", False):
            self._account_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        if S.get("always_on_top", False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.show()

        if S.get("optimize_roblox_ram", False):
            self._start_ram_boost()

        if S.get("rename_roblox_windows", False):
            self._start_rename_windows()

        if S.get("presence_indicator", False):
            self._start_presence_scanner()

        if S.get("roblox_installer_fix", False):
            try:
                RobloxAPI.quarantine_installers()
            except Exception as e:
                print(f"[ERROR] Failed to quarantine installers: {e}")

        if S.get("websocket_enabled") and S.get("developer_mode"):
            self._ws_server.start()

        if S.get("headless_manager_enabled", False):
            self._start_headless_manager()

        if S.get("window_grid_enabled", False):
            QTimer.singleShot(
                0,
                lambda: self._apply_window_grid_hotkey(show_error=False),
            )

        if roblox_settings_mod.has_startup_customizations():
            QTimer.singleShot(0, self._start_roblox_auto_apply)

        QTimer.singleShot(2500, self._start_cookie_validator)
        QTimer.singleShot(500, self._start_update_check)
        if S.get("browser_type", "chrome") == "chromium":
            QTimer.singleShot(1500, self._start_chromium_status_check)
        print("[INFO] UI ready")

    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {BG}; }}
            QWidget {{ color: {TEXT}; font-family: 'Segoe UI'; }}

            QFrame#navPanel, QFrame#rightPanel {{ background: {PANEL}; border: 0; }}
            QFrame#centerPanel {{ background: {BG};    border: 0; }}
            QFrame#titleBar {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}

            QLabel#sectionTitle {{ font-size: 13px; font-weight: 700; }}
            QLabel#titleText {{ font-size: 12px; font-weight: 700; color: {TEXT}; }}

            QPushButton#titleButton {{
                background: transparent; border: 0;
                min-height: 24px; min-width: 30px; padding: 0;
                text-align: center; color: {MUTED}; font-size: 12px;
            }}
            QPushButton#titleButton:hover {{ background: {SELECT}; color: {TEXT}; }}

            QPushButton#closeButton {{
                background: transparent; border: 0;
                min-height: 24px; min-width: 30px; padding: 0;
                text-align: center; color: {MUTED}; font-size: 12px;
            }}
            QPushButton#closeButton:hover {{ background: #5A2A2A; color: #FFFFFF; }}

            QPushButton#navTab {{
                background: transparent; border: 1px solid transparent;
                border-radius: 0; text-align: left; min-height: 28px;
                padding: 2px 8px; color: {MUTED}; font-size: 12px;
            }}
            QPushButton#navTab:checked {{
                background: #2E2E2E; border: 1px solid #3A3A3A;
                color: {TEXT}; font-weight: 700;
            }}

            QListWidget {{
                background: {INPUT}; border: 1px solid {LINE};
                outline: none; padding: 2px; font-size: 11px;
            }}
            QListWidget::item {{ height: 22px; padding-left: 6px; }}
            QListWidget::item:selected {{ background: {SELECT}; color: {TEXT}; }}

            QLabel#accountName {{ color: {TEXT};  font-size: 11px; }}
            QLabel#noteSep {{ color: #7A7A7A; font-size: 11px; }}
            QLabel#noteText {{ color: {NOTE};  font-size: 11px; font-weight: 600; }}
            QLabel#performanceSep {{ color: #7A7A7A; font-size: 11px; }}
            QLabel#ramUsage {{ color: #5DBBFF; font-size: 10px; }}
            QLabel#cpuUsage {{ color: #2ECC71; font-size: 10px; }}

            QLineEdit {{
                background: {INPUT}; border: 1px solid {LINE};
                padding: 4px 6px; min-height: 24px; color: {TEXT};
            }}

            QPushButton {{
                background: {INPUT}; border: 1px solid {LINE};
                min-height: 26px; padding: 2px 8px;
                text-align: left; font-size: 11px; color: {TEXT};
            }}
            QPushButton:hover {{ background: {SELECT}; }}
            QPushButton:pressed {{ background: {SELECT}; }}

            QToolButton#splitArrow {{
                background: {INPUT}; border: 1px solid {LINE};
                min-width: 26px; max-width: 26px; min-height: 26px;
                padding: 0; color: {TEXT};
            }}
            QToolButton#splitArrow:hover {{ background: {SELECT}; }}
            QToolButton#splitArrow:pressed {{ background: {SELECT}; }}
            QToolButton#splitArrow::menu-indicator {{ image: none; }}

            QMenu {{
                background: {PANEL}; border: 1px solid {LINE};
                color: {TEXT}; font-size: 11px;
                border-radius: 0px;
                padding: 2px 0px;
            }}
            QMenu::item {{
                padding: 4px 20px 4px 12px;
                border-radius: 0px;
            }}
            QMenu::item:selected {{ background: {SELECT}; border-radius: 0px; }}
            QMenu::separator {{ height: 1px; background: {LINE}; margin: 2px 0px; }}

            QScrollArea#groupScroll {{
                background: transparent; border: 0;
                max-height: 30px;
            }}
            QScrollArea#groupScroll > QWidget > QWidget {{
                background: transparent;
            }}
            QPushButton#groupTab {{
                background: transparent; border: 1px solid transparent;
                border-radius: 3px; min-height: 20px; max-height: 20px;
                padding: 0px 8px; font-size: 10px; color: {MUTED};
            }}
            QPushButton#groupTab:checked {{
                background: #2E2E2E; border: 1px solid #3A3A3A; color: {TEXT};
            }}
            QPushButton#groupTab:hover {{ background: #232323; border-color: #333333; }}

            QDialog {{ background: {BG}; }}
            QTextEdit {{ background: {INPUT}; border: 1px solid {LINE}; color: {TEXT}; font-size: 11px; }}

            QCheckBox {{ color: {TEXT}; font-size: 11px; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 13px; height: 13px;
                border: 1px solid {LINE}; background: {INPUT};
            }}
            QCheckBox::indicator:checked {{
                background: #3A7BD5; border: 1px solid #3A7BD5;
                image: url(none);
            }}
            QCheckBox::indicator:disabled {{
                background: {SELECT}; border: 1px solid {LINE};
                opacity: 0.5;
            }}
            QCheckBox:disabled {{ color: {MUTED}; }}

            QRadioButton {{ color: {TEXT}; font-size: 11px; spacing: 6px; }}
            QRadioButton::indicator {{
                width: 13px; height: 13px; border-radius: 7px;
                border: 1px solid {LINE}; background: {INPUT};
            }}
            QRadioButton::indicator:checked {{
                background: #3A7BD5; border: 2px solid {INPUT};
                outline: 1px solid #3A7BD5;
            }}
            QRadioButton:disabled {{ color: {MUTED}; }}

            QGroupBox {{
                border: 1px solid {LINE}; border-radius: 3px;
                margin-top: 10px; padding-top: 4px;
                font-size: 10px; font-weight: 700; color: {MUTED};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px 0 6px; left: 8px;
            }}
        """)

    def _build_ui(self): # build the main window UI structure
        central = QWidget(self)
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_title_bar())

        self._page_stack = QStackedWidget()
        self._built_pages = {0, 1, 2, 3, 7}
        self._lazy_page_builders = {
            4: self._build_settings_panel,
            5: self._build_console_panel,
            6: self._build_donations_panel,
        }

        _accounts_page = QWidget()
        _acc_lay = QHBoxLayout(_accounts_page)
        _acc_lay.setContentsMargins(0, 0, 0, 0)
        _acc_lay.setSpacing(0)
        _acc_lay.addWidget(self._build_center_panel(), 1)
        _acc_lay.addWidget(self._build_right_panel())

        self._page_stack.addWidget(_accounts_page) # idx 0
        self._page_stack.addWidget(self._build_auto_rejoin_panel()) # idx 1
        self._page_stack.addWidget(self._build_anti_afk_panel()) # idx 2
        self._page_stack.addWidget(self._build_multi_roblox_panel()) # idx 3
        self._page_stack.addWidget(QWidget()) # idx 4, built on first use
        self._page_stack.addWidget(QWidget()) # idx 5, built on first use
        self._page_stack.addWidget(QWidget()) # idx 6, built on first use
        self._page_stack.addWidget(self._build_setup_panel()) # idx 7

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_nav_panel())
        body.addWidget(self._page_stack, 1)
        outer.addLayout(body, 1)

    def _show_page(self, index: int) -> None:
        if index not in self._built_pages:
            builder = self._lazy_page_builders.get(index)
            if builder is not None:
                placeholder = self._page_stack.widget(index)
                page = builder()
                self._page_stack.removeWidget(placeholder)
                placeholder.deleteLater()
                self._page_stack.insertWidget(index, page)
                self._built_pages.add(index)
                if index == 4:
                    if hasattr(self, "_headless_list"):
                        self._refresh_headless_list(self._headless_latest_rows)
                    self._start_chromium_status_check()
                elif index == 5:
                    self._drain_console_queue()
        self._page_stack.setCurrentIndex(index)

    # Title bar
    def _build_title_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(32)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 0, 0)
        lay.setSpacing(0)

        if self._icon_path:
            pix = QPixmap(self._icon_path)
            if not pix.isNull():
                pm = pix.scaled(16, 16,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
                ico_lbl = QLabel()
                ico_lbl.setPixmap(pm)
                ico_lbl.setContentsMargins(0, 6, 8, 6)
                lay.addWidget(ico_lbl)

        title = QLabel("Evanovar's Roblox Account Manager")
        title.setObjectName("titleText")
        lay.addWidget(title)
        lay.addStretch(1)

        min_btn = QPushButton("-")
        min_btn.setObjectName("titleButton")
        min_btn.clicked.connect(self.showMinimized)
        lay.addWidget(min_btn)

        close_btn = QPushButton("x")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.close)
        lay.addWidget(close_btn)

        return bar

    # Drag window
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 32:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()
        super().mouseReleaseEvent(event)

    # Left nav panel
    def _build_nav_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("navPanel")
        panel.setFixedWidth(122)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(10)

        _NAV_PAGES = {
            "Accounts":    0,
            "Auto-Rejoin": 1,
            "Anti AFK":    2,
            "Multi Roblox":3,
            "Settings":    4,
            "Console":     5,
            "Donations":   6,
        }

        self._normal_nav_btns: list[QPushButton] = []

        for label, checked in [
            ("Accounts", True),
            ("Auto-Rejoin", False),
            ("Anti AFK", False),
            ("Multi Roblox", False),
            ("Settings", False),
            ("Console", False),
            ("Donations", False),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("navTab")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setChecked(checked)
            if label in _NAV_PAGES:
                page_idx = _NAV_PAGES[label]
                btn.clicked.connect(
                    lambda _=False, idx=page_idx: self._show_page(idx)
                )
            lay.addWidget(btn)
            self._normal_nav_btns.append(btn)

        # Setup nav button
        self._setup_nav_btn = QPushButton("Setup")
        self._setup_nav_btn.setObjectName("navTab")
        self._setup_nav_btn.setCheckable(True)
        self._setup_nav_btn.setAutoExclusive(True)
        self._setup_nav_btn.setChecked(False)
        self._setup_nav_btn.clicked.connect(
            lambda: self._page_stack.setCurrentIndex(7)
        )
        self._setup_nav_btn.hide() # shown when setup needed (hidden by default)
        lay.addWidget(self._setup_nav_btn)

        lay.addStretch(1)

        ver_lbl = QLabel(f"Version : {APP_VERSION}")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        ver_lbl.setStyleSheet(
            f"color: {MUTED}; font-size: 9px; background: transparent;"
        )
        lay.addWidget(ver_lbl)
        return panel

    def _build_setup_panel(self) -> QWidget: # Encryption setup panel
        panel = QWidget()
        panel.setObjectName("centerPanel")
        root = QVBoxLayout(panel)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(14)

        hdr = QLabel("Choose your encryption method")
        hdr.setStyleSheet("font-size: 14px; font-weight: 700;")
        sub = QLabel(
            "Your account cookies will be stored locally. "
            "Choose how they are protected."
        )
        sub.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        sub.setWordWrap(True)
        root.addWidget(hdr)
        root.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {LINE};")
        root.addWidget(sep)

        self._setup_stack = QStackedWidget()
        root.addWidget(self._setup_stack, 1)

        choice_w = QWidget()
        choice_lay = QVBoxLayout(choice_w)
        choice_lay.setContentsMargins(0, 0, 0, 0)
        choice_lay.setSpacing(10)

        _btn_style = (
            f"QPushButton {{ background: {INPUT}; color: {TEXT};"
            f"  border: 1px solid {LINE}; border-radius: 0;"
            f"  padding: 10px 16px; font-size: 12px; text-align: left; }}"
            f"QPushButton:hover {{ background: {SELECT}; border-color: #3A3A3A; }}"
            f"QPushButton:checked {{ background: #0A1A2A; border-color: #0078D7; color: {TEXT}; }}"
        )

        btn_group = QButtonGroup(self)
        btn_group.setExclusive(True)

        self._setup_hw_btn = QPushButton(
            "Hardware Encryption\n"
            "   Tied to this PC. No password needed. Not portable."
        )
        self._setup_hw_btn.setCheckable(True)
        self._setup_hw_btn.setStyleSheet(_btn_style)

        self._setup_pw_btn = QPushButton(
            "Password Encryption\n"
            "   Portable across PCs. No recovery if password is lost."
        )
        self._setup_pw_btn.setCheckable(True)
        self._setup_pw_btn.setChecked(True)
        self._setup_pw_btn.setStyleSheet(_btn_style)

        self._setup_none_btn = QPushButton(
            "No Encryption\n"
            "   Cookies stored in plain text. Not secure."
        )
        self._setup_none_btn.setCheckable(True)
        self._setup_none_btn.setStyleSheet(_btn_style)

        for b in (self._setup_hw_btn, self._setup_pw_btn, self._setup_none_btn):
            btn_group.addButton(b)
            choice_lay.addWidget(b)

        choice_lay.addStretch()

        cont_row = QHBoxLayout()
        cont_row.addStretch()
        self._setup_continue_btn = QPushButton("Continue")
        self._setup_continue_btn.setStyleSheet(
            f"QPushButton {{ background: {SELECT}; border: 1px solid {LINE};"
            f"  min-height: 30px; min-width: 120px; font-weight: 700;"
            f"  text-align: center; color: {TEXT}; border-radius: 0; }}"
            f"QPushButton:hover   {{ background: #3A3A3A; }}"
            f"QPushButton:pressed {{ background: #1E1E1E; }}"
        )
        cont_row.addWidget(self._setup_continue_btn)
        choice_lay.addLayout(cont_row)

        self._setup_stack.addWidget(choice_w) # idx 0

        pw_w = QWidget()
        pw_lay = QVBoxLayout(pw_w)
        pw_lay.setContentsMargins(0, 0, 0, 0)
        pw_lay.setSpacing(10)

        warn = QLabel(
            "IMPORTANT: There is NO password recovery.\n"
            "A lost password means permanent data loss."
        )
        warn.setStyleSheet(f"color: {NOTE}; font-size: 11px;")
        pw_lay.addWidget(warn)

        pw_lay.addWidget(QLabel("Enter your password (min. 8 characters):"))
        self._setup_pw_entry1 = QLineEdit()
        self._setup_pw_entry1.setEchoMode(QLineEdit.EchoMode.Password)
        self._setup_pw_entry1.setPlaceholderText("Password")
        pw_lay.addWidget(self._setup_pw_entry1)

        pw_lay.addWidget(QLabel("Confirm password:"))
        self._setup_pw_entry2 = QLineEdit()
        self._setup_pw_entry2.setEchoMode(QLineEdit.EchoMode.Password)
        self._setup_pw_entry2.setPlaceholderText("Confirm password")
        pw_lay.addWidget(self._setup_pw_entry2)

        self._setup_pw_err = QLabel("")
        self._setup_pw_err.setStyleSheet("color: #C0392B; font-size: 11px;")
        pw_lay.addWidget(self._setup_pw_err)

        pw_lay.addStretch()

        pw_btn_row = QHBoxLayout()
        pw_btn_row.setSpacing(8)
        pw_back = QPushButton("Back")
        self._setup_pw_confirm_btn = QPushButton("Confirm")
        self._setup_pw_confirm_btn.setStyleSheet(
            f"QPushButton {{ background: {SELECT}; border: 1px solid {LINE};"
            f"  min-height: 30px; min-width: 120px; font-weight: 700;"
            f"  text-align: center; color: {TEXT}; border-radius: 0; }}"
            f"QPushButton:hover   {{ background: #3A3A3A; }}"
            f"QPushButton:pressed {{ background: #1E1E1E; }}"
        )
        pw_btn_row.addWidget(pw_back)
        pw_btn_row.addStretch()
        pw_btn_row.addWidget(self._setup_pw_confirm_btn)
        pw_lay.addLayout(pw_btn_row)

        self._setup_stack.addWidget(pw_w)       # idx 1

        def _on_continue():
            if self._setup_hw_btn.isChecked():
                _do_hardware()
            elif self._setup_none_btn.isChecked():
                _do_none()
            else:
                self._setup_pw_entry1.clear()
                self._setup_pw_entry2.clear()
                self._setup_pw_err.setText("")
                self._setup_stack.setCurrentIndex(1)

        def _do_hardware():
            data_folder = get_data_dir()
            enc = EncryptionConfig(os.path.join(data_folder, "encryption_config.json"))
            enc.enable_hardware_encryption()
            _show_info(self, "Hardware Encryption Enabled",
                       "Hardware-based encryption is now active.\n"
                       "Your accounts will be encrypted automatically.")
            self._on_setup_complete()

        def _do_none():
            res = QMessageBox.warning(
                self, "No Encryption",
                "Your account data will be stored in plain text.\n"
                "Anyone with access to your files can read your cookies.\n\n"
                "Are you sure you want to continue without encryption?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                data_folder = get_data_dir()
                enc = EncryptionConfig(os.path.join(data_folder, "encryption_config.json"))
                enc.disable_encryption()
                self._on_setup_complete()

        def _on_confirm_pw():
            pw1 = self._setup_pw_entry1.text()
            pw2 = self._setup_pw_entry2.text()
            if len(pw1) < 8:
                self._setup_pw_err.setText("Password must be at least 8 characters.")
                return
            if pw1 != pw2:
                self._setup_pw_err.setText("Passwords do not match.")
                return
            data_folder = get_data_dir()
            enc = EncryptionConfig(os.path.join(data_folder, "encryption_config.json"))
            temp = PasswordEncryption(pw1)
            enc.enable_password_encryption(
                temp.get_salt_b64(),
                hashlib.sha256(pw1.encode()).hexdigest(),
            )
            _show_info(self, "Password Encryption Enabled",
                       "Password encryption is now active.\n"
                       "Keep your password safe, there is no recovery method.")
            self._on_setup_complete()

        self._setup_continue_btn.clicked.connect(_on_continue)
        pw_back.clicked.connect(lambda: self._setup_stack.setCurrentIndex(0))
        self._setup_pw_confirm_btn.clicked.connect(_on_confirm_pw)

        return panel

    def _on_setup_complete(self):
        self._setup_nav_btn.hide()
        for b in self._normal_nav_btns:
            b.show()
        self._normal_nav_btns[0].setChecked(True) # Accounts
        self._page_stack.setCurrentIndex(0)
        self._setup_needed = False

    def _build_center_panel(self) -> QFrame: # Main account list
        panel = QFrame()
        panel.setObjectName("centerPanel")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(0)

        section_title = QLabel("Account List")
        section_title.setObjectName("sectionTitle")
        header_row.addWidget(section_title)

        header_row.addStretch(1)

        # encryption label
        self._enc_label = QLabel()
        self._enc_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        header_row.addWidget(self._enc_label)

        lay.addLayout(header_row)

        # group section
        self._group_scroll = QScrollArea()
        self._group_scroll.setObjectName("groupScroll")
        self._group_scroll.setWidgetResizable(True)
        self._group_scroll.setFixedHeight(28)
        self._group_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._group_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        _group_bar_widget = QWidget()
        _group_bar_widget.setStyleSheet("background: transparent;")
        self._group_bar_lay = QHBoxLayout(_group_bar_widget)
        self._group_bar_lay.setContentsMargins(0, 0, 0, 0)
        self._group_bar_lay.setSpacing(4)
        self._group_scroll.setWidget(_group_bar_widget)
        lay.addWidget(self._group_scroll)

        # account list widget
        self._account_list = QListWidget()
        self._account_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._account_list.customContextMenuRequested.connect(self._on_account_context_menu)

        self._drag_filter = _DragDropFilter(
            self._account_list,
            get_avatar=lambda u: self._avatar_labels[u].pixmap() if u in self._avatar_labels else None,
            parent=self,
        )
        self._account_list.viewport().installEventFilter(self._drag_filter)
        self._drag_filter.reorder_requested.connect(self._on_account_reorder)

        lay.addWidget(self._account_list, 1)

       # Add and Remove buttons row
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        # Add account button
        self._add_btn = QToolButton()
        self._add_btn.setText("Add Account")
        self._add_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._add_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._add_btn.setFixedHeight(26)
        self._add_btn.setStyleSheet(
            f"QToolButton {{"
            f"  background: {INPUT}; border: 1px solid {LINE}; font-size: 11px;"
            f"  min-height: 26px; padding: 2px 28px 2px 8px; text-align: center; color: {TEXT};"
            f"}}"
            f"QToolButton:hover {{ background: {SELECT}; }}"
            f"QToolButton:pressed {{ background: {SELECT}; }}"
            f"QToolButton::menu-button {{ width: 24px; border-left: 1px solid {LINE}; }}"
            f"QToolButton::menu-arrow {{ width: 9px; height: 9px; }}"
        )

        # Dropdown menu for add button
        add_menu = QMenu(self._add_btn)
        act_cookie = add_menu.addAction("Import Cookie")
        act_userpass = add_menu.addAction("Import User:Pass")
        act_creator = add_menu.addAction("Account Creator")
        act_js = add_menu.addAction("Javascript")
        act_cookie.triggered.connect(self._on_import_cookie)
        act_userpass.triggered.connect(self._on_import_userpass)
        act_creator.triggered.connect(self._on_account_creator)
        act_js.triggered.connect(self._on_add_javascript)
        self._add_btn.setMenu(add_menu)
        self._add_btn.clicked.connect(self._on_add_account_browser)

        # Remove Button
        remove_btn = QPushButton("Remove")
        remove_btn.setFixedWidth(86)
        remove_btn.setFixedHeight(26)
        remove_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        remove_btn.setStyleSheet(
            f"QPushButton {{ background: {INPUT}; border: 1px solid {LINE};"
            f"  font-size: 11px; min-height: 26px; padding: 2px 8px;"
            f"  text-align: center; color: {TEXT}; }}"
            f"QPushButton:hover   {{ background: {SELECT}; }}"
            f"QPushButton:pressed {{ background: {SELECT}; }}"
        )
        remove_btn.clicked.connect(self._on_remove_account)

        bottom.addWidget(self._add_btn, 1)
        bottom.addWidget(remove_btn)
        bottom.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(bottom)

        return panel

    def _build_auto_rejoin_panel(self) -> QFrame: # Auto Rejoin
        panel = QFrame()
        panel.setObjectName("centerPanel")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        ttl = QLabel("Auto-Rejoin")
        ttl.setObjectName("sectionTitle")
        hdr.addWidget(ttl)
        hdr.addStretch(1)
        hint = QLabel("Right-click for actions")
        hint.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        hdr.addWidget(hint)
        lay.addLayout(hdr)

        # Account list for auto rejoin
        self._ar_list = QListWidget()
        self._ar_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._ar_list.customContextMenuRequested.connect(self._ar_on_context_menu)
        lay.addWidget(self._ar_list, 1)
        QTimer.singleShot(0, self._ar_refresh_list) # defer

        bottom = QHBoxLayout() # Add / Start All / Stop All buttons
        bottom.setSpacing(6)
        _BTN_SS = f"QPushButton {{ text-align: center; color: {TEXT}; }}"
        add_btn = QPushButton("Add Account")
        add_btn.setStyleSheet(_BTN_SS)
        add_btn.clicked.connect(self._ar_on_add)
        start_all_btn = QPushButton("Start All")
        start_all_btn.setStyleSheet(_BTN_SS)
        start_all_btn.clicked.connect(self._ar_on_start_all)
        stop_all_btn = QPushButton("Stop All")
        stop_all_btn.setStyleSheet(_BTN_SS)
        stop_all_btn.clicked.connect(self._ar_on_stop_all)
        bottom.addWidget(add_btn, 1)
        bottom.addWidget(start_all_btn)
        bottom.addWidget(stop_all_btn)
        lay.addLayout(bottom)
        return panel

    def _build_anti_afk_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("centerPanel")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        ttl = QLabel("Anti-AFK")
        ttl.setObjectName("sectionTitle")
        hdr.addWidget(ttl)
        hdr.addStretch(1)
        self._afk_status_lbl = QLabel("Status: Stopped")
        self._afk_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        hdr.addWidget(self._afk_status_lbl)
        lay.addLayout(hdr)

        desc = QLabel(
            "Automatically sends key presses to all Roblox windows at set intervals to prevent AFK kicks."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        lay.addWidget(desc)

        # Enable checkbox
        self._afk_enabled_chk = QCheckBox("Enable Anti-AFK")
        self._afk_enabled_chk.setStyleSheet(f"QCheckBox {{ color: {TEXT}; font-size: 12px; font-weight: 700; }}")
        self._afk_enabled_chk.stateChanged.connect(self._on_afk_enabled_changed)
        lay.addWidget(self._afk_enabled_chk)

        # Settings form
        form = QVBoxLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(10)

        # Action Key row
        row_key = QHBoxLayout()
        row_key.setSpacing(8)
        lbl_key = QLabel("Action Key:")
        lbl_key.setStyleSheet(f"color: {MUTED}; font-size: 11px; min-width: 80px;")
        row_key.addWidget(lbl_key)
        
        self._afk_key_btn = QPushButton("W")
        self._afk_key_btn.setFixedWidth(100)
        self._afk_key_btn.setFixedHeight(24)
        self._afk_key_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._afk_key_btn.setStyleSheet(
            f"QPushButton {{ background: {INPUT}; border: 1px solid {LINE};"
            f" color: {TEXT}; font-size: 11px; font-weight: 700; min-height: 24px; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {SELECT}; }}"
            f"QPushButton:focus {{ border: 1px solid {FG_ACCENT}; }}"
        )
        self._afk_key_btn.clicked.connect(self._on_afk_record_key)
        row_key.addWidget(self._afk_key_btn)
        
        self._afk_key_hint = QLabel("Click to record")
        self._afk_key_hint.setStyleSheet(f"color: {NOTE}; font-size: 10px;")
        self._afk_key_hint.hide()
        row_key.addWidget(self._afk_key_hint)
        row_key.addStretch(1)
        form.addLayout(row_key)

        # Press Count row
        row_press = QHBoxLayout()
        row_press.setSpacing(8)
        lbl_press = QLabel("Press Count:")
        lbl_press.setStyleSheet(f"color: {MUTED}; font-size: 11px; min-width: 80px;")
        row_press.addWidget(lbl_press)
        self._afk_press_spin = QSpinBox()
        self._afk_press_spin.setRange(1, 10)
        self._afk_press_spin.setValue(1)
        self._afk_press_spin.setFixedWidth(60)
        self._afk_press_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._afk_press_spin.setStyleSheet(
            f"QSpinBox {{ background: {INPUT}; border: 1px solid {LINE};"
            f" color: {TEXT}; padding: 4px; border-radius: 3px; }}"
        )
        self._afk_press_spin.valueChanged.connect(self._on_afk_setting_changed)
        row_press.addWidget(self._afk_press_spin)
        row_press.addStretch(1)
        form.addLayout(row_press)

        # Interval row
        row_interval = QHBoxLayout()
        row_interval.setSpacing(8)
        lbl_interval = QLabel("Interval (min):")
        lbl_interval.setStyleSheet(f"color: {MUTED}; font-size: 11px; min-width: 80px;")
        row_interval.addWidget(lbl_interval)
        self._afk_interval_spin = QSpinBox()
        self._afk_interval_spin.setRange(1, 120)
        self._afk_interval_spin.setValue(10)
        self._afk_interval_spin.setFixedWidth(60)
        self._afk_interval_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._afk_interval_spin.setStyleSheet(
            f"QSpinBox {{ background: {INPUT}; border: 1px solid {LINE};"
            f" color: {TEXT}; padding: 4px; border-radius: 3px; }}"
        )
        self._afk_interval_spin.valueChanged.connect(self._on_afk_setting_changed)
        row_interval.addWidget(self._afk_interval_spin)
        row_interval.addStretch(1)
        form.addLayout(row_interval)

        # Tooltip checkbox
        self._afk_tooltip_chk = QCheckBox("Show countdown tooltip")
        self._afk_tooltip_chk.setChecked(True)
        self._afk_tooltip_chk.setStyleSheet(f"QCheckBox {{ color: {MUTED}; font-size: 11px; }}")
        self._afk_tooltip_chk.stateChanged.connect(self._on_afk_setting_changed)
        form.addWidget(self._afk_tooltip_chk)

        lay.addLayout(form)
        lay.addStretch(1)

        self._load_afk_settings()
        
        # Install event filter for key recording
        self._key_grab_active = False
        self._afk_key_btn.installEventFilter(self)
        
        self._afk_tooltip = _FloatingTooltip()
        self._afk_tooltip.hide()
        
        actions.set_afk_tooltip_callback(self._on_afk_tooltip_emit)
        
        return panel

    def _load_afk_settings(self):
        saved = actions.load_ui_settings()
        self._afk_key = saved.get("anti_afk_key", "w")
        self._afk_press_count = saved.get("anti_afk_press_count", 1)
        self._afk_interval = saved.get("anti_afk_interval", 10)
        self._afk_tooltip_enabled = saved.get("anti_afk_tooltip_enabled", True)
        self._afk_enabled = saved.get("anti_afk_enabled", False)

        self._afk_key_btn.setText(self._afk_key.upper())
        self._afk_press_spin.setValue(int(self._afk_press_count))
        self._afk_interval_spin.setValue(int(self._afk_interval))
        self._afk_tooltip_chk.setChecked(bool(self._afk_tooltip_enabled))
        self._afk_enabled_chk.setChecked(bool(self._afk_enabled))
        self._update_afk_status()

    def _on_afk_setting_changed(self):
        self._afk_key = self._afk_key_btn.text().lower()
        self._afk_press_count = self._afk_press_spin.value()
        self._afk_interval = self._afk_interval_spin.value()
        self._afk_tooltip_enabled = self._afk_tooltip_chk.isChecked()
        self._save_afk_settings()

    def _on_afk_record_key(self):
        self._afk_key_btn.setText("...")
        self._afk_key_hint.show()
        self._afk_key_btn.setFocus()
        self._key_grab_active = True
    
    def _on_afk_tooltip_emit(self, message, x, y):
        self._bridge.afk_tooltip.emit(message, x, y)
    
    def _on_afk_tooltip_signal(self, message, x, y):
        if message is None:
            self._afk_tooltip.hide()
        else:
            self._afk_tooltip.show_message(message, x, y)

    def eventFilter(self, obj, event): # Handle key recording via event filter on the key button
        if obj == self._afk_key_btn and self._key_grab_active:
            if event.type() == event.Type.KeyPress:
                key_code = event.key()
                modifiers = event.modifiers()
                
                if key_code == Qt.Key_Escape:
                    self._key_grab_active = False
                    self._afk_key_hint.hide()
                    self._afk_key_btn.setText(self._afk_key.upper())
                    return True
                
                key_text = ""
                
                char_text = event.text().upper()
                if char_text and len(char_text) == 1 and char_text.isalpha():
                    key_text = char_text
                elif char_text and len(char_text) == 1 and char_text.isdigit():
                    key_text = char_text
                
                if not key_text:
                    key_map = {
                        Qt.Key_Space: "SPACE",
                        Qt.Key_Tab: "TAB",
                        Qt.Key_Backspace: "BACKSPACE",
                        Qt.Key_Return: "ENTER",
                        Qt.Key_Enter: "NUMPADENTER",
                        Qt.Key_Delete: "DELETE",
                        Qt.Key_Insert: "INSERT",
                        Qt.Key_Home: "HOME",
                        Qt.Key_End: "END",
                        Qt.Key_PageUp: "PGUP",
                        Qt.Key_PageDown: "PGDOWN",
                        Qt.Key_Down: "DOWN",
                        Qt.Key_Left: "LEFT",
                        Qt.Key_Right: "RIGHT",
                        Qt.Key_Up: "UP",

                        Qt.Key_F1: "F1", Qt.Key_F2: "F2", Qt.Key_F3: "F3",
                        Qt.Key_F4: "F4", Qt.Key_F5: "F5", Qt.Key_F6: "F6",
                        Qt.Key_F7: "F7", Qt.Key_F8: "F8", Qt.Key_F9: "F9",
                        Qt.Key_F10: "F10", Qt.Key_F11: "F11", Qt.Key_F12: "F12",

                        Qt.Key_Shift: "SHIFT",
                        Qt.Key_Control: "CTRL",
                        Qt.Key_Alt: "ALT",
                        Qt.Key_Meta: "WIN",
                        Qt.Key_AltGr: "ALTGR",

                        Qt.Key_CapsLock: "CAPSLOCK",
                        Qt.Key_NumLock: "NUMLOCK",
                        Qt.Key_ScrollLock: "SCROLLLOCK",

                        Qt.Key_Minus: "-",
                        Qt.Key_Equal: "=",
                        Qt.Key_BracketLeft: "[",
                        Qt.Key_BracketRight: "]",
                        Qt.Key_Backslash: "\\",
                        Qt.Key_Semicolon: ";",
                        Qt.Key_QuoteLeft: "'",
                        Qt.Key_Comma: ",",
                        Qt.Key_Period: ".",
                        Qt.Key_Slash: "/",
                        Qt.Key_QuoteLeft: "`",

                        Qt.Key_A: "A", Qt.Key_B: "B", Qt.Key_C: "C",
                        Qt.Key_D: "D", Qt.Key_E: "E", Qt.Key_F: "F",
                        Qt.Key_G: "G", Qt.Key_H: "H", Qt.Key_I: "I",
                        Qt.Key_J: "J", Qt.Key_K: "K", Qt.Key_L: "L",
                        Qt.Key_M: "M", Qt.Key_N: "N", Qt.Key_O: "O",
                        Qt.Key_P: "P", Qt.Key_Q: "Q", Qt.Key_R: "R",
                        Qt.Key_S: "S", Qt.Key_T: "T", Qt.Key_U: "U",
                        Qt.Key_V: "V", Qt.Key_W: "W", Qt.Key_X: "X",
                        Qt.Key_Y: "Y", Qt.Key_Z: "Z",
                        Qt.Key_0: "0", Qt.Key_1: "1", Qt.Key_2: "2",
                        Qt.Key_3: "3", Qt.Key_4: "4", Qt.Key_5: "5",
                        Qt.Key_6: "6", Qt.Key_7: "7", Qt.Key_8: "8",
                        Qt.Key_9: "9",
                    }
                    key_text = key_map.get(key_code, "")
                    
                    if not key_text and Qt.Key_0 <= key_code <= Qt.Key_9:
                        if modifiers & Qt.KeyboardModifier.KeypadModifier:
                            key_text = f"NUMPAD{chr(key_code)}"
                
                if key_text:
                    self._afk_key = key_text.lower()
                    self._afk_key_btn.setText(key_text)
                    self._afk_key_hint.hide()
                    self._key_grab_active = False
                    self._on_afk_setting_changed()
                else:
                    self._key_grab_active = False
                    self._afk_key_hint.hide()
                    self._afk_key_btn.setText(self._afk_key.upper())
                return True

            elif event.type() == QEvent.MouseButtonPress:
                button = event.button()

                mouse_map = {
                    Qt.LeftButton: "LMB",
                    Qt.RightButton: "RMB",
                    Qt.MiddleButton: "MMB",
                    Qt.BackButton: "MBACK",
                    Qt.ForwardButton: "MFWD",
                }

                key_text = mouse_map.get(button)

                if key_text:
                    self._afk_key = key_text.lower()
                    self._afk_key_btn.setText(key_text)
                    self._afk_key_hint.hide()
                    self._key_grab_active = False
                    self._on_afk_setting_changed()
                return True
        return super().eventFilter(obj, event)

    def _on_afk_enabled_changed(self, state):
        self._afk_enabled = (state == Qt.CheckState.Checked.value)
        self._save_afk_settings()
        self._update_afk_status()
        if self._afk_enabled:
            actions.start_anti_afk(
                self._afk_key,
                self._afk_press_count,
                self._afk_interval,
                self._afk_tooltip_enabled,
            )
        else:
            actions.stop_anti_afk()

    def _update_afk_status(self):
        status = "Running" if self._afk_enabled else "Stopped"
        color = self._AR_ACTIVE_COLOR if self._afk_enabled else self._AR_INACTIVE_COLOR
        self._afk_status_lbl.setText(f"Status: {status}")
        self._afk_status_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")

    def _save_afk_settings(self):
        actions.save_ui_setting("anti_afk_key", self._afk_key)
        actions.save_ui_setting("anti_afk_press_count", self._afk_press_count)
        actions.save_ui_setting("anti_afk_interval", self._afk_interval)
        actions.save_ui_setting("anti_afk_tooltip_enabled", self._afk_tooltip_enabled)
        actions.save_ui_setting("anti_afk_enabled", self._afk_enabled)

    def _build_multi_roblox_panel(self) -> QFrame: # Multi Roblox
        panel = QFrame()
        panel.setObjectName("centerPanel")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        ttl = QLabel("Multi Roblox")
        ttl.setObjectName("sectionTitle")
        hdr.addWidget(ttl)
        hdr.addStretch(1)
        self._mr_status_lbl = QLabel("Status: Disabled")
        self._mr_status_lbl.setStyleSheet("color: #EF5350; font-size: 11px;")
        hdr.addWidget(self._mr_status_lbl)
        lay.addLayout(hdr)

        desc = QLabel(
            "Allows multiple Roblox instances to run simultaneously. "
            "Choose Default (mutex) or Handle64 (Sysinternals) method."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        lay.addWidget(desc)

        # Enable checkbox
        self._mr_enabled_chk = QCheckBox("Enable Multi Roblox")
        self._mr_enabled_chk.setStyleSheet(f"QCheckBox {{ color: {TEXT}; font-size: 12px; font-weight: 700; }}")
        self._mr_enabled_chk.stateChanged.connect(self._on_mr_enabled_changed)
        lay.addWidget(self._mr_enabled_chk)

        # Settings form
        form = QVBoxLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(10)

        # Method row
        row_method = QHBoxLayout()
        row_method.setSpacing(8)
        lbl_method = QLabel("Method:")
        lbl_method.setStyleSheet(f"color: {MUTED}; font-size: 11px; min-width: 80px;")
        row_method.addWidget(lbl_method)

        self._mr_default_radio = QRadioButton("Default")
        self._mr_default_radio.setStyleSheet(f"QRadioButton {{ color: {TEXT}; font-size: 11px; }}")
        self._mr_default_radio.setToolTip(
            "Uses a Windows mutex (ROBLOX_singletonEvent) to allow multiple\n"
            "Roblox instances. Works without administrator rights.\n"
            "Also applies the Error 773 (cookie lock) fix automatically."
        )
        self._mr_default_radio.toggled.connect(self._on_mr_method_changed)
        row_method.addWidget(self._mr_default_radio)

        self._mr_handle64_radio = QRadioButton("Handle64")
        self._mr_handle64_radio.setStyleSheet(f"QRadioButton {{ color: {TEXT}; font-size: 11px; }}")
        self._mr_handle64_radio.setToolTip(
            "Uses handle64.exe (Sysinternals) to close the singleton handle\n"
            "in each Roblox process as it launches. More reliable but\n"
            "REQUIRES administrator privileges and handle64.exe to be present."
        )
        self._mr_handle64_radio.toggled.connect(self._on_mr_method_changed)
        row_method.addWidget(self._mr_handle64_radio)
        row_method.addStretch(1)
        form.addLayout(row_method)

        # Handle64 status row
        row_h64 = QHBoxLayout()
        row_h64.setSpacing(8)
        lbl_h64 = QLabel("Handle64:")
        lbl_h64.setStyleSheet(f"color: {MUTED}; font-size: 11px; min-width: 80px;")
        row_h64.addWidget(lbl_h64)

        self._mr_h64_status_lbl = QLabel()
        self._mr_h64_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        row_h64.addWidget(self._mr_h64_status_lbl)

        self._mr_dl_btn = QPushButton("Download Handle64")
        self._mr_dl_btn.setToolTip(
            "Downloads handle64.exe from Sysinternals (Microsoft)\n"
            "and saves it to the AccountManagerData folder."
        )
        self._mr_dl_btn.setFixedHeight(24)
        self._mr_dl_btn.setStyleSheet(
            f"QPushButton {{ background: {INPUT}; border: 1px solid {LINE}; "
            f"padding: 2px 8px; font-size: 11px; color: {TEXT}; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {SELECT}; }}"
            f"QPushButton:disabled {{ color: {MUTED}; }}"
        )
        self._mr_dl_btn.clicked.connect(self._on_mr_download_handle64)
        row_h64.addWidget(self._mr_dl_btn)
        row_h64.addStretch(1)
        form.addLayout(row_h64)

        lay.addLayout(form)
        lay.addStretch(1)

        # Load saved state
        self._load_mr_settings()
        return panel

    def _is_admin(self) -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _load_mr_settings(self):
        saved = actions.load_ui_settings()
        self._mr_method = saved.get("multi_roblox_method", "default")
        self._mr_enabled = saved.get("multi_roblox_enabled", False)

        handle64_available = bool(actions.find_handle64())
        self._mr_handle64_radio.setEnabled(handle64_available)

        self._mr_handle64_radio.blockSignals(True)
        self._mr_default_radio.blockSignals(True)
        if self._mr_method == "handle64" and handle64_available:
            self._mr_handle64_radio.setChecked(True)
        else:
            if self._mr_method == "handle64" and not handle64_available:
                self._mr_method = "default"
                actions.save_ui_setting("multi_roblox_method", "default")
            self._mr_default_radio.setChecked(True)
        self._mr_handle64_radio.blockSignals(False)
        self._mr_default_radio.blockSignals(False)

        self._mr_enabled_chk.blockSignals(True)
        self._mr_enabled_chk.setChecked(self._mr_enabled)
        self._mr_enabled_chk.blockSignals(False)
        self._update_mr_h64_status()
        self._update_mr_status()

        if self._mr_enabled:
            self._start_multi_roblox()

    def _update_mr_h64_status(self):
        path = actions.find_handle64()
        if path:
            self._mr_h64_status_lbl.setText("[handle64 found]")
            self._mr_h64_status_lbl.setStyleSheet("color: #4CAF50; font-size: 10px;")
            self._mr_handle64_radio.setEnabled(True)
            self._mr_dl_btn.setText("Downloaded")
            self._mr_dl_btn.setEnabled(False)
        else:
            self._mr_h64_status_lbl.setText("[handle64 not found]")
            self._mr_h64_status_lbl.setStyleSheet("color: #EF5350; font-size: 10px;")
            self._mr_handle64_radio.setEnabled(False)
            self._mr_dl_btn.setText("Download Handle64")
            self._mr_dl_btn.setEnabled(True)

    def _on_mr_method_changed(self):
        if self._mr_handle64_radio.isChecked():
            if not self._is_admin():
                self._mr_ask_restart_as_admin()
                self._mr_default_radio.blockSignals(True)
                self._mr_handle64_radio.blockSignals(True)
                self._mr_default_radio.setChecked(True)
                self._mr_default_radio.blockSignals(False)
                self._mr_handle64_radio.blockSignals(False)
                self._mr_method = "default"
                actions.save_ui_setting("multi_roblox_method", self._mr_method)
                if self._mr_enabled:
                    self._stop_multi_roblox()
                    self._start_multi_roblox()
                return
            self._mr_method = "handle64"
        else:
            self._mr_method = "default"
        actions.save_ui_setting("multi_roblox_method", self._mr_method)
        if self._mr_enabled:
            self._stop_multi_roblox()
            self._start_multi_roblox()

    def _on_mr_enabled_changed(self, state):
        try:
            self._mr_enabled = (state == Qt.CheckState.Checked.value)
            actions.save_ui_setting("multi_roblox_enabled", self._mr_enabled)

            if self._mr_enabled:
                QTimer.singleShot(0, self._start_multi_roblox)
            else:
                self._stop_multi_roblox()

            self._update_mr_status()
            
        except Exception as e:
            print(f"Error in _on_mr_enabled_changed: {e}")

    def _start_multi_roblox(self):
        if self._mr_method == "default":
            roblox_running = actions.is_roblox_running()
            if roblox_running:
                reply = QMessageBox.question(
                    self,
                    "Multi Roblox",
                    "Roblox is currently running.\n"
                    "Multi Roblox (default) must be enabled before Roblox starts.\n"
                    "Do you want to close all Roblox processes now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    actions.kill_roblox()
                    deadline = time.time() + 3.0
                    while time.time() < deadline and actions.is_roblox_running():
                        time.sleep(0.2)
                else:
                    self._mr_enabled = False
                    self._mr_enabled_chk.blockSignals(True)
                    self._mr_enabled_chk.setChecked(False)
                    self._mr_enabled_chk.blockSignals(False)
                    actions.save_ui_setting("multi_roblox_enabled", False)
                    self._update_mr_status() 
                    return

        ok, msg = actions.enable_multi_roblox(self._mr_method)
        if not ok:
            if msg == "NEEDS_ADMIN":
                self._mr_ask_restart_as_admin()
            elif msg == "ROBLOX_RUNNING":
                self._mr_status_lbl.setText("Error: Close Roblox first, then enable Multi Roblox.")
                self._mr_status_lbl.setStyleSheet("color: #EF5350; font-size: 11px;")
            else:
                self._mr_status_lbl.setText(f"Error: {msg}")
                self._mr_status_lbl.setStyleSheet("color: #EF5350; font-size: 11px;")
            self._mr_enabled = False
            self._mr_enabled_chk.blockSignals(True)
            self._mr_enabled_chk.setChecked(False)
            self._mr_enabled_chk.blockSignals(False)
            actions.save_ui_setting("multi_roblox_enabled", False)
            self._update_mr_status()
        else:
            self._update_mr_status()

    def _mr_ask_restart_as_admin(self):
        reply = QMessageBox.question(
            self,
            "Administrator Required",
            "The program is not running as administrator.\n\n"
            "Handle64 mode requires administrator privileges.\n\n"
            "Do you want to relaunch the app as administrator?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if getattr(sys, "frozen", False):
                    executable = sys.executable
                    params = " ".join(f'"{a}"' for a in sys.argv[1:])
                else:
                    executable = sys.executable
                    params = " ".join(f'"{a}"' for a in sys.argv)
                ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
                QApplication.quit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to restart as administrator:\n{e}")

    def _stop_multi_roblox(self):
        actions.disable_multi_roblox()
        self._update_mr_status()

    def _update_mr_status(self):
        running = self._mr_enabled_chk.isChecked()
        method_str = "Handle64" if getattr(self, "_mr_method", "default") == "handle64" else "Default"
        if running:
            self._mr_status_lbl.setText(f"Status: Running ({method_str})")
            self._mr_status_lbl.setStyleSheet("color: #4CAF50; font-size: 11px;")
        else:
            self._mr_status_lbl.setText("Status: Disabled")
            self._mr_status_lbl.setStyleSheet("color: #EF5350; font-size: 11px;")

    def _on_mr_download_handle64(self):
        self._mr_dl_btn.setText("Downloading...")
        self._mr_dl_btn.setEnabled(False)

        def _thread():
            ok = actions.download_handle64()
            self._bridge.mr_download_done.emit(ok)

        threading.Thread(target=_thread, daemon=True).start()

    def _build_settings_panel(self) -> QFrame: # Settings panel
        panel = QFrame()
        panel.setObjectName("centerPanel")

        root_lay = QHBoxLayout(panel)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Left category list
        cat_panel = QFrame()
        cat_panel.setFixedWidth(120)
        cat_panel.setStyleSheet(
            f"QFrame {{ background: {BG}; border-right: 1px solid {LINE}; }}"
        )
        cat_lay = QVBoxLayout(cat_panel)
        cat_lay.setContentsMargins(0, 10, 0, 10)
        cat_lay.setSpacing(2)

        cat_header = QLabel("Settings")
        cat_header.setStyleSheet(
            f"color: {MUTED}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 0.5px; padding: 0 10px 6px 10px;"
        )
        cat_lay.addWidget(cat_header)

        # Right stacked content
        content_stack = QStackedWidget()
        content_stack.setStyleSheet("background: transparent;")

        CATEGORIES = ["General", "Roblox", "Discord", "Misc", "Developer"]
        cat_buttons: list[QPushButton] = []

        def _switch_cat(idx: int):
            content_stack.setCurrentIndex(idx)
            for i, b in enumerate(cat_buttons):
                b.setChecked(i == idx)

        for i, name in enumerate(CATEGORIES):
            btn = QPushButton(name)
            btn.setObjectName("navTab")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda _=False, idx=i: _switch_cat(idx))
            cat_lay.addWidget(btn)
            cat_buttons.append(btn)

        cat_lay.addStretch(1)

        root_lay.addWidget(cat_panel)
        root_lay.addWidget(content_stack, 1)

        # Shared helpers
        def _scrollable() -> tuple[QScrollArea, QVBoxLayout]:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            sa.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            w = QWidget()
            w.setStyleSheet("background: transparent;")
            lay = QVBoxLayout(w)
            lay.setContentsMargins(16, 14, 16, 14)
            lay.setSpacing(6)
            sa.setWidget(w)
            return sa, lay

        S = actions.load_ui_settings() # Snapshot for initial values

        def _chk(key, label: str, tip: str, default=False,
                 on_change=None) -> QCheckBox:
            cb = QCheckBox(label)
            cb.setChecked(S.get(key, default) if key is not None else False)
            cb.setToolTip(tip)
            def _h(state):
                val = (state == Qt.CheckState.Checked.value)
                if key is not None:
                    actions.save_ui_setting(key, val)
                if on_change:
                    on_change(val)
            cb.stateChanged.connect(_h)
            return cb

        def _sec(title: str) -> QLabel:
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"color: {MUTED}; font-size: 9px; font-weight: 700; "
                f"letter-spacing: 0.5px; margin-top: 8px;"
            )
            return lbl

        def _sub_indent(widget, px=18):
            row = QHBoxLayout()
            row.setContentsMargins(px, 0, 0, 0)
            row.addWidget(widget)
            return row

        # General (Page 0)
        sa, f = _scrollable()
        content_stack.addWidget(sa)

        f.addWidget(_sec("WINDOW"))
        self._sett_topmost_chk = _chk(
            "enable_topmost", "Always on Top",
            "Keep this window above all other windows.\n"
            "Useful when managing accounts alongside other apps.",
            on_change=self._on_sett_topmost,
        )
        f.addWidget(self._sett_topmost_chk)

        self._sett_tray_chk = _chk(
            "hide_to_system_tray", "Hide to System Tray",
            "Keep Evanovar RAM running in the system tray when the main window is closed.\n"
            "Use the tray icon to show the window again or exit the application.",
            on_change=self._on_sett_tray,
        )
        f.addWidget(self._sett_tray_chk)

        f.addWidget(_sec("LAUNCH"))
        self._sett_confirm_chk = _chk(
            "confirm_before_launch", "Confirm Before Launch",
            "Show a confirmation prompt before any Roblox join/launch action.\n"
            "Prevents accidental launches.",
        )
        f.addWidget(self._sett_confirm_chk)

        f.addWidget(_sec("ACCOUNTS LIST"))
        self._sett_multisel_chk = _chk(
            "enable_multi_select", "Multi-Select (Ctrl / Shift + Click)",
            "Allow selecting multiple accounts simultaneously.\n"
            "Enables batch join, launch, and removal.",
            on_change=self._on_sett_multi_select,
        )
        f.addWidget(self._sett_multisel_chk)

        f.addWidget(_sec("SYSTEM"))
        self._sett_update_chk = _chk(
            "check_updates_on_startup", "Check for Updates on Startup",
            "Automatically check GitHub for a newer version when the app launches.\n"
            "An update window will appear if a newer release is found.",
        )
        self._sett_update_chk.setChecked(
            actions.load_ui_settings().get("check_updates_on_startup", True)
        )
        f.addWidget(self._sett_update_chk)

        # Start Menu shortcut
        _sm_path = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs",
            "Roblox Account Manager.lnk"
        )
        self._sett_startmenu_chk = QCheckBox("Add to Start Menu")
        self._sett_startmenu_chk.setChecked(os.path.exists(_sm_path))
        self._sett_startmenu_chk.setToolTip(
            "Create (or remove) a Start Menu shortcut for this application.\n"
            "Works with both the .exe build and the Python script."
        )
        self._sett_startmenu_chk.stateChanged.connect(
            lambda state: self._on_sett_start_menu(state, _sm_path)
        )
        f.addWidget(self._sett_startmenu_chk)

        _startup_enabled = windows_startup_mod.is_startup_enabled()
        self._sett_startup_chk = QCheckBox("Start with Windows")
        self._sett_startup_chk.setChecked(_startup_enabled)
        self._sett_startup_chk.setToolTip(
            "Start Evanovar RAM automatically when you sign in to Windows.\n"
            "This creates a shortcut in your Windows Startup folder."
        )
        self._sett_startup_chk.stateChanged.connect(self._on_sett_startup)
        f.addWidget(self._sett_startup_chk)

        f.addWidget(_sec("RECENT GAMES"))
        mg_row = QHBoxLayout()
        mg_row.setContentsMargins(0, 0, 0, 0)
        mg_l = QLabel("Max Recent Games")
        mg_l.setToolTip(
            "How many recent games to keep in the history list.\n"
            "Older entries are dropped automatically."
        )
        mg_row.addWidget(mg_l)
        mg_row.addStretch(1)
        self._sett_mg_spin = QSpinBox()
        self._sett_mg_spin.setRange(5, 50)
        self._sett_mg_spin.setValue(int(S.get("max_recent_games", 10)))
        self._sett_mg_spin.setFixedWidth(64)
        self._sett_mg_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._sett_mg_spin.valueChanged.connect(
            lambda v: actions.save_ui_setting("max_recent_games", v)
        )
        mg_row.addWidget(self._sett_mg_spin)
        f.addLayout(mg_row)

        f.addStretch(1)

        # Roblox (Page 1)
        sa, f = _scrollable()
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_stack.addWidget(sa)

        f.addWidget(_sec("LAUNCHER"))
        _launcher_lbl = QLabel(
            "Choose how Roblox is launched when you join a game."
        )
        _launcher_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        _launcher_lbl.setWordWrap(True)
        f.addWidget(_launcher_lbl)

        LAUNCHERS = [
            ("default",   "Automatic (roblox://)",
             "Launch via the standard roblox:// URI protocol (roblox-player)."),
            ("bloxstrap", "Bloxstrap",
             "Launch using Bloxstrap, an open-source Roblox bootstrapper with extra features."),
            ("fishstrap", "Fishstrap",
             "Launch using Fishstrap, a Bloxstrap fork."),
            ("froststrap", "Froststrap",
             "Launch using Froststrap."),
            ("client", "Roblox Client (direct .exe)",
             "Directly invoke the RobloxPlayerBeta.exe."),
            ("custom",    "Custom",
             "Specify a custom executable path to use as the launcher."),
        ]
        _cur_launcher = S.get("roblox_launcher", "default")
        _launcher_grp = QButtonGroup(sa)
        self._sett_launcher_radios: dict[str, QRadioButton] = {}

        for key, label, tip in LAUNCHERS:
            rb = QRadioButton(label)
            rb.setToolTip(tip)
            rb.setChecked(key == _cur_launcher)
            _launcher_grp.addButton(rb)
            self._sett_launcher_radios[key] = rb
            f.addWidget(rb)

        # Custom path row
        _custom_row = QHBoxLayout()
        _custom_row.setContentsMargins(20, 0, 0, 0)
        self._sett_custom_launcher_edit = QLineEdit()
        self._sett_custom_launcher_edit.setPlaceholderText("Path to launcher .exe ...")
        self._sett_custom_launcher_edit.setText(str(S.get("custom_roblox_launcher_path", "") or ""))
        self._sett_custom_launcher_edit.setEnabled(_cur_launcher == "custom")
        self._sett_custom_launcher_edit.editingFinished.connect(
            lambda: actions.save_ui_setting(
                "custom_roblox_launcher_path",
                self._sett_custom_launcher_edit.text(),
            )
        )
        _custom_row.addWidget(self._sett_custom_launcher_edit)
        _browse_btn = QPushButton("Browse")
        _browse_btn.setFixedWidth(60)
        _browse_btn.setEnabled(_cur_launcher == "custom")
        _browse_btn.clicked.connect(self._on_sett_browse_launcher)
        _custom_row.addWidget(_browse_btn)
        f.addLayout(_custom_row)
        self._sett_browse_btn = _browse_btn

        def _on_launcher_toggled(key):
            def _h(checked):
                if checked:
                    actions.save_ui_setting("roblox_launcher", key)
                    is_custom = (key == "custom")
                    self._sett_custom_launcher_edit.setEnabled(is_custom)
                    self._sett_browse_btn.setEnabled(is_custom)
            return _h

        for key, rb in self._sett_launcher_radios.items():
            rb.toggled.connect(_on_launcher_toggled(key))

        f.addWidget(_sec("WINDOWS"))
        self._sett_rename_chk = _chk(
            "rename_roblox_windows", "Rename Roblox Windows to Username",
            "Set each Roblox window's title bar to the account username\n"
            "so you can identify windows at a glance.",
            on_change=self._on_sett_rename_windows,
        )
        f.addWidget(self._sett_rename_chk)

        self._sett_monitoring_chk = _chk(
            "presence_indicator", "Account Activity Monitor",
            "Show online status and local Roblox RAM and CPU usage.\n"
            "Scans saved accounts every 5 seconds without using the Roblox API.",
            on_change=self._on_sett_presence_indicator,
        )
        f.addWidget(self._sett_monitoring_chk)

        # Start scanner immediately if the setting is already on
        if actions.load_ui_settings().get("presence_indicator", False):
            self._start_presence_scanner()

        f.addWidget(_sec("WINDOW GRID"))
        self._sett_window_grid_chk = _chk(
            "window_grid_enabled", "Enable Window Grid Keybind",
            "Register a global keybind that arranges every visible Roblox window\n"
            "into an equal grid on the monitor under your cursor.",
            on_change=self._on_sett_window_grid,
        )
        f.addWidget(self._sett_window_grid_chk)

        window_grid_row = QHBoxLayout()
        window_grid_row.setContentsMargins(20, 0, 0, 0)
        window_grid_label = QLabel("Keybind")
        window_grid_label.setToolTip(
            "Click the button, press a shortcut, then release its main key."
        )
        window_grid_row.addWidget(window_grid_label)
        window_grid_row.addStretch(1)
        self._sett_window_grid_key_btn = _HotkeyCaptureButton(
            str(
                S.get(
                    "window_grid_keybind",
                    window_grid_mod.DEFAULT_HOTKEY,
                )
                or window_grid_mod.DEFAULT_HOTKEY
            )
        )
        self._sett_window_grid_key_btn.setFixedWidth(150)
        self._sett_window_grid_key_btn.setEnabled(
            bool(S.get("window_grid_enabled", False))
        )
        self._sett_window_grid_key_btn.setToolTip(
            "Click to record a global keybind. Press Escape to cancel.\n"
            f"Default: {window_grid_mod.DEFAULT_HOTKEY}"
        )
        self._sett_window_grid_key_btn.recording_started.connect(
            self._unregister_window_grid_hotkey
        )
        self._sett_window_grid_key_btn.recording_canceled.connect(
            self._restore_window_grid_hotkey_after_recording
        )
        self._sett_window_grid_key_btn.sequence_changed.connect(
            self._on_sett_window_grid_keybind
        )
        window_grid_row.addWidget(self._sett_window_grid_key_btn)
        f.addLayout(window_grid_row)

        f.addWidget(_sec("FIXES"))
        self._sett_installer_fix_chk = _chk(
            "roblox_installer_fix", "Roblox Installer Fix",
            "Moves RobloxPlayerInstaller.exe out of each Roblox version folder\n"
            "on launch to stop the installer popup, then restores it on exit.",
            on_change=self._on_sett_installer_fix,
        )
        f.addWidget(self._sett_installer_fix_chk)

        f.addWidget(_sec("RAM OPTIMIZATION"))
        self._sett_boost_ram_chk = _chk(
            "optimize_roblox_ram", "Boost Roblox RAM Limit (May Cause Crash)",
            "Periodically trim Roblox working-set memory to reduce RAM usage.\n"
            "May causes crash when using this feature, use with caution.",
            on_change=self._on_sett_boost_ram,
        )
        f.addWidget(self._sett_boost_ram_chk)

        ram_row = QHBoxLayout()
        ram_row.setContentsMargins(20, 0, 0, 0)
        _ram_lbl = QLabel("Low RAM Limit (MB)")
        _ram_lbl.setToolTip(
            "Target memory limit per Roblox process in megabytes.\n"
            "Processes using more than this will have their working set trimmed."
        )
        ram_row.addWidget(_ram_lbl)
        ram_row.addStretch(1)
        self._sett_ram_spin = QSpinBox()
        self._sett_ram_spin.setRange(100, 8192)
        self._sett_ram_spin.setValue(int(S.get("optimize_roblox_ram_limit_mb", 750)))
        self._sett_ram_spin.setSuffix(" MB")
        self._sett_ram_spin.setFixedWidth(90)
        self._sett_ram_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._sett_ram_spin.setEnabled(S.get("optimize_roblox_ram", False))
        self._sett_ram_spin.valueChanged.connect(
            lambda v: actions.save_ui_setting("optimize_roblox_ram_limit_mb", v)
        )
        ram_row.addWidget(self._sett_ram_spin)
        f.addLayout(ram_row)

        f.addWidget(_sec("ROBLOX DOWNLOADER"))
        _roblox_downloader_desc = QLabel(
            "Download a Windows Roblox Player deployment directly from Roblox."
        )
        _roblox_downloader_desc.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        _roblox_downloader_desc.setWordWrap(True)
        f.addWidget(_roblox_downloader_desc)

        _roblox_downloader_custom = bool(
            S.get("roblox_downloader_customizations", False)
        )
        self._sett_roblox_downloader_custom_chk = _chk(
            "roblox_downloader_customizations",
            "Enable Customizations",
            "Enable a custom Roblox version hash and download location.\n"
            "When disabled, the latest LIVE version is downloaded to Roblox's "
            "default Versions folder.",
            on_change=self._on_sett_roblox_downloader_customizations,
        )
        f.addWidget(self._sett_roblox_downloader_custom_chk)

        roblox_version_row = QHBoxLayout()
        roblox_version_row.setContentsMargins(20, 0, 0, 0)
        roblox_version_label = QLabel("Version")
        roblox_version_label.setFixedWidth(78)
        roblox_version_label.setToolTip(
            "Use LIVE for the latest WindowsPlayer version,\n"
            "or enter a specific version hash."
        )
        roblox_version_row.addWidget(roblox_version_label)
        self._sett_roblox_downloader_version_edit = QLineEdit()
        self._sett_roblox_downloader_version_edit.setPlaceholderText("LIVE")
        self._sett_roblox_downloader_version_edit.setText(
            str(S.get("roblox_downloader_version", "LIVE") or "LIVE")
        )
        self._sett_roblox_downloader_version_edit.setEnabled(
            _roblox_downloader_custom
        )
        self._sett_roblox_downloader_version_edit.editingFinished.connect(
            lambda: actions.save_ui_setting(
                "roblox_downloader_version",
                self._sett_roblox_downloader_version_edit.text(),
            )
        )
        roblox_version_row.addWidget(self._sett_roblox_downloader_version_edit, 1)
        f.addLayout(roblox_version_row)

        roblox_location_row = QHBoxLayout()
        roblox_location_row.setContentsMargins(20, 0, 0, 0)
        roblox_location_label = QLabel("Location Path")
        roblox_location_label.setFixedWidth(78)
        roblox_location_label.setToolTip(
            "Folder that will contain the downloaded version folder."
        )
        roblox_location_row.addWidget(roblox_location_label)
        self._sett_roblox_downloader_location_edit = QLineEdit()
        self._sett_roblox_downloader_location_edit.setPlaceholderText(
            roblox_downloader_mod.get_default_versions_path()
        )
        self._sett_roblox_downloader_location_edit.setText(
            str(
                S.get(
                    "roblox_downloader_location",
                    roblox_downloader_mod.get_default_versions_path(),
                )
                or roblox_downloader_mod.get_default_versions_path()
            )
        )
        self._sett_roblox_downloader_location_edit.setEnabled(
            _roblox_downloader_custom
        )
        self._sett_roblox_downloader_location_edit.editingFinished.connect(
            lambda: actions.save_ui_setting(
                "roblox_downloader_location",
                self._sett_roblox_downloader_location_edit.text(),
            )
        )
        roblox_location_row.addWidget(
            self._sett_roblox_downloader_location_edit,
            1,
        )
        self._sett_roblox_downloader_browse_btn = QPushButton("Browse Folder")
        self._sett_roblox_downloader_browse_btn.setEnabled(
            _roblox_downloader_custom
        )
        self._sett_roblox_downloader_browse_btn.clicked.connect(
            self._on_sett_browse_roblox_download_path
        )
        roblox_location_row.addWidget(self._sett_roblox_downloader_browse_btn)
        f.addLayout(roblox_location_row)

        self._sett_roblox_downloader_btn = QPushButton("Download Latest Roblox")
        self._sett_roblox_downloader_btn.setToolTip(
            "Download and extract the selected WindowsPlayer deployment."
        )
        self._sett_roblox_downloader_btn.setStyleSheet(
            f"QPushButton {{ background: {INPUT}; color: {TEXT}; "
            f"border: 1px solid {LINE}; border-radius: 0; "
            f"text-align: center; }}"
            f"QPushButton:hover {{ background: {SELECT}; }}"
        )
        self._sett_roblox_downloader_btn.clicked.connect(
            self._on_sett_download_roblox
        )
        f.addWidget(self._sett_roblox_downloader_btn)

        headless_hdr = QHBoxLayout()
        headless_hdr.setContentsMargins(0, 0, 0, 0)
        headless_hdr.addWidget(_sec("HEADLESS MANAGER"))
        headless_hdr.addStretch(1)
        f.addLayout(headless_hdr)

        self._sett_headless_chk = _chk(
            "headless_manager_enabled", "Enable Headless Manager",
            "Lists every running Roblox process so you can hide or show\n"
            "its window on demand.",
            on_change=self._on_sett_headless_manager,
        )
        f.addWidget(self._sett_headless_chk)

        self._headless_list = QListWidget()
        self._headless_list.setFixedHeight(160)
        self._headless_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._headless_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._headless_list.customContextMenuRequested.connect(self._headless_on_context_menu)
        f.addWidget(self._headless_list)
        self._refresh_headless_list([])

        f.addWidget(_sec("ROBLOX SETTINGS"))
        self._roblox_settings_config = roblox_settings_mod.get_customization_config(
            settings=S
        )
        self._roblox_settings_pending_config = dict(self._roblox_settings_config)

        _roblox_settings_desc = QLabel(
            "Close Roblox before applying changes so it does not overwrite them."
        )
        _roblox_settings_desc.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        _roblox_settings_desc.setWordWrap(True)
        f.addWidget(_roblox_settings_desc)

        f.addWidget(_sec("BASIC SETTINGS"))

        self._sett_framerate_chk = QCheckBox("Enable Framerate Cap")
        self._sett_framerate_chk.setChecked(
            bool(self._roblox_settings_config.get("framerate_enabled", False))
        )
        self._sett_framerate_chk.setToolTip(
            "Apply FramerateCap before Roblox starts."
        )
        self._sett_fps_spin = QSpinBox()
        self._sett_fps_spin.setRange(-1, 999)
        self._sett_fps_spin.setSpecialValueText("Unlimited")
        self._sett_fps_spin.setSuffix(" FPS")
        try:
            self._sett_fps_spin.setValue(
                max(
                    -1,
                    min(
                        999,
                        int(self._roblox_settings_config.get(
                            "framerate_value", 60
                        )),
                    ),
                )
            )
        except (TypeError, ValueError):
            self._sett_fps_spin.setValue(60)
        self._sett_fps_spin.setFixedWidth(90)
        self._sett_fps_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._sett_framerate_chk.stateChanged.connect(
            lambda state: self._on_roblox_managed_toggle(
                "framerate",
                state == Qt.CheckState.Checked.value,
            )
        )
        self._sett_fps_spin.valueChanged.connect(
            self._on_sett_framerate_value
        )
        framerate_row = QHBoxLayout()
        framerate_row.setContentsMargins(20, 0, 0, 0)
        framerate_row.addWidget(self._sett_framerate_chk)
        framerate_row.addStretch(1)
        framerate_row.addWidget(self._sett_fps_spin)
        f.addLayout(framerate_row)

        self._sett_master_volume_chk = QCheckBox("Enable Master Volume")
        self._sett_master_volume_chk.setChecked(
            bool(self._roblox_settings_config.get("master_volume_enabled", False))
        )
        self._sett_master_volume_chk.setToolTip(
            "Apply MasterVolume without changing other Roblox volume settings."
        )
        self._roblox_master_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._roblox_master_volume_slider.setRange(0, 10)
        self._roblox_master_volume_slider.setSingleStep(1)
        self._roblox_master_volume_slider.setFixedWidth(180)
        try:
            master_volume = max(
                0.0,
                min(
                    1.0,
                    float(self._roblox_settings_config.get(
                        "master_volume_value", 1.0
                    )),
                ),
            )
            self._roblox_master_volume_slider.setValue(round(master_volume * 10))
        except (TypeError, ValueError):
            self._roblox_master_volume_slider.setValue(10)
        self._roblox_master_volume_label = QLabel("1.0")
        self._roblox_master_volume_label.setFixedWidth(36)
        self._sett_master_volume_chk.stateChanged.connect(
            lambda state: self._on_roblox_managed_toggle(
                "master_volume",
                state == Qt.CheckState.Checked.value,
            )
        )
        self._roblox_master_volume_slider.valueChanged.connect(
            self._on_master_volume_changed
        )
        master_volume_row = QHBoxLayout()
        master_volume_row.setContentsMargins(20, 0, 0, 0)
        master_volume_row.addWidget(self._sett_master_volume_chk)
        master_volume_row.addStretch(1)
        master_volume_row.addWidget(self._roblox_master_volume_slider)
        master_volume_row.addWidget(self._roblox_master_volume_label)
        f.addLayout(master_volume_row)

        self._sett_start_quality_chk = QCheckBox("Enable Start Quality")
        self._sett_start_quality_chk.setChecked(
            bool(self._roblox_settings_config.get("start_quality_enabled", False))
        )
        self._sett_start_quality_chk.setToolTip(
            "Apply SavedQualityLevel when Roblox starts."
        )
        self._roblox_start_quality_slider = QSlider(Qt.Orientation.Horizontal)
        self._roblox_start_quality_slider.setRange(0, 10)
        self._roblox_start_quality_slider.setSingleStep(1)
        self._roblox_start_quality_slider.setFixedWidth(180)
        try:
            self._roblox_start_quality_slider.setValue(
                max(
                    0,
                    min(
                        10,
                        int(self._roblox_settings_config.get(
                            "start_quality_value", 0
                        )),
                    ),
                )
            )
        except (TypeError, ValueError):
            self._roblox_start_quality_slider.setValue(0)
        self._roblox_start_quality_label = QLabel("0")
        self._roblox_start_quality_label.setFixedWidth(36)
        self._sett_start_quality_chk.stateChanged.connect(
            lambda state: self._on_roblox_managed_toggle(
                "start_quality",
                state == Qt.CheckState.Checked.value,
            )
        )
        self._roblox_start_quality_slider.valueChanged.connect(
            self._on_start_quality_changed
        )
        start_quality_row = QHBoxLayout()
        start_quality_row.setContentsMargins(20, 0, 0, 0)
        start_quality_row.addWidget(self._sett_start_quality_chk)
        start_quality_row.addStretch(1)
        start_quality_row.addWidget(self._roblox_start_quality_slider)
        start_quality_row.addWidget(self._roblox_start_quality_label)
        f.addLayout(start_quality_row)

        f.addWidget(_sec("ADVANCED SETTINGS"))
        self._roblox_settings_search = QLineEdit()
        self._roblox_settings_search.setPlaceholderText("Search Roblox settings...")
        self._roblox_settings_search.textChanged.connect(
            self._filter_roblox_settings
        )
        f.addWidget(self._roblox_settings_search)

        self._roblox_settings_tree = QTreeWidget()
        self._roblox_settings_tree.setColumnCount(3)
        self._roblox_settings_tree.setHeaderLabels(["Setting", "Type", "Value"])
        self._roblox_settings_tree.setFixedHeight(200)
        self._roblox_settings_tree.setRootIsDecorated(False)
        self._roblox_settings_tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._roblox_settings_tree.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._roblox_settings_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._roblox_settings_tree.header().setStretchLastSection(True)
        self._roblox_settings_tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._roblox_settings_tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._roblox_settings_tree.itemSelectionChanged.connect(
            self._on_roblox_setting_selected
        )
        f.addWidget(self._roblox_settings_tree)

        _selected_row = QHBoxLayout()
        _selected_row.setContentsMargins(20, 0, 0, 0)
        _selected_row.addWidget(QLabel("Selected Setting"))
        self._roblox_settings_selected_label = QLabel("None")
        self._roblox_settings_selected_label.setStyleSheet(f"color: {MUTED};")
        _selected_row.addWidget(self._roblox_settings_selected_label, 1)
        f.addLayout(_selected_row)

        _type_row = QHBoxLayout()
        _type_row.setContentsMargins(20, 0, 0, 0)
        _type_row.addWidget(QLabel("Type"))
        self._roblox_settings_type_label = QLabel("None")
        self._roblox_settings_type_label.setStyleSheet(f"color: {MUTED};")
        _type_row.addWidget(self._roblox_settings_type_label, 1)
        f.addLayout(_type_row)

        _state_row = QHBoxLayout()
        _state_row.setContentsMargins(20, 0, 0, 0)
        _state_row.addWidget(QLabel("State"))
        self._roblox_settings_state_label = QLabel("Ready")
        self._roblox_settings_state_label.setStyleSheet(f"color: {MUTED};")
        _state_row.addWidget(self._roblox_settings_state_label, 1)
        f.addLayout(_state_row)

        _value_row = QHBoxLayout()
        _value_row.setContentsMargins(20, 0, 0, 0)
        _value_row.addWidget(QLabel("Value"))
        self._roblox_settings_value_stack = QStackedWidget()
        self._roblox_settings_value_edit = QLineEdit()
        self._roblox_settings_value_edit.editingFinished.connect(
            self._on_roblox_setting_text_finished
        )
        self._roblox_settings_value_stack.addWidget(
            self._roblox_settings_value_edit
        )
        self._roblox_settings_bool_edit = QCheckBox("false")
        self._roblox_settings_bool_edit.stateChanged.connect(
            self._on_roblox_setting_bool_changed
        )
        self._roblox_settings_value_stack.addWidget(
            self._roblox_settings_bool_edit
        )
        self._roblox_settings_value_stack.setEnabled(False)
        _value_row.addWidget(self._roblox_settings_value_stack, 1)
        f.addLayout(_value_row)

        _roblox_settings_btn_row = QHBoxLayout()
        _roblox_settings_btn_row.setContentsMargins(20, 0, 0, 0)
        self._roblox_settings_reload_btn = QPushButton("Reload from Roblox")
        self._roblox_settings_reload_btn.clicked.connect(
            self._reload_roblox_settings
        )
        self._roblox_settings_apply_btn = QPushButton("Apply to Roblox")
        self._roblox_settings_apply_btn.setEnabled(False)
        self._roblox_settings_apply_btn.clicked.connect(
            self._apply_roblox_settings
        )
        _roblox_settings_btn_row.addWidget(self._roblox_settings_reload_btn)
        _roblox_settings_btn_row.addStretch(1)
        _roblox_settings_btn_row.addWidget(self._roblox_settings_apply_btn)
        f.addLayout(_roblox_settings_btn_row)

        self._roblox_settings_auto_apply_chk = QCheckBox(
            "Auto Apply Advanced Settings"
        )
        self._roblox_settings_auto_apply_chk.setChecked(
            bool(self._roblox_settings_config.get("auto_apply", False))
        )
        self._roblox_settings_auto_apply_chk.stateChanged.connect(
            self._on_roblox_advanced_auto_apply_toggle
        )
        f.addWidget(self._roblox_settings_auto_apply_chk)

        f.addStretch(1)

        # Discord (Page 2)
        sa, f = _scrollable()
        content_stack.addWidget(sa)

        dc = S.get("discord_webhook", {})

        f.addWidget(_sec("WEBHOOK"))
        self._sett_dc_enabled_chk = QCheckBox("Enable Discord Webhook")
        self._sett_dc_enabled_chk.setChecked(dc.get("enabled", False))
        self._sett_dc_enabled_chk.setToolTip(
            "Forward log events to a Discord channel via webhook.\n"
            "All events that pass your filters will be posted automatically."
        )
        self._sett_dc_enabled_chk.stateChanged.connect(self._on_dc_save)
        f.addWidget(self._sett_dc_enabled_chk)

        url_row = QHBoxLayout()
        url_row.setContentsMargins(0, 0, 0, 0)
        url_lbl = QLabel("Webhook URL")
        url_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        url_row.addWidget(url_lbl)
        f.addLayout(url_row)
        self._sett_dc_url_edit = QLineEdit()
        self._sett_dc_url_edit.setPlaceholderText("https://discord.com/api/webhooks/...")
        self._sett_dc_url_edit.setText(dc.get("url", ""))
        self._sett_dc_url_edit.editingFinished.connect(self._on_dc_save)
        f.addWidget(self._sett_dc_url_edit)

        f.addWidget(_sec("PINGS"))
        ping_row = QHBoxLayout()
        ping_row.setContentsMargins(0, 0, 0, 0)
        self._sett_dc_ping_chk = QCheckBox("Ping user on alerts")
        self._sett_dc_ping_chk.setChecked(dc.get("enable_ping", False))
        self._sett_dc_ping_chk.setToolTip("Mention a Discord user ID in alert messages.")
        self._sett_dc_ping_chk.stateChanged.connect(self._on_dc_save)
        ping_row.addWidget(self._sett_dc_ping_chk)
        self._sett_dc_pingid_edit = QLineEdit()
        self._sett_dc_pingid_edit.setPlaceholderText("User ID (e.g. 123456789)")
        self._sett_dc_pingid_edit.setText(dc.get("ping_user_id", ""))
        self._sett_dc_pingid_edit.setFixedWidth(160)
        self._sett_dc_pingid_edit.editingFinished.connect(self._on_dc_save)
        ping_row.addWidget(self._sett_dc_pingid_edit)
        f.addLayout(ping_row)

        self._sett_dc_pingerr_chk = QCheckBox("Ping only on [ERROR]")
        self._sett_dc_pingerr_chk.setChecked(dc.get("ping_on_error", True))
        self._sett_dc_pingerr_chk.setToolTip(
            "Only mention the user for [ERROR] messages, not every event."
        )
        self._sett_dc_pingerr_chk.stateChanged.connect(self._on_dc_save)
        f.addLayout(_sub_indent(self._sett_dc_pingerr_chk))

        f.addWidget(_sec("SCREENSHOTS"))
        ss_row = QHBoxLayout()
        ss_row.setContentsMargins(0, 0, 0, 0)
        self._sett_dc_ss_chk = QCheckBox("Screenshot every")
        self._sett_dc_ss_chk.setChecked(dc.get("screenshot_enabled", False))
        self._sett_dc_ss_chk.setToolTip(
            "Periodically capture a screenshot and upload it to Discord via the webhook."
        )
        self._sett_dc_ss_chk.stateChanged.connect(self._on_dc_save)
        ss_row.addWidget(self._sett_dc_ss_chk)
        self._sett_dc_ss_spin = QSpinBox()
        self._sett_dc_ss_spin.setRange(1, 1440)
        self._sett_dc_ss_spin.setValue(int(dc.get("screenshot_interval_minutes", 60)))
        self._sett_dc_ss_spin.setSuffix(" min")
        self._sett_dc_ss_spin.setFixedWidth(80)
        self._sett_dc_ss_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._sett_dc_ss_spin.valueChanged.connect(self._on_dc_save)
        ss_row.addWidget(self._sett_dc_ss_spin)
        ss_row.addStretch(1)
        f.addLayout(ss_row)

        f.addWidget(_sec("LOG FILTERS"))
        _filter_lbl = QLabel(
            "Choose which event types are forwarded to Discord."
        )
        _filter_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        _filter_lbl.setWordWrap(True)
        f.addWidget(_filter_lbl)

        _log_fields = [
            ("log_errors", "Log [ERROR]", True),
            ("log_success", "Log [SUCCESS]", True),
            ("log_warnings", "Log [WARNING]", True),
            ("log_info", "Log [INFO]", False),
            ("log_auto_rejoin", "Log Auto-Rejoin events", True),
            ("log_auto_rejoin_console", "Log Auto-Rejoin console", False),
        ]
        self._sett_dc_log_chks: dict[str, QCheckBox] = {}
        for key, label, default in _log_fields:
            cb = QCheckBox(label)
            cb.setChecked(dc.get(key, default))
            cb.stateChanged.connect(self._on_dc_save)
            f.addWidget(cb)
            self._sett_dc_log_chks[key] = cb

        f.addWidget(_sec("ACTIONS"))
        _test_btn = QPushButton("Test Webhook")
        _test_btn.setToolTip(
            "Send a test embed to the configured webhook URL to verify it is working."
        )
        _test_btn.clicked.connect(self._on_dc_test)
        f.addWidget(_test_btn)

        f.addStretch(1)

        # Misc (Page 3)
        sa, f = _scrollable()
        content_stack.addWidget(sa)

        f.addWidget(_sec("BROWSER ENGINE"))
        _br_lbl = QLabel(
            "Supported browsers: Chrome, Firefox, Edge, and built-in Chromium. "
            "Brave and Opera GX users should select Chromium."
        )
        _br_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        _br_lbl.setWordWrap(True)
        f.addWidget(_br_lbl)

        _cur_br = S.get("browser_type", "chrome")
        _br_grp = QButtonGroup(sa)
        for br_key, br_label, br_tip in [
            ("chrome", "Google Chrome",
             "Use Google Chrome through Selenium. Google Chrome must be installed."),
            ("firefox", "Mozilla Firefox",
             "Use Mozilla Firefox through Selenium. Mozilla Firefox must be installed."),
            ("edge", "Microsoft Edge",
             "Use Microsoft Edge through Selenium. Microsoft Edge must be installed."),
            ("chromium", "Chromium",
             "Use the built-in Chromium and matching driver. Download it with the button below."),
        ]:
            rb = QRadioButton(br_label)
            rb.setChecked(br_key == _cur_br)
            rb.setToolTip(br_tip)
            _br_grp.addButton(rb)
            rb.toggled.connect(
                (lambda k: lambda checked: actions.save_ui_setting("browser_type", k) if checked else None)(br_key)
            )
            f.addWidget(rb)

        _chromium_installed = bool(chromium_mod.validate_chromium())
        self._sett_chromium_btn = QPushButton(
            "Reinstall Chromium" if _chromium_installed else "Download Chromium"
        )
        self._sett_chromium_btn.setEnabled(True)
        self._sett_chromium_btn.setToolTip(
            "Download the latest portable Chromium and matching ChromeDriver.\n"
            "Reinstalling replaces the current Chromium folder with a clean copy."
        )
        self._sett_chromium_btn.clicked.connect(self._on_sett_dl_chromium)
        f.addLayout(_sub_indent(self._sett_chromium_btn))

        f.addWidget(_sec("ENCRYPTION"))
        _enc_btn = QPushButton("Switch Encryption Method")
        _enc_btn.setToolTip(
            "Change between hardware-based and password-based encryption.\n"
            "You will need to re-import your accounts after switching."
        )
        _enc_btn.clicked.connect(self._on_sett_switch_encryption)
        f.addWidget(_enc_btn)

        f.addWidget(_sec("DATA"))
        _wipe_btn = QPushButton("Wipe All Data")
        _wipe_btn.setToolTip(
            "Permanently delete all saved accounts, settings, and cached data.\n"
            "This action cannot be undone."
        )
        _wipe_btn.setStyleSheet(
            "QPushButton { color: #EF5350; border-color: #5A2A2A; }"
            "QPushButton:hover { background: #3A1A1A; color: #FF6B6B; }"
        )
        _wipe_btn.clicked.connect(self._on_sett_wipe_data)
        f.addWidget(_wipe_btn)

        f.addStretch(1)

        # Developer (Page 4)
        sa, f = _scrollable()
        content_stack.addWidget(sa)

        f.addWidget(_sec("DEVELOPER"))
        self._sett_devmode_chk = _chk(
            "developer_mode", "Developer Mode",
            "Unlock developer-only features.\n"
            "Enables Copy Cookie and WebSocket controls.",
            on_change=self._on_sett_developer_mode,
        )
        f.addWidget(self._sett_devmode_chk)

        self._sett_copycookie_chk = _chk(
            "enable_copy_cookie", "Enable Copy Cookie Button",
            "Show a Copy Cookie button on each account entry.\n"
            "WARNING: cookies grant full account access, never share them.",
        )
        f.addWidget(self._sett_copycookie_chk)
        _dev_on = S.get("developer_mode", False)
        self._sett_copycookie_chk.setEnabled(_dev_on)

        f.addWidget(_sec("WEBSOCKET SERVER"))
        self._sett_ws_chk = _chk(
            "websocket_enabled", "Enable WebSocket Server",
            "Start a local WebSocket server so external scripts can\n"
            "query account data and trigger actions.",
            on_change=self._on_sett_ws_changed,
        )
        f.addWidget(self._sett_ws_chk)
        self._sett_ws_chk.setEnabled(_dev_on)

        ws_port_row = QHBoxLayout()
        ws_port_row.setContentsMargins(20, 0, 0, 0)
        _wsp_lbl = QLabel("Port")
        _wsp_lbl.setToolTip("TCP port for the WebSocket server (default: 7963).")
        ws_port_row.addWidget(_wsp_lbl)
        ws_port_row.addStretch(1)
        self._sett_ws_port = QSpinBox()
        self._sett_ws_port.setRange(1024, 65535)
        self._sett_ws_port.setValue(int(S.get("websocket_port", 7963)))
        self._sett_ws_port.setFixedWidth(80)
        self._sett_ws_port.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._sett_ws_port.valueChanged.connect(
            lambda v: actions.save_ui_setting("websocket_port", v)
        )
        ws_port_row.addWidget(self._sett_ws_port)
        f.addLayout(ws_port_row)

        self._sett_ws_pw_chk = _chk(
            "websocket_require_password", "Require Password",
            "Clients must supply a password to connect to the WebSocket server.",
            on_change=self._on_sett_ws_password_required,
        )
        f.addLayout(_sub_indent(self._sett_ws_pw_chk))

        self._sett_ws_saved_password = str(
            self.manager.get_secure_setting("websocket_password", "") or ""
        )
        ws_password_row = QHBoxLayout()
        ws_password_row.setContentsMargins(20, 0, 0, 0)
        ws_password_label = QLabel("Password")
        ws_password_row.addWidget(ws_password_label)
        ws_password_row.addStretch(1)
        self._sett_ws_password_edit = QLineEdit()
        self._sett_ws_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._sett_ws_password_edit.setMaxLength(256)
        self._sett_ws_password_edit.setFixedWidth(180)
        self._sett_ws_password_edit.setText(self._sett_ws_saved_password)
        self._sett_ws_password_edit.setToolTip(
            "Password used by AUTH <password> | <command>."
        )
        ws_password_row.addWidget(self._sett_ws_password_edit)
        self._sett_ws_password_set_btn = QPushButton("Set")
        self._sett_ws_password_set_btn.setFixedWidth(60)
        self._sett_ws_password_set_btn.clicked.connect(
            self._on_sett_ws_password_save
        )
        ws_password_row.addWidget(self._sett_ws_password_set_btn)
        f.addLayout(ws_password_row)

        self._update_ws_password_controls()

        ws_docs_btn = QPushButton("Read Documentation")
        ws_docs_btn.clicked.connect(
            lambda: webbrowser.open("https://evanovars-roblox-account-manager.gitbook.io/evanovars-ram")
        )
        f.addWidget(ws_docs_btn)

        f.addStretch(1)

        return panel

    def _on_sett_topmost(self, enabled: bool):
        current = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if current == enabled:
            return
        restore_window_grid = self._window_grid_hotkey_registered
        if restore_window_grid:
            self._unregister_window_grid_hotkey()
        self.hide()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()
        if restore_window_grid:
            QTimer.singleShot(
                0,
                lambda: self._apply_window_grid_hotkey(show_error=False),
            )
        print(f"[INFO] Always on Top {'enabled' if enabled else 'disabled'}")

    def _on_sett_multi_select(self, enabled: bool):
        if hasattr(self, "_account_list") and self._account_list:
            mode = (QAbstractItemView.SelectionMode.ExtendedSelection
                    if enabled else
                    QAbstractItemView.SelectionMode.SingleSelection)
            self._account_list.setSelectionMode(mode)

    def _on_sett_start_menu(self, state: int, path: str):
        enabled = (state == Qt.CheckState.Checked.value)
        if enabled:
            try:
                if getattr(sys, "frozen", False):
                    exe = sys.executable
                else:
                    exe = os.path.abspath(sys.argv[0])
                ps = (
                    f'$s=New-Object -comObject WScript.Shell;'
                    f'$l=$s.CreateShortcut("{path}");'
                    f'$l.TargetPath="{exe}";'
                    f'$l.WorkingDirectory="{os.path.dirname(exe)}";'
                    f'$l.Description="Roblox Account Manager";$l.Save()'
                )
                subprocess.run(["powershell", "-Command", ps],
                               capture_output=True, creationflags=0x08000000)
                print("[INFO] Start Menu shortcut created")
            except Exception as e:
                print(f"[ERROR] Failed to create shortcut: {e}")
                self._sett_startmenu_chk.setChecked(False)
        else:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    print("[INFO] Start Menu shortcut removed")
            except Exception as e:
                print(f"[ERROR] Failed to remove shortcut: {e}")

    def _set_startup_checkbox(self, enabled: bool) -> None:
        if not hasattr(self, "_sett_startup_chk"):
            return
        self._sett_startup_chk.blockSignals(True)
        self._sett_startup_chk.setChecked(enabled)
        self._sett_startup_chk.blockSignals(False)

    def _on_sett_startup(self, state: int) -> None:
        enabled = state == Qt.CheckState.Checked.value
        result = (
            windows_startup_mod.enable_startup()
            if enabled
            else windows_startup_mod.disable_startup()
        )
        if result:
            actions.save_ui_setting("start_with_windows", enabled)
            print(f"[INFO] Start with Windows {'enabled' if enabled else 'disabled'}")
            return

        self._set_startup_checkbox(not enabled)
        actions.save_ui_setting("start_with_windows", not enabled)
        self._show_operation_error(result)

    def _on_sett_boost_ram(self, enabled: bool):
        if hasattr(self, "_sett_ram_spin"):
            self._sett_ram_spin.setEnabled(enabled)
        if enabled:
            self._start_ram_boost()
        else:
            self._stop_ram_boost()

    def _on_sett_rename_windows(self, enabled: bool):
        if enabled:
            self._start_rename_windows()
        else:
            self._stop_rename_windows()

    def _on_sett_presence_indicator(self, enabled: bool):
        if enabled:
            self._start_presence_scanner()
        else:
            self._stop_presence_scanner()
        self._refresh_account_list()

    def _on_sett_installer_fix(self, enabled: bool):
        try:
            if enabled:
                RobloxAPI.quarantine_installers()
            else:
                RobloxAPI.restore_installers()
        except Exception as e:
            print(f"[ERROR] Roblox Installer Fix toggle failed: {e}")

    def _load_roblox_settings(
        self,
        show_error: bool = True,
        reload_from_roblox: bool = False,
    ):
        if self._roblox_settings_loading or self._roblox_settings_applying:
            return
        self._roblox_settings_loading = True
        self._roblox_settings_show_load_error = show_error
        self._roblox_settings_reload_btn.setEnabled(False)
        self._roblox_settings_apply_btn.setEnabled(False)
        self._roblox_settings_auto_apply_chk.setEnabled(False)
        if reload_from_roblox:
            roblox_settings_mod.reload_local_profile_from_roblox_async(
                self._bridge.roblox_settings_loaded.emit
            )
        else:
            roblox_settings_mod.load_local_profile_async(
                self._bridge.roblox_settings_loaded.emit
            )

    def _on_roblox_settings_loaded(self, result: OperationResult):
        self._roblox_settings_loading = False
        self._roblox_settings_reload_btn.setEnabled(True)
        if not result:
            self._roblox_settings_records.clear()
            self._roblox_settings_pending.clear()
            self._roblox_settings_file_hash = ""
            self._roblox_settings_tree.clear()
            self._roblox_settings_selected_label.setText("None")
            self._roblox_settings_type_label.setText("None")
            self._roblox_settings_value_stack.setEnabled(False)
            self._set_roblox_managed_controls_enabled(False)
            self._roblox_settings_auto_apply_chk.setEnabled(False)
            self._roblox_settings_startup_reload = False
            self._update_roblox_settings_apply_state()
            if self._roblox_settings_show_load_error:
                self._show_operation_error(result)
            return

        data = result.data or {}
        self._roblox_settings_file_hash = str(data.get("file_hash", ""))
        self._roblox_settings_records = {
            str(record["key"]): dict(record)
            for record in data.get("settings", [])
        }
        self._roblox_settings_pending.clear()
        self._roblox_settings_config = roblox_settings_mod.get_customization_config(
            settings=actions.load_ui_settings(),
            records=self._roblox_settings_records,
        )
        self._roblox_settings_pending_config = dict(self._roblox_settings_config)
        self._populate_roblox_settings_tree()
        self._sync_quick_controls_from_pending()
        self._set_roblox_managed_controls_enabled(True)
        self._roblox_settings_auto_apply_chk.blockSignals(True)
        self._roblox_settings_auto_apply_chk.setEnabled(True)
        self._roblox_settings_auto_apply_chk.setChecked(
            bool(self._roblox_settings_config.get("auto_apply", False))
        )
        self._roblox_settings_auto_apply_chk.blockSignals(False)
        self._update_roblox_settings_apply_state()
        if self._roblox_settings_startup_reload:
            self._roblox_settings_startup_reload = False
            if (
                bool(self._roblox_settings_config.get("auto_apply", False))
                or bool(self._roblox_settings_config.get("lock_owned", False))
                or any(
                bool(self._roblox_settings_config.get(key, False))
                for key in (
                    "framerate_enabled",
                    "master_volume_enabled",
                    "start_quality_enabled",
                )
                )
            ):
                QTimer.singleShot(0, self._start_roblox_auto_apply)

    def _populate_roblox_settings_tree(self):
        selected_key = self._current_roblox_setting_key()
        self._roblox_settings_tree.clear()
        search_text = self._roblox_settings_search.text().strip().lower()
        selected_item = None
        for key, record in sorted(
            self._roblox_settings_records.items(),
            key=lambda item: item[1].get("name", item[0]).lower(),
        ):
            value = str(record.get("value", ""))
            searchable = " ".join((
                key,
                str(record.get("name", "")),
                str(record.get("xml_type", "")),
                value,
            )).lower()
            if search_text and search_text not in searchable:
                continue
            setting_name = str(record.get("name", key))
            if bool(record.get("pending", False)):
                setting_name = f"{setting_name} *"
            item = QTreeWidgetItem([
                setting_name,
                str(record.get("xml_type", "")),
                value,
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            self._roblox_settings_tree.addTopLevelItem(item)
            if key == selected_key:
                selected_item = item

        if self._roblox_settings_tree.topLevelItemCount() == 0:
            empty_item = QTreeWidgetItem(["No settings found", "", ""])
            empty_item.setFlags(
                empty_item.flags() & ~Qt.ItemFlag.ItemIsEnabled
            )
            self._roblox_settings_tree.addTopLevelItem(empty_item)
            self._on_roblox_setting_selected()
        elif selected_item is not None:
            self._roblox_settings_tree.setCurrentItem(selected_item)
        else:
            self._roblox_settings_tree.setCurrentItem(
                self._roblox_settings_tree.topLevelItem(0)
            )

    def _filter_roblox_settings(self, _text: str):
        self._populate_roblox_settings_tree()

    def _current_roblox_setting_key(self) -> str:
        item = self._roblox_settings_tree.currentItem()
        if item is None:
            return ""
        return str(item.data(0, Qt.ItemDataRole.UserRole) or "")

    def _on_roblox_setting_selected(self):
        key = self._current_roblox_setting_key()
        record = self._roblox_settings_records.get(key)
        if record is None:
            self._roblox_settings_selected_label.setText("None")
            self._roblox_settings_type_label.setText("None")
            self._roblox_settings_state_label.setText("Ready")
            self._roblox_settings_value_stack.setEnabled(False)
            return

        value = str(record.get("value", ""))
        xml_type = str(record.get("xml_type", "string"))
        self._roblox_settings_editor_active = True
        self._roblox_settings_value_stack.setEnabled(
            bool(record.get("editable", True))
        )
        self._roblox_settings_selected_label.setText(key)
        self._roblox_settings_type_label.setText(xml_type)
        if bool(record.get("pending", False)):
            self._roblox_settings_state_label.setText("Pending")
        else:
            self._roblox_settings_state_label.setText("Ready")
        if xml_type == "bool":
            self._roblox_settings_value_stack.setCurrentIndex(1)
            checked = value.strip().lower() == "true"
            self._roblox_settings_bool_edit.setChecked(checked)
            self._roblox_settings_bool_edit.setText("true" if checked else "false")
        else:
            self._roblox_settings_value_stack.setCurrentIndex(0)
            self._roblox_settings_value_edit.setText(value)
        self._roblox_settings_editor_active = False

    def _on_roblox_setting_text_finished(self):
        if not self._roblox_settings_editor_active:
            self._stage_roblox_setting_value(
                self._roblox_settings_value_edit.text()
            )

    def _on_roblox_setting_bool_changed(self, state: int):
        checked = state == Qt.CheckState.Checked.value
        self._roblox_settings_bool_edit.setText("true" if checked else "false")
        if not self._roblox_settings_editor_active:
            self._stage_roblox_setting_value("true" if checked else "false")

    def _stage_roblox_setting_value(self, value: str):
        key = self._current_roblox_setting_key()
        record = self._roblox_settings_records.get(key)
        if record is None or not bool(record.get("editable", True)):
            return
        save_result = roblox_settings_mod.save_advanced_setting(key, str(value))
        if not save_result:
            self._roblox_settings_editor_active = True
            if str(record.get("xml_type", "string")) == "bool":
                checked = str(record.get("value", "")).lower() == "true"
                self._roblox_settings_bool_edit.setChecked(checked)
                self._roblox_settings_bool_edit.setText(
                    "true" if checked else "false"
                )
            else:
                self._roblox_settings_value_edit.setText(
                    str(record.get("value", ""))
                )
            self._roblox_settings_editor_active = False
            self._show_operation_error(save_result)
            return
        normalized = str((save_result.data or {}).get("settings", {}).get(key, {}).get("value", value))
        record["value"] = normalized
        record["pending"] = normalized != str(record.get("source_value", ""))
        self._roblox_settings_config = roblox_settings_mod.get_customization_config(
            records=self._roblox_settings_records
        )
        self._roblox_settings_pending_config = dict(self._roblox_settings_config)
        self._sync_quick_controls_from_pending()
        self._refresh_roblox_setting_row(key)
        self._update_roblox_settings_apply_state()
        self._on_roblox_setting_selected()

    def _refresh_roblox_setting_row(self, key: str):
        for index in range(self._roblox_settings_tree.topLevelItemCount()):
            item = self._roblox_settings_tree.topLevelItem(index)
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                record = self._roblox_settings_records.get(key, {})
                setting_name = str(record.get("name", key))
                if bool(record.get("pending", False)):
                    setting_name = f"{setting_name} *"
                item.setText(
                    2,
                    str(record.get("value", "")),
                )
                item.setText(
                    0,
                    setting_name,
                )
                break

    def _update_roblox_settings_apply_state(self):
        enabled = any(
            bool(record.get("pending", False))
            for record in self._roblox_settings_records.values()
        )
        self._roblox_settings_apply_btn.setEnabled(
            enabled
            and bool(self._roblox_settings_records)
            and not self._roblox_settings_loading
            and not self._roblox_settings_applying
        )

    def _sync_quick_controls_from_pending(self):
        config = self._roblox_settings_pending_config
        framerate_record = self._roblox_settings_records.get("FramerateCap")
        if framerate_record is not None:
            try:
                framerate = int(config.get(
                    "framerate_value",
                    framerate_record.get("value", 60),
                ))
                self._sett_fps_spin.blockSignals(True)
                self._sett_fps_spin.setValue(max(-1, min(999, framerate)))
                self._sett_fps_spin.blockSignals(False)
            except (TypeError, ValueError):
                pass

        volume_record = self._roblox_settings_records.get("MasterVolume")
        if volume_record is not None:
            try:
                volume = float(config.get(
                    "master_volume_value",
                    volume_record.get("value", 1),
                ))
                volume = max(0.0, min(1.0, volume))
                self._roblox_master_volume_slider.blockSignals(True)
                self._roblox_master_volume_slider.setValue(round(volume * 10))
                self._roblox_master_volume_slider.blockSignals(False)
                self._roblox_master_volume_label.setText(f"{volume:.1f}")
            except (TypeError, ValueError):
                pass

        quality_record = self._roblox_settings_records.get("SavedQualityLevel")
        if quality_record is not None:
            try:
                quality = int(config.get(
                    "start_quality_value",
                    quality_record.get("value", 0),
                ))
                quality = max(0, min(10, quality))
                self._roblox_start_quality_slider.blockSignals(True)
                self._roblox_start_quality_slider.setValue(quality)
                self._roblox_start_quality_slider.blockSignals(False)
                self._roblox_start_quality_label.setText(str(quality))
            except (TypeError, ValueError):
                pass

    def _set_roblox_managed_controls_enabled(self, file_available: bool):
        records = self._roblox_settings_records
        managed_controls = (
            ("FramerateCap", "framerate_enabled", self._sett_framerate_chk, self._sett_fps_spin),
            ("MasterVolume", "master_volume_enabled", self._sett_master_volume_chk, self._roblox_master_volume_slider),
            ("SavedQualityLevel", "start_quality_enabled", self._sett_start_quality_chk, self._roblox_start_quality_slider),
        )
        for xml_key, enabled_key, checkbox, value_control in managed_controls:
            exists = file_available and xml_key in records
            checkbox.blockSignals(True)
            checkbox.setEnabled(exists)
            checkbox.setChecked(
                exists
                and bool(self._roblox_settings_pending_config.get(enabled_key, False))
            )
            checkbox.blockSignals(False)
            value_control.setEnabled(
                exists and bool(self._roblox_settings_pending_config.get(enabled_key, False))
            )

    def _on_roblox_managed_toggle(self, name: str, enabled: bool):
        enabled_fields = {
            "framerate": ("framerate_enabled", "FramerateCap"),
            "master_volume": ("master_volume_enabled", "MasterVolume"),
            "start_quality": ("start_quality_enabled", "SavedQualityLevel"),
        }
        field_data = enabled_fields.get(name)
        if field_data is None or self._roblox_settings_loading:
            return
        _enabled_key, xml_key = field_data
        record = self._roblox_settings_records.get(xml_key)
        if record is None:
            return
        save_result = roblox_settings_mod.save_basic_setting(
            xml_key,
            enabled=enabled,
        )
        if not save_result:
            checkbox = {
                "framerate": self._sett_framerate_chk,
                "master_volume": self._sett_master_volume_chk,
                "start_quality": self._sett_start_quality_chk,
            }[name]
            checkbox.blockSignals(True)
            checkbox.setChecked(not enabled)
            checkbox.blockSignals(False)
            self._show_operation_error(save_result)
            return
        record["basic_enabled"] = bool(enabled)
        self._roblox_settings_config = roblox_settings_mod.get_customization_config(
            records=self._roblox_settings_records
        )
        self._roblox_settings_pending_config = dict(self._roblox_settings_config)
        self._set_roblox_managed_controls_enabled(True)
        self._on_roblox_setting_selected()
        self._refresh_roblox_setting_row(xml_key)
        self._update_roblox_settings_apply_state()

    def _on_sett_framerate_value(self, value: int):
        if self._roblox_settings_loading:
            return
        record = self._roblox_settings_records.get("FramerateCap")
        if record is None:
            return
        self._save_roblox_local_value("FramerateCap", str(value))

    def _on_master_volume_changed(self, value: int):
        volume = max(0, min(10, int(value))) / 10
        self._roblox_master_volume_label.setText(f"{volume:.1f}")
        if not self._roblox_settings_loading:
            self._save_roblox_local_value("MasterVolume", f"{volume:.1f}")

    def _on_start_quality_changed(self, value: int):
        self._roblox_start_quality_label.setText(str(value))
        if self._roblox_settings_loading:
            return
        self._save_roblox_local_value("SavedQualityLevel", str(value))

    def _save_roblox_local_value(self, key: str, value: str):
        result = roblox_settings_mod.save_basic_setting(
            key,
            value=value,
        )
        if not result:
            self._sync_quick_controls_from_pending()
            self._show_operation_error(result)
            return
        record = self._roblox_settings_records.get(key)
        self._roblox_settings_config = roblox_settings_mod.get_customization_config(
            records=self._roblox_settings_records
        )
        self._roblox_settings_pending_config = dict(self._roblox_settings_config)
        if record is not None:
            record["basic_enabled"] = bool(self._roblox_settings_config.get({
                "FramerateCap": "framerate_enabled",
                "MasterVolume": "master_volume_enabled",
                "SavedQualityLevel": "start_quality_enabled",
            }[key], False))
        self._set_roblox_managed_controls_enabled(True)
        self._update_roblox_settings_apply_state()

    def _reload_roblox_settings(self):
        self._load_roblox_settings(
            show_error=True,
            reload_from_roblox=True,
        )

    def _apply_roblox_settings(self):
        if self._roblox_settings_applying:
            return
        if not any(
            bool(record.get("pending", False))
            for record in self._roblox_settings_records.values()
        ):
            return
        self._roblox_settings_applying = True
        self._roblox_settings_apply_btn.setEnabled(False)
        self._roblox_settings_reload_btn.setEnabled(False)
        roblox_settings_mod.apply_local_profile_async(
            self._bridge.roblox_settings_applied.emit
        )

    def _on_roblox_settings_applied(self, result: OperationResult):
        self._roblox_settings_applying = False
        self._roblox_settings_reload_btn.setEnabled(True)
        if not result:
            self._update_roblox_settings_apply_state()
            self._show_operation_error(result)
            return
        data = result.data or {}
        self._roblox_settings_file_hash = str(data.get("file_hash", ""))
        self._roblox_settings_records = {
            str(record["key"]): dict(record)
            for record in data.get("settings", [])
        }
        self._roblox_settings_pending.clear()
        self._roblox_settings_config = roblox_settings_mod.get_customization_config(
            records=self._roblox_settings_records
        )
        self._roblox_settings_pending_config = dict(self._roblox_settings_config)
        self._populate_roblox_settings_tree()
        self._sync_quick_controls_from_pending()
        self._set_roblox_managed_controls_enabled(True)
        self._roblox_settings_auto_apply_chk.blockSignals(True)
        self._roblox_settings_auto_apply_chk.setChecked(
            bool(self._roblox_settings_config.get("auto_apply", False))
        )
        self._roblox_settings_auto_apply_chk.blockSignals(False)
        self._update_roblox_settings_apply_state()

    def _on_roblox_advanced_auto_apply_toggle(self, state: int):
        enabled = state == Qt.CheckState.Checked.value
        result = roblox_settings_mod.save_advanced_auto_apply(enabled)
        if not result:
            self._roblox_settings_auto_apply_chk.blockSignals(True)
            self._roblox_settings_auto_apply_chk.setChecked(not enabled)
            self._roblox_settings_auto_apply_chk.blockSignals(False)
            self._show_operation_error(result)
            return
        self._roblox_settings_config = roblox_settings_mod.get_customization_config(
            records=self._roblox_settings_records
        )
        self._roblox_settings_pending_config = dict(
            self._roblox_settings_config
        )

    def _start_roblox_auto_apply(self):
        if self._roblox_settings_auto_applying:
            return
        self._roblox_settings_auto_applying = True
        roblox_settings_mod.apply_saved_customizations_async(
            None,
            self._bridge.roblox_settings_auto_applied.emit,
        )

    def _on_roblox_settings_auto_applied(self, result: OperationResult):
        self._roblox_settings_auto_applying = False
        if not result:
            print(
                f"[ERROR] Roblox settings Auto Apply failed: "
                f"{result.code} {result.message}"
            )
            self._show_operation_error(result)
            return
        if 4 not in self._built_pages:
            return
        data = result.data or {}
        self._roblox_settings_file_hash = str(data.get("file_hash", ""))
        self._roblox_settings_records = {
            str(record["key"]): dict(record)
            for record in data.get("settings", [])
        }
        self._roblox_settings_config = roblox_settings_mod.get_customization_config(
            records=self._roblox_settings_records
        )
        self._roblox_settings_pending_config = dict(
            self._roblox_settings_config
        )
        self._populate_roblox_settings_tree()
        self._sync_quick_controls_from_pending()
        self._set_roblox_managed_controls_enabled(True)
        self._roblox_settings_auto_apply_chk.blockSignals(True)
        self._roblox_settings_auto_apply_chk.setChecked(
            bool(self._roblox_settings_config.get("auto_apply", False))
        )
        self._roblox_settings_auto_apply_chk.blockSignals(False)
        self._update_roblox_settings_apply_state()

    def _unregister_window_grid_hotkey(self) -> None:
        if self._window_grid_hotkey_registered:
            window_grid_mod.unregister_hotkey(
                self._window_grid_hotkey_hwnd
            )
        self._window_grid_hotkey_registered = False
        self._window_grid_hotkey_hwnd = 0

    def _apply_window_grid_hotkey(self, show_error: bool = True) -> bool:
        self._unregister_window_grid_hotkey()
        settings = actions.load_ui_settings()
        if not settings.get("window_grid_enabled", False):
            return True

        sequence = str(
            settings.get(
                "window_grid_keybind",
                window_grid_mod.DEFAULT_HOTKEY,
            )
            or window_grid_mod.DEFAULT_HOTKEY
        )
        window_handle = int(self.winId())
        result = window_grid_mod.register_hotkey(window_handle, sequence)
        if result:
            self._window_grid_hotkey_registered = True
            self._window_grid_hotkey_hwnd = window_handle
            print(f"[Window Grid] Keybind enabled: {sequence}")
            return True

        print(f"[Window Grid] {result.code}: {result.message}")
        if result.code == "WINDOW_GRID_KEYBIND_INVALID":
            invalid_result = result
            default_sequence = window_grid_mod.DEFAULT_HOTKEY
            actions.save_ui_setting(
                "window_grid_keybind",
                default_sequence,
            )
            if hasattr(self, "_sett_window_grid_key_btn"):
                self._sett_window_grid_key_btn.set_sequence(
                    default_sequence
                )

            result = window_grid_mod.register_hotkey(
                window_handle,
                default_sequence,
            )
            if result:
                self._window_grid_hotkey_registered = True
                self._window_grid_hotkey_hwnd = window_handle
                print(
                    f"[Window Grid] Invalid keybind reset to "
                    f"{default_sequence}."
                )
                if show_error:
                    self._show_operation_error(invalid_result)
                return True

        actions.save_ui_setting("window_grid_enabled", False)
        if hasattr(self, "_sett_window_grid_chk"):
            self._sett_window_grid_chk.blockSignals(True)
            self._sett_window_grid_chk.setChecked(False)
            self._sett_window_grid_chk.blockSignals(False)
        if hasattr(self, "_sett_window_grid_key_btn"):
            self._sett_window_grid_key_btn.setEnabled(False)
        if show_error:
            self._show_operation_error(result)
        return False

    def _on_sett_window_grid(self, enabled: bool) -> None:
        if hasattr(self, "_sett_window_grid_key_btn"):
            self._sett_window_grid_key_btn.setEnabled(enabled)
        if enabled:
            self._apply_window_grid_hotkey()
        else:
            self._unregister_window_grid_hotkey()
            print("[Window Grid] Keybind disabled.")

    def _restore_window_grid_hotkey_after_recording(self) -> None:
        if actions.load_ui_settings().get("window_grid_enabled", False):
            self._apply_window_grid_hotkey(show_error=False)

    def _on_sett_window_grid_keybind(self, sequence: str) -> None:
        actions.save_ui_setting("window_grid_keybind", sequence)
        if actions.load_ui_settings().get("window_grid_enabled", False):
            self._apply_window_grid_hotkey()

    _HM_HIDDEN_COLOR = "#4CAF50"
    _HM_SHOWN_COLOR = "#EF5350"

    def _on_sett_headless_manager(self, enabled: bool):
        if enabled:
            self._start_headless_manager()
        else:
            self._stop_headless_manager()

    def _start_headless_manager(self) -> None:
        if self._headless_manager is not None:
            return
        self._headless_manager = headless_manager_mod.HeadlessManager(
            on_update=lambda rows: self._bridge.headless_update.emit(rows),
        )
        self._headless_manager.start()
        print("[INFO] Headless Manager started.")

    def _stop_headless_manager(self) -> None:
        if self._headless_manager is None:
            return
        self._headless_manager.stop(restore=True)
        self._headless_manager = None
        self._headless_latest_rows = []
        if hasattr(self, "_headless_list"):
            self._refresh_headless_list([])
        print("[INFO] Headless Manager stopped, Roblox windows restored.")

    def _headless_selected_pid(self) -> int | None:
        item = self._headless_list.currentItem() if self._headless_list else None
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _headless_selected_pids(self) -> list[int]:
        if not self._headless_list:
            return []
        pids = []
        for it in self._headless_list.selectedItems():
            pid = it.data(Qt.ItemDataRole.UserRole)
            if pid:
                pids.append(pid)
        return pids

    def _on_headless_update(self, rows: list[dict]):
        if self._headless_manager is None:
            return
        self._headless_latest_rows = [dict(row) for row in rows]
        if hasattr(self, "_headless_list"):
            self._refresh_headless_list(rows)

    def _refresh_headless_list(self, rows: list[dict]):
        cur = self._headless_selected_pid()
        selected = set(self._headless_selected_pids())
        self._headless_list.clear()
        self._headless_avatar_labels.clear()
        self._headless_status_labels.clear()

        AV = avatars.AVATAR_SIZE
        ITEM_H = AV + 6

        if not rows:
            empty = QListWidgetItem(
                "No Roblox processes found." if self._headless_manager else
                "Headless Manager is disabled."
            )
            empty.setForeground(QColor(MUTED))
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._headless_list.addItem(empty)
            return

        for row_data in rows:
            pid = row_data["pid"]
            username = row_data["username"]
            hidden = row_data["hidden"]

            item = QListWidgetItem("")
            item.setSizeHint(QSize(0, ITEM_H))
            item.setData(Qt.ItemDataRole.UserRole, pid)

            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(4, 0, 6, 0)
            row_lay.setSpacing(6)

            av_lbl = QLabel()
            av_lbl.setFixedSize(AV, AV)
            av_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
            av_lbl.setPixmap(self._make_placeholder_pixmap(AV))
            row_lay.addWidget(av_lbl)
            self._headless_avatar_labels[pid] = av_lbl

            name_lbl = QLabel(username)
            name_lbl.setObjectName("accountName")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            row_lay.addWidget(name_lbl)

            sep = QLabel("|")
            sep.setObjectName("noteSep")
            sep.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            row_lay.addWidget(sep)

            status_str = "hidden" if hidden else "shown"
            status_color = self._HM_HIDDEN_COLOR if hidden else self._HM_SHOWN_COLOR
            status_lbl = QLabel(status_str)
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            status_lbl.setStyleSheet(f"color: {status_color}; font-size: 10px;")
            row_lay.addWidget(status_lbl)
            self._headless_status_labels[pid] = status_lbl

            row_lay.addStretch(1)

            row.setFixedHeight(ITEM_H)
            self._headless_list.addItem(item)
            self._headless_list.setItemWidget(item, row)

        for i in range(self._headless_list.count()):
            it = self._headless_list.item(i)
            pid = it.data(Qt.ItemDataRole.UserRole) if it else None
            if pid in selected:
                it.setSelected(True)
            if cur and pid == cur:
                self._headless_list.setCurrentItem(it)

        self._headless_load_avatars_async(rows)

    def _headless_load_avatars_async(self, rows: list[dict]):
        by_pid = {r["pid"]: r for r in rows}
        for pid, label in list(self._headless_avatar_labels.items()):
            row_data = by_pid.get(pid)
            if not row_data:
                continue
            user_id = row_data.get("user_id")
            username = row_data.get("username")
            if not user_id:
                continue
            avatars.fetch_avatar_async(
                user_id, username,
                on_done=lambda u, b, p=pid: self._bridge.headless_avatar_ready.emit(p, b),
            )

    def _on_headless_avatar_ready(self, pid: int, img_bytes: object):
        try:
            pix = self._make_circular_pixmap(bytes(img_bytes), avatars.AVATAR_SIZE)
            if pix.isNull():
                return
            lbl = self._headless_avatar_labels.get(pid)
            if lbl is not None:
                lbl.setPixmap(pix)
        except Exception:
            pass

    def _headless_set_status_label(self, pid: int, hidden: bool) -> None:
        lbl = self._headless_status_labels.get(pid)
        if lbl is None:
            return
        lbl.setText("hidden" if hidden else "shown")
        color = self._HM_HIDDEN_COLOR if hidden else self._HM_SHOWN_COLOR
        lbl.setStyleSheet(f"color: {color}; font-size: 10px;")

    def _headless_on_context_menu(self, pos):
        item = self._headless_list.itemAt(pos)
        if item is None or self._headless_manager is None:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        if not pid:
            return

        if pid not in self._headless_selected_pids():
            self._headless_list.setCurrentItem(item)

        pids = self._headless_selected_pids()
        any_shown = any(not self._headless_manager.is_hidden(p) for p in pids)
        any_hidden = any(self._headless_manager.is_hidden(p) for p in pids)

        menu = QMenu(self)
        act_hide = menu.addAction("Hide") if any_shown else None
        act_show = menu.addAction("Show") if any_hidden else None

        chosen = menu.exec(self._headless_list.mapToGlobal(pos))
        if act_hide and chosen == act_hide:
            for p in pids:
                self._headless_manager.set_hidden(p, True)
                self._headless_set_status_label(p, True)
        elif act_show and chosen == act_show:
            for p in pids:
                self._headless_manager.set_hidden(p, False)
                self._headless_set_status_label(p, False)

    def _start_update_check(self) -> None:
        if not actions.load_ui_settings().get("check_updates_on_startup", True):
            return
        def _worker():
            latest = updater_mod.check_latest_version()
            if latest and updater_mod.is_newer(APP_VERSION, latest):
                self._bridge.update_available.emit(latest)
        threading.Thread(target=_worker, daemon=True, name="UpdateCheck").start()

    def _on_update_available(self, latest_version: str) -> None:
        self._show_update_dialog(latest_version)

    def _show_update_dialog(self, latest_version: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Update Available")
        dlg.setFixedSize(440, 290)
        dlg.setStyleSheet(f"""
            QDialog   {{ background: {BG}; }}
            QLabel    {{ color: {TEXT}; background: transparent; }}
            QPushButton {{
                background: {INPUT}; color: {TEXT};
                border: 1px solid {LINE}; border-radius: 0;
                padding: 6px 14px; font-size: 12px;
            }}
            QPushButton:hover    {{ background: {SELECT}; border-color: #444; }}
            QPushButton:disabled {{ color: #666; }}
        """)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # Header
        hdr = QLabel("Update Available")
        hdr.setStyleSheet("font-size: 15px; font-weight: 700; color: #EDEDED;")
        lay.addWidget(hdr)

        # Version Info Card
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {PANEL}; border: none; }}")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 10, 14, 10)
        card_lay.setSpacing(4)
        lbl_cur = QLabel(f"Your version is outdated:  v{APP_VERSION}")
        lbl_cur.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        lbl_new = QLabel(f"Latest version:  v{latest_version}")
        lbl_new.setStyleSheet("color: #5DBBFF; font-size: 13px; font-weight: 600;")
        card_lay.addWidget(lbl_cur)
        card_lay.addWidget(lbl_new)
        lay.addWidget(card)

        # Progress download button (mimics chromium bar)
        dl_btn = QPushButton("Download Automatically")
        dl_btn.setFixedHeight(34)
        lay.addWidget(dl_btn)

        # Status label
        status_lbl = QLabel("")
        status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(status_lbl)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        manual_btn = QPushButton("Manual Download")
        ignore_btn = QPushButton("Ignore")
        btn_row.addWidget(manual_btn)
        btn_row.addWidget(ignore_btn)
        lay.addLayout(btn_row)

        # Helpers for the chromium-style progress bar
        def _set_progress(pct: int) -> None:
            pct = max(0, min(100, pct))
            dl_btn.setText(f"Downloading...  {pct}%")
            if pct == 0:
                dl_btn.setStyleSheet("")
            else:
                a = f"{pct / 100:.4f}"
                b = f"{min(pct / 100 + 0.001, 1.0):.4f}"
                dl_btn.setStyleSheet(
                    f"QPushButton {{"
                    f"  background: qlineargradient("
                    f"    x1:0, y1:0, x2:1, y2:0,"
                    f"    stop:0 #3A5A9A, stop:{a} #3A5A9A,"
                    f"    stop:{b} {INPUT}, stop:1 {INPUT}"
                    f"  );"
                    f"  color: {TEXT}; border: 1px solid {LINE}; border-radius: 4px;"
                    f"}}"
                )

        def _set_buttons_enabled(enabled: bool) -> None:
            dl_btn.setEnabled(enabled)
            manual_btn.setEnabled(enabled)
            ignore_btn.setEnabled(enabled)

        # Download signal connections
        def _on_progress(pct: int) -> None:
            _set_progress(pct)

        def _on_done(success: bool, err: str) -> None:
            try:
                self._bridge.update_progress.disconnect(_on_progress)
                self._bridge.update_done.disconnect(_on_done)
            except RuntimeError:
                pass
            if success:
                dl_btn.setText("Done! Closing...")
                dl_btn.setStyleSheet(
                    f"QPushButton {{ background: #1E4D1E; color: {TEXT}; "
                    f"border: 1px solid #2E6D2E; border-radius: 4px; }}"
                )
                status_lbl.setText("Update installed. The app will close now.")
                dlg.setEnabled(False)
                QTimer.singleShot(1500, self.close)
            else:
                _set_buttons_enabled(True)
                dl_btn.setText("Download Automatically")
                dl_btn.setStyleSheet("")
                status_lbl.setText(f"Download failed: {err}")

        # Button actions
        def _on_download_clicked() -> None:
            _set_buttons_enabled(False)
            _set_progress(0)
            status_lbl.setText("Starting download...")
            try:
                self._bridge.update_progress.disconnect()
            except RuntimeError:
                pass
            try:
                self._bridge.update_done.disconnect()
            except RuntimeError:
                pass
            self._bridge.update_progress.connect(_on_progress)
            self._bridge.update_done.connect(_on_done)
            updater_mod.download_update(
                on_progress=lambda p: self._bridge.update_progress.emit(p),
                on_done=lambda ok, e: self._bridge.update_done.emit(ok, e),
            )

        dl_btn.clicked.connect(_on_download_clicked)
        manual_btn.clicked.connect(lambda: (
            webbrowser.open(updater_mod.RELEASES_PAGE),
            dlg.accept(),
        ))
        ignore_btn.clicked.connect(dlg.accept)

        dlg.exec()

    # Cookie Validator
    def _start_cookie_validator(self) -> None:
        if self._cv_validator is not None:
            return
        self._cv_validator = self._cv_mod.CookieValidator(
            self.manager,
            on_result=lambda u, status: self._bridge.cookie_validated.emit(
                u,
                status,
            ),
            delay_sec=1.5,
        )
        self._cv_validator.start()

    def _on_cookie_validated(self, username: str, status: str) -> None:
        self._apply_cookie_status_to_row(
            username,
            status == self._cv_mod.INVALID,
        )

    def _apply_cookie_status_to_row(self, username: str, flagged: bool) -> None:
        badge = self._invalid_badges.get(username)
        if badge is None and flagged:
            container = self._account_avatar_containers.get(username)
            if container is not None:
                badge = self._create_invalid_badge(container)
                self._invalid_badges[username] = badge
        if badge is not None:
            badge.setVisible(flagged)
        name_label = self._account_name_labels.get(username)
        if name_label is not None:
            name_label.setStyleSheet(
                "color: #E8A020; font-style: italic;" if flagged else ""
            )
            name_label.setToolTip(
                "Cookie validation received repeated unauthorized responses.\n"
                "You can still try launching this account."
                if flagged else ""
            )
        row = self._account_rows.get(username)
        if row is not None:
            row.setStyleSheet(
                "QWidget { background: rgba(200, 50, 50, 0.06); }"
                if flagged else ""
            )

    def _is_account_invalid(self, username: str) -> bool:
        data = self.manager.accounts.get(username)
        return self._cv_mod.is_flagged(data) if isinstance(data, dict) else False

    def _guard_invalid(self, usernames: list[str]) -> bool:
        bad = [u for u in usernames if self._is_account_invalid(u)]
        if not bad:
            return True
        names = ", ".join(bad)
        reply = QMessageBox.question(
            self,
            "Cookie May Be Invalid",
            f"The following account(s) received repeated unauthorized "
            f"responses during cookie validation:\n\n  {names}\n\n"
            "Would you like to try launching anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _start_presence_scanner(self) -> None:
        if self._presence_scanner is not None:
            return
        self._presence_scanner = self._presence_mod.PresenceScanner(
            self.manager,
            on_update=lambda snapshot: self._bridge.presence_update.emit(snapshot),
            interval_sec=5,
        )
        self._presence_scanner.start()
        print("[INFO] Account Activity Monitor started.")

    def _stop_presence_scanner(self) -> None:
        if self._presence_scanner is None:
            self._online_usernames = set()
            self._activity_snapshot = {}
            self._update_presence_dots()
            self._update_activity_rows()
            return
        self._presence_scanner.stop()
        self._presence_scanner = None
        self._online_usernames = set()
        self._activity_snapshot = {}
        self._update_presence_dots()
        self._update_activity_rows()
        print("[INFO] Account Activity Monitor stopped.")

    def _on_presence_update(self, snapshot: object) -> None:
        if isinstance(snapshot, dict):
            self._activity_snapshot = {
                str(username): dict(metrics)
                for username, metrics in snapshot.items()
                if isinstance(metrics, dict)
            }
        else:
            self._activity_snapshot = {}
        self._online_usernames = set(self._activity_snapshot)
        self._update_presence_dots()
        self._update_activity_rows()

    def _update_presence_dots(self) -> None:
        for username, dot in self._presence_dots.items():
            dot.setVisible(username in self._online_usernames)

    def _update_activity_rows(self) -> None:
        for username, container in self._activity_widgets.items():
            metrics = self._activity_snapshot.get(username)
            if not metrics:
                container.setVisible(False)
                continue

            ram_mb = float(metrics.get("ram_mb", 0.0) or 0.0)
            cpu_percent = float(metrics.get("cpu_percent", 0.0) or 0.0)
            ram_text = (
                f"{ram_mb:.0f} MB"
                if metrics.get("ram_available", False)
                else "N/A"
            )
            cpu_text = (
                f"{cpu_percent:.1f}%"
                if metrics.get("cpu_available", False)
                else "N/A"
            )
            labels = self._activity_labels.get(username)
            if labels is not None:
                ram_label, cpu_label = labels
                if ram_label.text() != ram_text:
                    ram_label.setText(ram_text)
                if cpu_label.text() != cpu_text:
                    cpu_label.setText(cpu_text)
            container.setVisible(True)

    # RAM boost background worker
    def _start_ram_boost(self):
        if getattr(self, "_ram_boost_running", False):
            return
        self._ram_boost_running = True
        self._ram_boost_stop = False
        def _worker():
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            print("[INFO] RAM boost started")
            while not self._ram_boost_stop:
                try:
                    limit_mb = int(actions.load_ui_settings().get("optimize_roblox_ram_limit_mb", 750))
                    current_pids = set()
                    for proc in psutil.process_iter(["pid", "name"]):
                        if proc.info["name"] and proc.info["name"].lower() == "robloxplayerbeta.exe":
                            current_pids.add(proc.info["pid"])
                    for pid in current_pids:
                        try:
                            mem_mb = psutil.Process(pid).memory_info().rss / 1024 / 1024
                            if mem_mb >= limit_mb:
                                h = kernel32.OpenProcess(0x1F0FFF, False, pid)
                                if h:
                                    psapi.EmptyWorkingSet(h)
                                    kernel32.CloseHandle(h)
                                    print(f"[INFO] Trimmed RAM for Roblox PID {pid} ({mem_mb:.0f} MB)")
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[ERROR] RAM boost error: {e}")
                time.sleep(15)
            self._ram_boost_running = False
            print("[INFO] RAM boost stopped")
        threading.Thread(target=_worker, daemon=True, name="RamBoost").start()

    def _stop_ram_boost(self):
        self._ram_boost_stop = True

    # Rename Roblox Windows worker
    def _start_rename_windows(self):
        if self._window_renamer is not None:
            return
        self._window_renamer = window_renamer_mod.RobloxWindowRenamer(
            self.manager,
        )
        self._window_renamer.start()

    def _stop_rename_windows(self):
        renamer = self._window_renamer
        self._window_renamer = None
        if renamer is not None:
            renamer.stop()

    def _on_sett_browse_launcher(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Launcher", "", "Executables (*.exe);;All files (*)"
        )
        if path:
            self._sett_custom_launcher_edit.setText(path)

    def _on_sett_roblox_downloader_customizations(self, enabled: bool):
        if hasattr(self, "_sett_roblox_downloader_version_edit"):
            self._sett_roblox_downloader_version_edit.setEnabled(enabled)
        if hasattr(self, "_sett_roblox_downloader_location_edit"):
            self._sett_roblox_downloader_location_edit.setEnabled(enabled)
        if hasattr(self, "_sett_roblox_downloader_browse_btn"):
            self._sett_roblox_downloader_browse_btn.setEnabled(enabled)

    def _on_sett_browse_roblox_download_path(self):
        current_path = self._sett_roblox_downloader_location_edit.text().strip()
        if not current_path:
            current_path = roblox_downloader_mod.get_default_versions_path()
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Roblox Versions Folder",
            current_path,
        )
        if path:
            self._sett_roblox_downloader_location_edit.setText(path)

    def _on_sett_download_roblox(self):
        button = self._sett_roblox_downloader_btn
        customizations_enabled = (
            self._sett_roblox_downloader_custom_chk.isChecked()
        )
        version_value = self._sett_roblox_downloader_version_edit.text()
        location_path = self._sett_roblox_downloader_location_edit.text()

        button.setEnabled(False)
        button.setText("0%")
        self._sett_roblox_downloader_custom_chk.setEnabled(False)
        self._sett_roblox_downloader_version_edit.setEnabled(False)
        self._sett_roblox_downloader_location_edit.setEnabled(False)
        self._sett_roblox_downloader_browse_btn.setEnabled(False)

        def _worker():
            success, result_type, message = roblox_downloader_mod.download_roblox(
                version_value,
                location_path,
                customizations_enabled,
                progress_callback=(
                    lambda percent, text: self._bridge.roblox_download_progress.emit(
                        percent,
                        text,
                    )
                ),
            )
            self._bridge.roblox_download_done.emit(
                success,
                result_type,
                message,
            )

        threading.Thread(
            target=_worker,
            daemon=True,
            name="roblox-downloader",
        ).start()

    def _on_roblox_download_progress(self, percent: int, operation: str):
        if not hasattr(self, "_sett_roblox_downloader_btn"):
            return
        button = self._sett_roblox_downloader_btn
        filled = max(0, min(100, int(percent)))
        button.setText(f"{filled}%")
        button.setToolTip(operation)
        if filled == 0:
            button.setStyleSheet(
                f"QPushButton {{ background: {INPUT}; color: {TEXT}; "
                f"border: 1px solid {LINE}; border-radius: 0; "
                f"text-align: center; }}"
            )
            return

        stop_a = f"{filled / 100:.4f}"
        stop_b = f"{min(filled / 100 + 0.001, 1.0):.4f}"
        button.setStyleSheet(
            f"QPushButton {{"
            f"  background: qlineargradient("
            f"    x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 #3A5A9A,"
            f"    stop:{stop_a} #3A5A9A,"
            f"    stop:{stop_b} {INPUT},"
            f"    stop:1 {INPUT}"
            f"  );"
            f"  color: {TEXT}; border: 1px solid {LINE};"
            f"  border-radius: 0; text-align: center;"
            f"}}"
        )

    def _on_roblox_download_done(
        self,
        success: bool,
        result_type: str,
        message: str,
    ):
        if not hasattr(self, "_sett_roblox_downloader_btn"):
            return

        button = self._sett_roblox_downloader_btn
        button.setText("Download Latest Roblox")
        button.setEnabled(True)
        button.setToolTip(
            "Download and extract the selected WindowsPlayer deployment."
        )
        button.setStyleSheet(
            f"QPushButton {{ background: {INPUT}; color: {TEXT}; "
            f"border: 1px solid {LINE}; border-radius: 0; "
            f"text-align: center; }}"
            f"QPushButton:hover {{ background: {SELECT}; }}"
        )

        self._sett_roblox_downloader_custom_chk.setEnabled(True)
        customizations_enabled = (
            self._sett_roblox_downloader_custom_chk.isChecked()
        )
        self._sett_roblox_downloader_version_edit.setEnabled(
            customizations_enabled
        )
        self._sett_roblox_downloader_location_edit.setEnabled(
            customizations_enabled
        )
        self._sett_roblox_downloader_browse_btn.setEnabled(
            customizations_enabled
        )

        if success and result_type == "already_exists":
            QMessageBox.information(
                self,
                "Roblox Downloader",
                "The latest Roblox version has already been downloaded.\n\n"
                f"{message}",
            )
        elif success:
            QMessageBox.information(
                self,
                "Roblox Downloader",
                "Roblox was downloaded successfully.\n\n"
                f"Location:\n{message}",
            )
        else:
            QMessageBox.critical(
                self,
                "Roblox Downloader",
                f"Failed to download Roblox.\n\n{message}",
            )

    def _set_chromium_button_idle(self) -> None:
        if not hasattr(self, "_sett_chromium_btn"):
            return
        installed = bool(chromium_mod.validate_chromium())
        self._sett_chromium_btn.setText(
            "Reinstall Chromium" if installed else "Download Chromium"
        )
        self._sett_chromium_btn.setEnabled(True)
        self._sett_chromium_btn.setStyleSheet("")

    def _start_chromium_status_check(self) -> None:
        chromium_mod.check_chromium_status(
            lambda result: self._bridge.chromium_status.emit(result)
        )

    def _on_chromium_status(self, result) -> None:
        operation_result = ensure_result(
            result,
            failure_code="CHROMIUM_STATUS_FAILED",
            failure_title="Chromium Check Failed",
            failure_message="The latest Chromium version could not be checked.",
        )
        if not operation_result:
            print(
                f"[WARNING] Chromium status check failed: "
                f"{operation_result.code}: {operation_result.detail}"
            )
            return
        if self._chromium_download_active:
            return

        data = operation_result.data or {}
        installed = bool(data.get("installed"))
        installed_build = str(data.get("installed_build", "") or "")
        latest_build = str(data.get("latest_build", "") or "")
        outdated = bool(data.get("outdated"))

        self._sett_chromium_btn.setText(
            "Reinstall Chromium" if installed else "Download Chromium"
        )
        if installed:
            if outdated:
                detail = (
                    f"Installed snapshot: {installed_build}\n"
                    f"Latest snapshot: {latest_build}\n"
                    "Reinstall Chromium to update it."
                )
            else:
                detail = (
                    f"Installed snapshot: {installed_build or 'Unknown'}\n"
                    f"Latest snapshot: {latest_build}\n"
                    "You can reinstall Chromium with a clean copy."
                )
        else:
            detail = (
                f"Latest snapshot: {latest_build}\n"
                "Download portable Chromium and its matching ChromeDriver."
            )
        self._sett_chromium_btn.setToolTip(detail)

    def _on_chromium_progress(self, pct: int, label: str) -> None:
        if not hasattr(self, "_sett_chromium_btn"):
            return
        btn = self._sett_chromium_btn
        btn.setText(label if label else f"{pct}%")
        filled = max(0, min(100, pct))
        if filled == 0:
            btn.setStyleSheet(
                f"QPushButton {{ background: {INPUT}; color: {TEXT}; "
                f"border: 1px solid {LINE}; text-align: center; }}"
            )
            return

        stop_a = f"{filled / 100:.4f}"
        stop_b = f"{min(filled / 100 + 0.001, 1.0):.4f}"
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: qlineargradient("
            f"    x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 #3A5A9A,"
            f"    stop:{stop_a} #3A5A9A,"
            f"    stop:{stop_b} {INPUT},"
            f"    stop:1 {INPUT}"
            f"  );"
            f"  color: {TEXT}; border: 1px solid {LINE}; text-align: center;"
            f"}}"
        )

    def _on_chromium_done(self, result) -> None:
        self._chromium_download_active = False
        operation_result = ensure_result(
            result,
            failure_code="CHROMIUM_DOWNLOAD_FAILED",
            failure_title="Chromium Download Failed",
            failure_message="Chromium could not be downloaded.",
        )
        self._set_chromium_button_idle()
        if operation_result:
            print("[INFO] Chromium download and extraction complete.")
            return

        print(
            f"[ERROR] Chromium download failed: "
            f"{operation_result.code}: {operation_result.detail}"
        )
        self._show_operation_error(operation_result)

    def _on_sett_dl_chromium(self):
        if self._chromium_download_active:
            return

        target_exe = chromium_mod.get_chromium_path()
        action = (
            "Reinstall"
            if bool(chromium_mod.validate_chromium())
            else "Download"
        )
        print(f"[INFO] {action} requested. Target: {target_exe}")

        self._chromium_download_active = True
        self._sett_chromium_btn.setEnabled(False)
        self._sett_chromium_btn.setText("0%")
        print("[INFO] Starting Chromium download thread...")

        chromium_mod.download_chromium(
            lambda percent, label: self._bridge.chromium_progress.emit(
                percent,
                label,
            ),
            lambda result: self._bridge.chromium_done.emit(result),
        )

    def _on_sett_switch_encryption(self):
        method_labels = {"hardware": "Hardware", "password": "Password", "none": "No Encryption"}
        current_method = self.manager.get_encryption_method() or "none"

        other_methods = [m for m in ("hardware", "password", "none") if m != current_method]
        choice, ok = QInputDialog.getItem(
            self, "Switch Encryption Method",
            f"Current method: {method_labels[current_method]}\n"
            "Choose the new encryption method:",
            [method_labels[m] for m in other_methods], 0, False,
        )
        if not ok or not choice:
            return
        new_method = other_methods[[method_labels[m] for m in other_methods].index(choice)]

        new_password = None
        if new_method == "password":
            while True:
                pw1, ok1 = QInputDialog.getText(
                    self, "Set Password", "Enter new password (min. 8 characters):",
                    QLineEdit.EchoMode.Password,
                )
                if not ok1:
                    return
                if len(pw1) < 8:
                    QMessageBox.warning(self, "Invalid Password", "Password must be at least 8 characters.")
                    continue
                pw2, ok2 = QInputDialog.getText(
                    self, "Confirm Password", "Confirm new password:",
                    QLineEdit.EchoMode.Password,
                )
                if not ok2:
                    return
                if pw1 != pw2:
                    QMessageBox.warning(self, "Password Mismatch", "Passwords do not match.")
                    continue
                new_password = pw1
                break

        if new_method == "none":
            reply = QMessageBox.warning(
                self, "No Encryption",
                "Your account data will be stored in plain text.\n"
                "Anyone with access to your files can read your cookies.\n\n"
                "Are you sure you want to continue without encryption?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            reply = QMessageBox.question(
                self, "Switch Encryption Method",
                f"Switch encryption to {method_labels[new_method]}?\n"
                "Your existing accounts will be re-encrypted in place.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.manager.switch_encryption_method(new_method, password=new_password)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to switch encryption method:\n{e}")
            return

        self._update_encryption_badge()
        _show_info(
            self, "Encryption Switched",
            f"Encryption method switched to {method_labels[new_method]}.",
        )

    def _on_sett_wipe_data(self):
        reply = QMessageBox.warning(
            self, "Wipe All Data",
            "This will permanently delete ALL saved accounts, settings,\n"
            "and cached data. This action CANNOT be undone.\n\n"
            "Are you absolutely sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            data_dir = get_data_dir()
            try:
                shutil.rmtree(data_dir, ignore_errors=True)
                QMessageBox.information(
                    self, "Done",
                    "All data wiped. The application will now close."
                )
                QApplication.quit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Wipe failed:\n{e}")

    def _on_sett_developer_mode(self, enabled: bool):
        self._sett_copycookie_chk.setEnabled(enabled)
        self._sett_ws_chk.setEnabled(enabled)
        self._update_ws_password_controls()
        if not enabled:
            self._sett_copycookie_chk.setChecked(False)
            self._sett_ws_chk.setChecked(False)
            actions.save_ui_setting("enable_copy_cookie", False)
            actions.save_ui_setting("websocket_enabled", False)
            self._stop_ws_server()

    def _on_sett_ws_changed(self, enabled: bool):
        self._update_ws_password_controls()
        if enabled:
            self._start_ws_server()
        else:
            self._stop_ws_server()

    def _update_ws_password_controls(self):
        if not hasattr(self, "_sett_ws_pw_chk"):
            return
        developer_enabled = bool(
            hasattr(self, "_sett_devmode_chk")
            and self._sett_devmode_chk.isChecked()
        )
        websocket_enabled = bool(
            hasattr(self, "_sett_ws_chk")
            and self._sett_ws_chk.isChecked()
        )
        controls_enabled = developer_enabled and websocket_enabled
        self._sett_ws_pw_chk.setEnabled(controls_enabled)
        password_enabled = controls_enabled and self._sett_ws_pw_chk.isChecked()
        if hasattr(self, "_sett_ws_password_edit"):
            self._sett_ws_password_edit.setEnabled(password_enabled)
        if hasattr(self, "_sett_ws_password_set_btn"):
            self._sett_ws_password_set_btn.setEnabled(password_enabled)

    def _on_sett_ws_password_required(self, enabled: bool):
        self._update_ws_password_controls()
        if enabled and not self._sett_ws_saved_password:
            self._sett_ws_password_edit.setFocus()

    def _on_sett_ws_password_save(self):
        password = self._sett_ws_password_edit.text()
        previous = self._sett_ws_saved_password
        if password == previous:
            return True
        if not password:
            self._sett_ws_password_edit.setText(previous)
            self._show_operation_error(OperationResult.failure(
                "WEBSOCKET_PASSWORD_REQUIRED",
                "WebSocket Password Required",
                "Enter a WebSocket password before clicking Set.",
            ))
            return False

        result = self.manager.set_secure_setting(
            "websocket_password",
            password,
        )

        if not result:
            self._sett_ws_password_edit.setText(previous)
            self._show_operation_error(result)
            return False

        self._sett_ws_saved_password = password
        return True

    def _start_ws_server(self) -> None:
        if self._ws_server:
            self._ws_server.start()

    def _stop_ws_server(self) -> None:
        if self._ws_server:
            self._ws_server.stop()

    def _on_dc_save(self, *_):
        try:
            dc = actions.load_ui_settings().get("discord_webhook", {})
            dc["enabled"] = self._sett_dc_enabled_chk.isChecked()
            dc["url"] = self._sett_dc_url_edit.text().strip()
            dc["enable_ping"] = self._sett_dc_ping_chk.isChecked()
            dc["ping_user_id"] = self._sett_dc_pingid_edit.text().strip()
            dc["ping_on_error"] = self._sett_dc_pingerr_chk.isChecked()
            dc["screenshot_enabled"] = self._sett_dc_ss_chk.isChecked()
            dc["screenshot_interval_minutes"] = self._sett_dc_ss_spin.value()
            for key, cb in self._sett_dc_log_chks.items():
                dc[key] = cb.isChecked()
            actions.save_ui_setting("discord_webhook", dc)
            if dc.get("enabled") and dc.get("screenshot_enabled"):
                webhook.start_screenshot_loop(
                    lambda: actions.get_ui_setting("discord_webhook", {})
                )
            else:
                webhook.stop_screenshot_loop()
        except Exception as e:
            print(f"[Discord] Failed to save settings: {e}")

    def _on_dc_test(self):
        url = self._sett_dc_url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Enter a Webhook URL first.")
            return
        def _do():
            try:
                payload = {
                    "embeds": [{
                        "title": "Roblox Account Manager Test",
                        "description": "Discord webhook integration is working correctly!",
                        "color": 0x2ECC71,
                        "footer": {"text": "Evanovar's Roblox Account Manager"},
                    }]
                }
                resp = requests.post(
                    url, json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                if resp.status_code in (200, 204):
                    print("[SUCCESS] Discord test webhook sent.")
                else:
                    print(f"[ERROR] Discord test failed: HTTP {resp.status_code} | {resp.text[:120]}")
            except Exception as e:
                print(f"[ERROR] Discord test exception: {e}")
        threading.Thread(target=_do, daemon=True).start()

    _AR_ACTIVE_COLOR = "#4CAF50"
    _AR_INACTIVE_COLOR = "#EF5350"

    def _ar_refresh_list(self):
        if self._ar_list is None:
            return

        cur = self._ar_selected_account()
        self._ar_list.clear()
        if not hasattr(self, "_ar_avatar_labels"):
            self._ar_avatar_labels: dict[str, QLabel] = {}
        self._ar_avatar_labels.clear()

        AV = avatars.AVATAR_SIZE
        ITEM_H = AV + 6

        if not self._ar_configs:
            empty = QListWidgetItem("No accounts monitored, Press Add Account.")
            empty.setForeground(QColor(MUTED))
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._ar_list.addItem(empty)
            return

        for account, cfg in self._ar_configs.items():
            worker = self._ar_workers.get(account)
            active = worker is not None and worker.is_alive()

            item = QListWidgetItem("")
            item.setSizeHint(QSize(0, ITEM_H))
            item.setData(Qt.ItemDataRole.UserRole, account)

            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(4, 0, 6, 0)
            row_lay.setSpacing(6)

            # Avatar
            av_lbl = QLabel()
            av_lbl.setFixedSize(AV, AV)
            av_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
            av_lbl.setPixmap(self._make_placeholder_pixmap(AV))
            row_lay.addWidget(av_lbl)
            self._ar_avatar_labels[account] = av_lbl

            # Username
            name_lbl = QLabel(account)
            name_lbl.setObjectName("accountName")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            row_lay.addWidget(name_lbl)

            # status
            sep = QLabel("|")
            sep.setObjectName("noteSep")
            sep.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            row_lay.addWidget(sep)

            status_str = "active"   if active else "inactive"
            status_color = self._AR_ACTIVE_COLOR if active else self._AR_INACTIVE_COLOR
            status_lbl = QLabel(status_str)
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            status_lbl.setStyleSheet(f"color: {status_color}; font-size: 10px;")
            row_lay.addWidget(status_lbl)

            row_lay.addStretch(1)

            pid_lbl = QLabel(f"Place: {cfg.get('place_id', '?')}")
            pid_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            pid_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
            row_lay.addWidget(pid_lbl)

            row.setFixedHeight(ITEM_H)
            self._ar_list.addItem(item)
            self._ar_list.setItemWidget(item, row)

        # Restore selection
        if cur:
            for i in range(self._ar_list.count()):
                it = self._ar_list.item(i)
                if it and it.data(Qt.ItemDataRole.UserRole) == cur:
                    self._ar_list.setCurrentItem(it)
                    break
        if self._ar_list.count() > 0 and not self._ar_list.currentItem():
            self._ar_list.setCurrentRow(0)

        self._ar_load_avatars_async()

    def _ar_load_avatars_async(self): # Load avatar for auto rejoin accounts
        ar_labels = getattr(self, "_ar_avatar_labels", {})
        for account in list(ar_labels.keys()):
            acc_data = self.manager.accounts.get(account, {})
            if not isinstance(acc_data, dict):
                continue
            user_id = str(acc_data.get("user_id") or "")
            if not user_id or user_id == "0":
                continue
            avatars.fetch_avatar_async(
                user_id, account,
                on_done=lambda u, b: self._bridge.avatar_ready.emit(u, b),
            )

    def _on_rejoin_status(self, account: str, status: str) -> None:
        self._ar_refresh_list()

    def _ar_selected_account(self) -> str | None: # get selected account
        item = self._ar_list.currentItem() if self._ar_list else None
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _ar_start_worker(self, account: str) -> None: # start worker for an account
        if account in self._ar_workers and self._ar_workers[account].is_alive():
            return
        cfg = self._ar_configs.get(account)
        if not cfg:
            return
        worker = ar.AutoRejoinWorker(
            account, cfg, self.manager,
            on_status=lambda u, s: self._bridge.rejoin_status.emit(u, s),
        )
        self._ar_workers[account] = worker
        worker.start()

    def _ar_on_context_menu(self, pos): # Context menu for auto rejoin accounts
        # Start: start worker to monitor and auto-rejoin for this account
        # Stop: stop worker and auto-rejoin for this account
        # Edit: edit the account's auto-rejoin configuration
        # Remove: stop worker if active, remove account from auto-rejoin list and erase configuration
        item = self._ar_list.itemAt(pos)
        if item is None:
            return
        account = item.data(Qt.ItemDataRole.UserRole)
        if not account:
            return

        self._ar_list.setCurrentItem(item)
        worker = self._ar_workers.get(account)
        active = worker is not None and worker.is_alive()

        menu = QMenu(self)
        act_start = menu.addAction("Start") if not active else None
        act_stop = menu.addAction("Stop") if active else None
        act_edit = menu.addAction("Edit")
        menu.addSeparator()
        act_remove = menu.addAction("Remove")

        chosen = menu.exec(self._ar_list.mapToGlobal(pos))
        if act_start  and chosen == act_start:
            self._ar_on_start()
        elif act_stop  and chosen == act_stop:
            self._ar_on_stop()
        elif chosen == act_edit:
            self._ar_on_edit()
        elif chosen == act_remove:
            self._ar_on_remove()

    # Auto-Rejoin button slots
    def _ar_on_add(self):
        win = _AutoRejoinAddWindow(self.manager, self)
        if win.exec() == QDialog.DialogCode.Accepted:
            for account, cfg in win.result_configs.items():
                self._ar_configs[account] = cfg
            ar.save_configs(self._ar_configs)
            self._ar_refresh_list()

    def _ar_on_edit(self): # Edit config for the selected account
        account = self._ar_selected_account()
        if not account:
            _show_error(self, "No Selection", "Select an account to edit.")
            return
        cfg = self._ar_configs.get(account)
        if not cfg:
            return
        # pre fill the add/edit form with the existing config for this account
        win = _AutoRejoinAddWindow(self.manager, self, edit_account=account, edit_config=cfg)
        if win.exec() == QDialog.DialogCode.Accepted:
            for acc, config in win.result_configs.items():
                self._ar_configs[acc] = config
            ar.save_configs(self._ar_configs)
            self._ar_refresh_list()

    def _ar_on_start(self):
        account = self._ar_selected_account()
        if not account:
            _show_error(self, "No Selection", "Select an account to start.")
            return
        self._ar_start_worker(account)
        self._ar_show_launching_status(account)
        QTimer.singleShot(500, self._ar_refresh_list)

    def _ar_show_launching_status(self, account: str):
        for i in range(self._ar_list.count()):
            item = self._ar_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == account:
                widget = self._ar_list.itemWidget(item)
                if widget:
                    # Find and update the status label
                    for child in widget.children():
                        if isinstance(child, QLabel):
                            style = child.styleSheet()
                            if "active" in style or "inactive" in style:
                                child.setText("launching")
                                child.setStyleSheet(f"color: {NOTE}; font-size: 10px;")
                                break
                break 

    def _ar_on_stop(self):
        account = self._ar_selected_account()
        if not account:
            _show_error(self, "No Selection", "Select an account to stop.")
            return
        worker = self._ar_workers.pop(account, None)
        if worker:
            worker.stop()
        self._ar_refresh_list()

    def _ar_on_start_all(self):
        for account in list(self._ar_configs.keys()):
            self._ar_start_worker(account)
        for account in list(self._ar_configs.keys()):
            self._ar_show_launching_status(account)
        QTimer.singleShot(500, self._ar_refresh_list)

    def _ar_on_stop_all(self):
        for worker in list(self._ar_workers.values()):
            worker.stop()
        self._ar_workers.clear()
        self._ar_refresh_list()

    def nativeEvent(self, event_type, message):
        if window_grid_mod.is_hotkey_message(message):
            result = window_grid_mod.tile_roblox_windows()
            if not result:
                print(f"[Window Grid] {result.code}: {result.message}")
                if result.detail:
                    print(f"[Window Grid] {result.detail}")
            return True, 0
        return super().nativeEvent(event_type, message)

    def _setup_system_tray(self) -> None:
        if actions.load_ui_settings().get("hide_to_system_tray", False):
            result = self._enable_system_tray()
            if not result:
                self._set_tray_checkbox(False)
                actions.save_ui_setting("hide_to_system_tray", False)
                self._show_operation_error(result)

    def _set_tray_checkbox(self, enabled: bool) -> None:
        if not hasattr(self, "_sett_tray_chk"):
            return
        self._sett_tray_chk.blockSignals(True)
        self._sett_tray_chk.setChecked(enabled)
        self._sett_tray_chk.blockSignals(False)

    def _enable_system_tray(self) -> OperationResult:
        if self._tray_icon:
            self._tray_icon.show()
            QApplication.instance().setQuitOnLastWindowClosed(False)
            return OperationResult.success()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return OperationResult.failure(
                "SYSTEM_TRAY_UNAVAILABLE",
                "System Tray Unavailable",
                "Windows did not provide a system tray for Evanovar RAM.",
                detail="QSystemTrayIcon.isSystemTrayAvailable() returned false.",
            )

        try:
            icon = QIcon(self._icon_path) if self._icon_path else QApplication.windowIcon()
            if icon.isNull():
                return OperationResult.failure(
                    "SYSTEM_TRAY_SETUP_FAILED",
                    "System Tray Setup Failed",
                    "The application icon could not be loaded for the system tray.",
                    detail="No valid application icon was available.",
                )

            tray_icon = QSystemTrayIcon(icon, self)
            tray_icon.setToolTip("Evanovar's Roblox Account Manager")
            menu = QMenu(self)
            show_action = QAction("Show UI", self)
            exit_action = QAction("Exit", self)
            show_action.triggered.connect(self._show_from_tray)
            exit_action.triggered.connect(self._exit_from_tray)
            menu.addAction(show_action)
            menu.addSeparator()
            menu.addAction(exit_action)
            tray_icon.setContextMenu(menu)
            tray_icon.activated.connect(self._on_tray_activated)
            tray_icon.show()

            self._tray_icon = tray_icon
            self._tray_menu = menu
            QApplication.instance().setQuitOnLastWindowClosed(False)
            return OperationResult.success()
        except Exception as exc:
            print(f"[ERROR] Failed to create system tray icon: {exc}")
            return OperationResult.failure(
                "SYSTEM_TRAY_SETUP_FAILED",
                "System Tray Setup Failed",
                "The system tray icon could not be created.",
                detail=f"{type(exc).__name__}: {exc}",
            )

    def _disable_system_tray(self) -> None:
        tray_icon = self._tray_icon
        tray_menu = self._tray_menu
        self._tray_icon = None
        self._tray_menu = None
        if tray_icon:
            tray_icon.hide()
            tray_icon.setContextMenu(None)
            tray_icon.deleteLater()
        if tray_menu:
            tray_menu.deleteLater()
        app = QApplication.instance()
        if app:
            app.setQuitOnLastWindowClosed(True)

    def _on_sett_tray(self, enabled: bool) -> None:
        if enabled:
            result = self._enable_system_tray()
            if result:
                actions.save_ui_setting("hide_to_system_tray", True)
                return
            self._set_tray_checkbox(False)
            actions.save_ui_setting("hide_to_system_tray", False)
            self._show_operation_error(result)
            return

        actions.save_ui_setting("hide_to_system_tray", False)
        self._disable_system_tray()

    def _on_tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        try:
            self.show()
            if self._tray_restore_maximized:
                self.showMaximized()
            else:
                self.showNormal()
            self.raise_()
            self.activateWindow()
        except Exception as exc:
            print(f"[ERROR] Failed to restore UI from system tray: {exc}")
            _show_error(
                self,
                "System Tray Restore Failed",
                "The main window could not be restored from the system tray.\n\n"
                f"Error code: SYSTEM_TRAY_RESTORE_FAILED\n\n{exc}",
            )

    def _exit_from_tray(self) -> None:
        self._tray_exit_requested = True
        self.close()

    def _perform_shutdown_cleanup(self) -> None:
        if self._shutdown_cleanup_done:
            return
        self._shutdown_cleanup_done = True

        try:
            self._unregister_window_grid_hotkey()
        except Exception:
            pass
        try:
            for worker in list(self._ar_workers.values()):
                worker.stop(join_timeout=1.0)
        except Exception:
            pass
        # Stop WebSocket server
        try:
            if self._ws_server:
                self._ws_server.stop()
        except Exception:
            pass
        # Stop screenshot loop
        try:
            webhook.stop_screenshot_loop()
        except Exception:
            pass
        # Stop presence scanner
        try:
            self._stop_presence_scanner()
        except Exception:
            pass
        # Stop Roblox window renamer
        try:
            self._stop_rename_windows()
        except Exception:
            pass
        # Cleanup drag-drop filter
        try:
            if hasattr(self, "_drag_filter"):
                self._drag_filter.cleanup()
        except Exception:
            pass
        # Restore quarantined installers
        try:
            if actions.load_ui_settings().get("roblox_installer_fix", False):
                RobloxAPI.restore_installers()
        except Exception as e:
            print(f"[ERROR] Failed to restore installers: {e}")
        # Unlock the Roblox settings file only when this app owns the lock.
        try:
            profile_result = roblox_settings_mod.load_local_profile()
            profile = (profile_result.data or {}).get("profile", {})
            if profile_result and bool(profile.get("lock_owned", False)):
                unlock_result = roblox_settings_mod.unlock_framerate_cap()
                if not unlock_result:
                    print(
                        f"[ERROR] {unlock_result.code}: "
                        f"{unlock_result.message} {unlock_result.detail}"
                    )
                else:
                    profile["lock_owned"] = False
                    roblox_settings_mod.save_local_profile(profile)
        except Exception as e:
            print(f"[ERROR] Failed to unlock framerate cap file: {e}")
        try:
            self._stop_headless_manager()
        except Exception as e:
            print(f"[ERROR] Failed to restore Roblox windows: {e}")
        self._disable_system_tray()

    def closeEvent(self, event):
        hide_to_tray = actions.load_ui_settings().get(
            "hide_to_system_tray",
            False,
        )
        if hide_to_tray and not self._tray_exit_requested:
            self._tray_restore_maximized = self.isMaximized()
            event.ignore()
            self.hide()
            return

        self._perform_shutdown_cleanup()
        super().closeEvent(event)

    def _ar_on_remove(self):
        account = self._ar_selected_account()
        if not account:
            _show_error(self, "No Selection", "Select an account to remove.")
            return
        reply = QMessageBox.question(
            self, "Remove Auto-Rejoin",
            f"Remove auto-rejoin for '{account}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        worker = self._ar_workers.pop(account, None)
        if worker:
            worker.stop()
        self._ar_configs.pop(account, None)
        ar.save_configs(self._ar_configs)
        self._ar_refresh_list()

    def _build_right_panel(self) -> QFrame: # Right panel actions
        panel = QFrame()
        panel.setObjectName("rightPanel")
        panel.setFixedWidth(228)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        title = QLabel("Actions")
        title.setObjectName("sectionTitle")
        lay.addWidget(title)

        # Current place label
        self._game_name_label = QLabel("")
        self._game_name_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        lay.addWidget(self._game_name_label)

        # Place ID
        place_lbl = QLabel("Place ID")
        place_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        lay.addWidget(place_lbl)

        self._place_id_edit = QComboBox()
        self._place_id_edit.setEditable(True)
        self._place_id_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._place_id_edit.lineEdit().setPlaceholderText("e.g. 10449761463") # This game is fun
        _arrow_path = _dropdown_arrow_icon_path(TEXT).replace("\\", "/")
        self._place_id_edit.setStyleSheet(
            f"QComboBox {{ background: {INPUT}; border: 1px solid {LINE};"
            f" color: {TEXT}; padding: 4px 6px; min-height: 24px; }}"
            f"QComboBox::drop-down {{ border: 0; width: 20px; }}"
            f"QComboBox::down-arrow {{ image: url({_arrow_path}); width: 10px; height: 10px; }}"
        )
        self._place_id_edit.currentTextChanged.connect(self._on_place_id_changed)
        self._place_id_edit.activated.connect(self._on_favorite_selected)
        self._favorite_ctx_filter = _ComboRightClickFilter(self)
        self._favorite_ctx_filter.right_clicked.connect(self._on_favorite_context_menu)
        self._place_id_edit.view().viewport().installEventFilter(self._favorite_ctx_filter)
        self._refresh_favorites_dropdown()
        lay.addWidget(self._place_id_edit)

        # Private server
        priv_lbl = QLabel("Private Server Link (Optional)")
        priv_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        lay.addWidget(priv_lbl)

        self._private_server_edit = QLineEdit()
        self._private_server_edit.setPlaceholderText("VIP Link or Link Code")
        self._private_server_edit.textChanged.connect(self._on_private_server_changed)
        lay.addWidget(self._private_server_edit)

        # join button
        join_btn = QPushButton("Join Place ID")
        join_btn.setStyleSheet(
            f"QPushButton {{ background: {SELECT}; border: 1px solid {LINE};"
            f"  min-height: 30px; font-weight: 700; text-align: center; color: {TEXT}; }}"
            f"QPushButton:hover   {{ background: #3A3A3A; }}"
            f"QPushButton:pressed {{ background: #1E1E1E; }}"
        )
        join_btn.clicked.connect(self._on_join_place)

        self._join_menu = QMenu(self)
        act_join_user = self._join_menu.addAction("Join User")
        act_job_id = self._join_menu.addAction("Job ID")
        act_small_srv = self._join_menu.addAction("Small Server")
        self._join_menu.addSeparator()
        act_save_fav = self._join_menu.addAction("Save Current Game")
        act_join_user.triggered.connect(self._on_join_user)
        act_job_id.triggered.connect(self._on_join_job_id)
        act_small_srv.triggered.connect(self._on_join_small_server)
        act_save_fav.triggered.connect(self._on_save_current_game)

        self._join_arrow = QToolButton()
        self._join_arrow.setObjectName("splitArrow")
        self._join_arrow.setText("v")
        self._join_arrow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._join_arrow.setMenu(self._join_menu)
        self._join_arrow.setFixedWidth(26)
        self._join_arrow.setFixedHeight(30)

        join_row = QHBoxLayout()
        join_row.setSpacing(4)
        join_row.addWidget(join_btn, 1)
        join_row.addWidget(self._join_arrow)
        lay.addLayout(join_row)

        recent_header = QHBoxLayout()
        recent_header.setContentsMargins(0, 0, 0, 0)
        recent_header.setSpacing(0)

        recent_lbl = QLabel("Recent games")
        recent_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        recent_header.addWidget(recent_lbl)
        recent_header.addStretch(1)

        _discord_path = os.path.join(get_data_dir(), "discordlogo.png")
        if not os.path.exists(_discord_path):
            _discord_path = get_resource_path("discordlogo.png")
        discord_btn = QPushButton()
        discord_btn.setObjectName("discordBtn")
        discord_btn.setFixedSize(18, 18)
        discord_btn.setToolTip("Join Discord server")
        discord_btn.setFlat(True)
        discord_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        discord_btn.setStyleSheet(
            "QPushButton#discordBtn { background: transparent; border: 0; padding: 0; }"
            "QPushButton#discordBtn:hover { background: transparent; }"
        )
        if os.path.exists(_discord_path):
            _dpix = QPixmap(_discord_path).scaled(
                16, 16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            discord_btn.setIcon(QIcon(_dpix))
            discord_btn.setIconSize(QSize(16, 16))
        discord_btn.clicked.connect(
            lambda: webbrowser.open("https://discord.gg/SZaZU8zwZA")
        )
        recent_header.addWidget(discord_btn)

        lay.addLayout(recent_header)


        self._recent_list = QListWidget()
        self._recent_list.setFixedHeight(90)
        self._recent_list.itemDoubleClicked.connect(self._on_recent_game_double_click)
        lay.addWidget(self._recent_list)

        # Quick action buttons
        for label, slot in [
            ("Edit Note",           self._on_edit_note),
            ("Refresh List",        self._refresh_account_list),
            ("Launch Roblox Home",  self._on_launch_home),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"QPushButton {{ text-align: center; color: {TEXT}; }}"
            )
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        lay.addStretch(1)
        return panel

    @staticmethod
    def _make_circular_pixmap(data: bytes, size: int = avatars.AVATAR_SIZE) -> QPixmap: # Avatar helpers
        src = QPixmap()
        src.loadFromData(data)
        if src.isNull():
            return QPixmap()
        src = src.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, src)
        painter.end()
        return result

    def _make_placeholder_pixmap(self, size: int = avatars.AVATAR_SIZE) -> QPixmap: # Gray icon
        cached = self._placeholder_pixmaps.get(size)
        if cached is not None:
            return cached
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#2A2A2A"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, size, size)
        painter.end()
        self._placeholder_pixmaps[size] = result
        return result

    @staticmethod
    def _create_invalid_badge(container: QWidget) -> QLabel:
        badge_size = 6
        ring = 1
        badge = QLabel(container)
        badge.setFixedSize(badge_size + ring * 2, badge_size + ring * 2)
        badge.move(0, 0)
        badge.setStyleSheet(f"""
            QLabel {{
                background: #E8A020;
                border-radius: {(badge_size + ring * 2) // 2}px;
                border: {ring}px solid {BG};
            }}
        """)
        badge.setToolTip(
            "Cookie validation received repeated unauthorized responses.\n"
            "You can still try launching this account."
        )
        return badge

    def _get_selected_username(self) -> str | None:
        item = self._account_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _get_selected_usernames(self) -> list[str]:
        items = self._account_list.selectedItems()
        names = []
        for it in items:
            u = it.data(Qt.ItemDataRole.UserRole)
            if u:  # skip group-header rows which have no UserRole data
                names.append(u)
        return names

    def _confirm_launch(self, action_label: str, accounts: list[str]) -> bool:
        if not actions.load_ui_settings().get("confirm_before_launch", False):
            return True
        if len(accounts) == 1:
            msg = f"Launch {action_label} for {accounts[0]}?"
        else:
            names_preview = ", ".join(accounts[:5])
            if len(accounts) > 5:
                names_preview += f" (+{len(accounts)-5} more)"
            msg = f"Launch {action_label} for {len(accounts)} accounts:\n{names_preview}"
        reply = QMessageBox.question(
            self, "Confirm Launch", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _refresh_account_list(self): # Main account list population and refresh
        if hasattr(self, "_drag_filter"):
            self._drag_filter.abort()
        cur_item = self._account_list.currentItem()
        cur_username = cur_item.data(Qt.ItemDataRole.UserRole) if cur_item else None
        selected_usernames = {
            it.data(Qt.ItemDataRole.UserRole) for it in self._account_list.selectedItems()
        }
        scroll_value = self._account_list.verticalScrollBar().value()
        self._account_list.clear()
        self._avatar_labels.clear()
        self._presence_dots.clear()
        self._activity_widgets.clear()
        self._activity_labels.clear()
        self._invalid_badges.clear()
        self._account_avatar_containers.clear()
        self._account_name_labels.clear()
        self._account_rows.clear()
        account_items = list(self.manager.accounts.items())
        activity_enabled = bool(
            actions.load_ui_settings().get("presence_indicator", False)
        )

        # Filter by groups
        if self._current_group is not None:
            assignments = groups.get_assignments()
            account_items = [
                (u, d) for u, d in account_items
                if assignments.get(u) == self._current_group
            ]

        if not account_items:
            item = QListWidgetItem("No accounts, use 'Add Account' to add one.")
            item.setForeground(QColor(MUTED))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._account_list.addItem(item)
            self._rebuild_group_bar()
            return

        AV = avatars.AVATAR_SIZE
        ITEM_H = AV + 6

        for username, data in account_items:
            note = data.get("note", "") if isinstance(data, dict) else ""

            item = QListWidgetItem("")
            item.setSizeHint(QSize(0, ITEM_H))
            item.setData(Qt.ItemDataRole.UserRole, username)

            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(4, 0, 6, 0)
            row_lay.setSpacing(6)

            av_container = QWidget()
            av_container.setFixedSize(AV, AV)

            av_lbl = QLabel(av_container)
            av_lbl.setFixedSize(AV, AV)
            av_lbl.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            )
            av_lbl.setPixmap(self._make_placeholder_pixmap(AV))

            DOT_SIZE = 6
            RING = 1
            dot_lbl = QLabel(av_container)
            dot_lbl.setFixedSize(DOT_SIZE + RING * 2, DOT_SIZE + RING * 2)
            dot_lbl.move(AV - DOT_SIZE - RING, AV - DOT_SIZE - RING)
            dot_lbl.setStyleSheet(f"""
                QLabel {{
                    background: #2ECC71;
                    border-radius: {(DOT_SIZE + RING * 2) // 2}px;
                    border: {RING}px solid {BG};
                }}
            """)
            is_online = username in self._online_usernames
            dot_lbl.setVisible(is_online)
            self._presence_dots[username] = dot_lbl

            row_lay.addWidget(av_container)
            self._avatar_labels[username] = av_lbl
            self._account_avatar_containers[username] = av_container

            flagged = self._cv_mod.is_flagged(data) if isinstance(data, dict) else False

            if flagged:
                bad_lbl = self._create_invalid_badge(av_container)
                self._invalid_badges[username] = bad_lbl

            name_lbl = QLabel(username)
            name_lbl.setObjectName("accountName")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if flagged:
                name_lbl.setStyleSheet("color: #E8A020; font-style: italic;")
                name_lbl.setToolTip(
                    "Cookie validation received repeated unauthorized responses.\n"
                    "You can still try launching this account."
                )
            row_lay.addWidget(name_lbl)
            self._account_name_labels[username] = name_lbl

            if note: # Note display
                sep = QLabel("|")
                sep.setObjectName("noteSep")
                sep.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                note_lbl = QLabel(note)
                note_lbl.setObjectName("noteText")
                note_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                row_lay.addWidget(sep)
                row_lay.addWidget(note_lbl)

            if activity_enabled:
                activity_container = QWidget(row)
                activity_lay = QHBoxLayout(activity_container)
                activity_lay.setContentsMargins(0, 0, 0, 0)
                activity_lay.setSpacing(4)

                ram_sep = QLabel("|")
                ram_sep.setObjectName("performanceSep")
                ram_lbl = QLabel("0 MB")
                ram_lbl.setObjectName("ramUsage")
                ram_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )

                cpu_sep = QLabel("|")
                cpu_sep.setObjectName("performanceSep")
                cpu_lbl = QLabel("0.0%")
                cpu_lbl.setObjectName("cpuUsage")
                cpu_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )

                activity_lay.addWidget(ram_sep)
                activity_lay.addWidget(ram_lbl)
                activity_lay.addWidget(cpu_sep)
                activity_lay.addWidget(cpu_lbl)
                row_lay.addWidget(activity_container)
                self._activity_widgets[username] = activity_container
                self._activity_labels[username] = (ram_lbl, cpu_lbl)
                activity_container.setVisible(username in self._activity_snapshot)
            row_lay.addStretch(1)
            row.setFixedHeight(ITEM_H)

            if flagged:
                row.setStyleSheet(
                    "QWidget { background: rgba(200, 50, 50, 0.06); }"
                )

            self._account_list.addItem(item)
            self._account_list.setItemWidget(item, row)
            self._account_rows[username] = row

        restored_current = False
        for i in range(self._account_list.count()):
            it = self._account_list.item(i)
            username = it.data(Qt.ItemDataRole.UserRole)
            if username in selected_usernames:
                it.setSelected(True)
            if username == cur_username:
                self._account_list.setCurrentItem(it)
                restored_current = True

        if not restored_current and self._account_list.count() > 0:
            self._account_list.setCurrentRow(0)

        # setCurrentItem/setCurrentRow above auto-scroll to keep the current
        # item visible - restore the scroll position the user actually had.
        self._account_list.verticalScrollBar().setValue(scroll_value)

        self._rebuild_group_bar()
        self._load_avatars_async()
        self._update_activity_rows()


    def _rebuild_group_bar(self):
        if self._group_bar_lay is None:
            return
        
        while self._group_bar_lay.count():
            child = self._group_bar_lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # [All] group
        all_btn = QPushButton("All")
        all_btn.setObjectName("groupTab")
        all_btn.setCheckable(True)
        all_btn.setChecked(self._current_group is None)
        all_btn.clicked.connect(lambda: self._on_group_tab_clicked(None))
        self._group_bar_lay.addWidget(all_btn)

        for gname in groups.get_group_names():
            btn = QPushButton(gname)
            btn.setObjectName("groupTab")
            btn.setCheckable(True)
            btn.setChecked(self._current_group == gname)
            btn.clicked.connect(lambda _=False, n=gname: self._on_group_tab_clicked(n))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, n=gname, b=btn: self._on_group_tab_context(pos, n, b)
            )
            self._group_bar_lay.addWidget(btn)

        # + button to add new group
        plus_btn = QPushButton("+")
        plus_btn.setObjectName("groupTab")
        plus_btn.setFixedWidth(24)
        plus_btn.setToolTip("Create new group")
        plus_btn.clicked.connect(self._on_add_group)
        self._group_bar_lay.addWidget(plus_btn)

        self._group_bar_lay.addStretch(1)

    def _on_group_tab_clicked(self, group_name: str | None):
        self._current_group = group_name
        self._rebuild_group_bar()
        self._refresh_account_list()

    def _on_group_tab_context(self, pos, group_name: str, btn: QPushButton):
        # Context menu for group tabs
        # Rename: change the group's name
        # Delete: remove the group, accounts become ungrouped
        menu = QMenu(self)
        act_rename = menu.addAction("Rename")
        act_delete = menu.addAction("Delete")
        chosen = menu.exec(btn.mapToGlobal(pos))
        if chosen == act_rename:
            self._on_rename_group(group_name)
        elif chosen == act_delete:
            self._on_delete_group(group_name)

    def _on_add_group(self):
        name, ok = QInputDialog.getText(self, "New Group", "Group name:")
        if not ok or not name.strip():
            return
        if not groups.create_group(name.strip()):
            _show_error(self, "Error", f"Group '{name.strip()}' already exists.")
            return
        self._rebuild_group_bar()

    def _on_rename_group(self, old_name: str):
        new_name, ok = QInputDialog.getText(
            self, "Rename Group", "New name:", text=old_name
        )
        if not ok or not new_name.strip():
            return
        if not groups.rename_group(old_name, new_name.strip()):
            _show_error(self, "Error", "Could not rename, name may already exist.")
            return
        if self._current_group == old_name:
            self._current_group = new_name.strip()
        self._rebuild_group_bar()
        self._refresh_account_list()

    def _on_delete_group(self, name: str):
        reply = QMessageBox.question(
            self, "Delete Group",
            f"Delete group '{name}'?\nAccounts in this group will become ungrouped.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        groups.delete_group(name)
        if self._current_group == name:
            self._current_group = None
        self._rebuild_group_bar()
        self._refresh_account_list()

    def _on_assign_to_group(self, usernames, group_name: str):
        if isinstance(usernames, str):
            usernames = [usernames]
        for username in usernames:
            groups.set_account_group(username, group_name)
        self._refresh_account_list()

    def _on_remove_from_group(self, usernames):
        if isinstance(usernames, str):
            usernames = [usernames]
        for username in usernames:
            groups.set_account_group(username, None)
        self._refresh_account_list()

    def _load_avatars_async(self):
        avatars.sync_missing_avatar_cache(
            self.manager.accounts,
            on_avatar_ready=lambda u, b: self._bridge.avatar_ready.emit(u, b),
            on_complete=lambda: self.manager.save_accounts(),
        )

    def _on_avatar_ready(self, username: str, img_bytes: object):
        # Convert byte to circular pixmap
        try:
            pix = self._make_circular_pixmap(bytes(img_bytes), avatars.AVATAR_SIZE)
            if pix.isNull():
                return
            lbl = self._avatar_labels.get(username)
            if lbl is not None:
                lbl.setPixmap(pix)
            ar_lbl = getattr(self, "_ar_avatar_labels", {}).get(username)
            if ar_lbl is not None:
                ar_lbl.setPixmap(pix)
            # Feed avatar into drag floating label if user is being dragged
            df = getattr(self, "_drag_filter", None)
            if df and df._dragging and df._username == username:
                df.update_float_avatar(pix)
        except Exception:
            pass

    # Recent games
    def _refresh_recent_games(self):
        self._recent_list.clear()
        for entry in actions.load_recent_games():
            pid = entry.get("place_id", "")
            name = entry.get("name", pid)
            private_server = entry.get("private_server", "")
            is_private = entry.get("private", bool(private_server))

            label = name if (name and name != pid) else pid

            if is_private:
                label = f"[P] {label}"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, {"place_id": pid, "private_server": private_server})
            self._recent_list.addItem(item)

    def _on_recent_game_double_click(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        pid = data.get("place_id", "")
        private_server = data.get("private_server", "")
        if pid:
            self._place_id_edit.setCurrentText(pid)
            self._private_server_edit.setText(private_server)

    def _update_encryption_badge(self):
        text, color = actions.get_encryption_status(self.manager)
        self._enc_label.setText(text)
        self._enc_label.setStyleSheet(
            f"color: {color};"
        )

    def _on_place_id_changed(self, text: str):
        self._game_name_label.setText("")
        self._game_name_timer.start(350)

    def _on_private_server_changed(self, text: str):
        self._game_name_label.setText("")
        self._game_name_timer.start(350)

    def _schedule_game_name_fetch(self):
        self._game_name_timer.start(350)

    def _fetch_game_name_for(self, place_id: str):
        def _cb(name):
            if name:
                truncated = name if len(name) <= 28 else name[:26] + ".."
                display = f"Current: {truncated}"
            else:
                display = ""

            self._bridge.game_name_ready.emit(display) # emit to main thread

        actions.fetch_game_name_async(place_id, _cb)

    def _do_fetch_game_name(self):
        place_id = self._place_id_edit.currentText().strip()
        private = self._private_server_edit.text().strip()
        actions.save_ui_setting("last_place_id", place_id)
        actions.save_ui_setting("last_private_server", private)
        if place_id:
            if not place_id.isdigit():
                self._game_name_label.setText("")
                return
            self._fetch_game_name_for(place_id)
            return

        if not private:
            self._game_name_label.setText("")
            return

        # Place ID box is empty: resolve a place id from the Private Server
        # Link off the UI thread (the "now" share-link format needs a network call).
        usernames = self._get_selected_usernames()
        cookie = self.manager.accounts.get(usernames[0], {}).get("cookie", "") if usernames else ""

        def _resolve_worker():
            resolved_pid, _ = RobloxAPI.resolve_share_url(private, cookie=cookie)
            if resolved_pid and str(resolved_pid).isdigit():
                self._fetch_game_name_for(str(resolved_pid))
            else:
                self._bridge.game_name_ready.emit("")

        threading.Thread(target=_resolve_worker, daemon=True, name="resolve-current-place").start()

    def _refresh_favorites_dropdown(self):
        current = self._place_id_edit.currentText()
        self._place_id_edit.blockSignals(True)
        self._place_id_edit.clear()
        for fav in favorites_mod.load_favorites():
            place_id = str(fav.get("place_id", ""))
            name = fav.get("name") or place_id
            private_server = fav.get("private_server", "")
            self._place_id_edit.addItem(name, (place_id, private_server))
        self._place_id_edit.setCurrentText(current)
        self._place_id_edit.blockSignals(False)

    def _on_favorite_selected(self, index: int):
        data = self._place_id_edit.itemData(index)
        if not data:
            return
        place_id, private_server = data
        self._place_id_edit.setCurrentText(str(place_id))
        self._private_server_edit.setText(private_server or "")

    def _on_favorite_context_menu(self, pos):
        view = self._place_id_edit.view()
        index = view.indexAt(pos)
        if not index.isValid():
            return
        data = self._place_id_edit.itemData(index.row())
        if not data:
            return
        place_id, private_server = data

        menu = QMenu(self)
        act_remove = menu.addAction("Remove")
        chosen = menu.exec(view.viewport().mapToGlobal(pos))
        if chosen == act_remove:
            favorites_mod.remove_favorite(place_id, private_server)
            self._refresh_favorites_dropdown()
            self._place_id_edit.hidePopup()

    def _on_save_current_game(self):
        place_id = self._place_id_edit.currentText().strip()
        private = self._private_server_edit.text().strip()

        if not place_id and not private:
            _show_error(self, "Missing Place ID", "Enter a Place ID or a Private Server Link first.")
            return

        if place_id:
            self._prompt_save_favorite(place_id, private)
            return

        usernames = self._get_selected_usernames()
        cookie = self.manager.accounts.get(usernames[0], {}).get("cookie", "") if usernames else ""

        def _resolve_worker():
            resolved_pid, _ = RobloxAPI.resolve_share_url(private, cookie=cookie)
            self._bridge.favorite_place_resolved.emit({
                "private": private,
                "effective_place_id": str(resolved_pid) if resolved_pid else "",
            })

        threading.Thread(target=_resolve_worker, daemon=True, name="resolve-save-favorite").start()

    def _on_favorite_place_resolved(self, payload: dict):
        effective_place_id = payload.get("effective_place_id", "")
        if not effective_place_id:
            _show_error(
                self, "Invalid Private Server",
                "Could not resolve a Place ID from the Private Server Link.",
            )
            return
        self._prompt_save_favorite(effective_place_id, payload["private"])

    def _prompt_save_favorite(self, place_id: str, private: str):
        default_name = self._game_name_label.text().replace("Current: ", "").strip() or place_id
        name, ok = QInputDialog.getText(
            self, "Save Current Game", "Name for this favorite:", text=default_name,
        )
        if not ok or not name.strip():
            return

        favorites_mod.add_favorite(place_id, name.strip(), private)
        self._refresh_favorites_dropdown()
        print(f"[SUCCESS] Saved favorite: {name.strip()} (Place {place_id})")

    def _on_add_account_browser(self):
        actions.add_account_browser(
            self.manager,
            on_done=self._on_add_done,
        )

    def _on_import_cookie(self):
        dlg = _ImportCookieDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.cookie_value:
            actions.import_cookie(
                self.manager,
                dlg.cookie_value,
                on_done=self._on_add_done,
            )

    def _on_import_userpass(self):
        dlg = _ImportUserPassDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.pairs:
            actions.import_user_pass(
                self.manager,
                dlg.pairs,
                on_done=self._on_add_done,
            )

    def _on_account_creator(self):
        dlg = _AccountCreatorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            account_creator_mod.create_accounts(
                self.manager,
                dlg.amount,
                options=dlg.options,
                on_done=(
                    lambda success, message:
                    self._bridge.account_creator_done.emit(success, message)
                ),
            )

    def _on_account_creator_done(self, success: bool, message: str):
        if success:
            self._refresh_account_list()
            _show_info(self, "Account Creator", message)
        else:
            _show_error(self, "Account Creator", message)

    def _on_add_javascript(self):
        dlg = _AddJavascriptDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            actions.add_account_browser(
                self.manager,
                on_done=self._on_add_done,
                javascript=dlg.js_value,
            )

    def _on_add_done(self, success: bool, result):
        if isinstance(result, OperationResult):
            operation_result = result
        elif success:
            operation_result = OperationResult.success(str(result or ""))
        else:
            operation_result = OperationResult.failure(
                "ACCOUNT_ADD_FAILED",
                "Account Could Not Be Added",
                str(result or "The account could not be added."),
            )
        self._bridge.account_added.emit(operation_result)

    def _on_add_done_main(self, result):
        operation_result = ensure_result(
            result,
            failure_code="ACCOUNT_ADD_FAILED",
            failure_title="Account Could Not Be Added",
            failure_message="The account could not be added.",
        )
        if operation_result:
            # Auto-refresh the account list
            self._refresh_account_list()
            if operation_result.message:
                _show_info(self, "Account Added", operation_result.message)
        else:
            self._show_operation_error(operation_result)

    def _on_account_reorder(self, from_row: int, insert_before_row: int): # Reoder accounts
        items = list(self.manager.accounts.items())
        if from_row < 0 or from_row >= len(items):
            return

        moved = items.pop(from_row)

        # Adjust target index after removal
        target = insert_before_row
        if insert_before_row > from_row:
            target -= 1
        target = max(0, min(target, len(items)))

        items.insert(target, moved)
        self.manager.accounts = dict(items)

        try:
            self.manager.save_accounts()
        except Exception as e:
            print(f"[WARNING] Could not save account order: {e}")

        self._refresh_account_list()
        print(f"[INFO] Moved '{moved[0]}' to position {target + 1}.")

    # Remove account
    def _on_remove_account(self):
        usernames = self._get_selected_usernames()
        if not usernames:
            _show_error(self, "No selection", "Please select an account to remove.")
            return
        if len(usernames) == 1:
            reply = QMessageBox.question(
                self, "Confirm Removal",
                f"Remove account '{usernames[0]}'? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                ok, msg = actions.remove_account(self.manager, usernames[0])
                if ok:
                    self._refresh_account_list()
                else:
                    _show_error(self, "Error", msg)
        else:
            reply = QMessageBox.question(
                self, "Confirm Removal",
                f"Remove {len(usernames)} accounts? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                for username in usernames:
                    ok, msg = actions.remove_account(self.manager, username)
                    if ok:
                        self._refresh_account_list()
                    else:
                        _show_error(self, "Error", msg)

    # Join Place ID
    def _on_join_place(self):
        usernames = self._get_selected_usernames()
        if not usernames:
            _show_error(self, "No selection", "Please select at least one account first.")
            return
        if not self._guard_invalid(usernames):
            return

        place_id = self._place_id_edit.currentText().strip()
        private = self._private_server_edit.text().strip()

        # Place ID is only required when there's no Private Server Link to
        # resolve a Place ID from - the Place ID inputbox is never rewritten.
        if not place_id and not private:
            _show_error(self, "Missing Place ID", "Enter a Place ID or a Private Server Link.")
            return

        if not self._confirm_launch("Join Place ID", usernames):
            return

        if place_id:
            # Place ID inputbox takes priority over any place id embedded in the link
            self._dispatch_join_place(usernames, place_id, private, place_id)
            return

        cookie = self.manager.accounts.get(usernames[0], {}).get("cookie", "")

        def _resolve_worker():
            resolved_pid, _ = RobloxAPI.resolve_share_url(private, cookie=cookie)
            self._bridge.join_place_resolved.emit({
                "usernames": usernames,
                "private": private,
                "effective_place_id": str(resolved_pid) if resolved_pid else "",
            })

        threading.Thread(target=_resolve_worker, daemon=True, name="resolve-join-place").start()

    def _on_join_place_resolved(self, payload: dict):
        effective_place_id = payload.get("effective_place_id", "")
        if not effective_place_id:
            _show_error(
                self, "Invalid Private Server",
                "Could not resolve a Place ID from the Private Server Link.",
            )
            return
        self._dispatch_join_place(
            payload["usernames"], "", payload["private"], effective_place_id,
        )

    def _dispatch_join_place(self, usernames: list[str], place_id: str, private: str, effective_place_id: str):
        if len(usernames) == 1:
            print(f"[INFO] Joining place {effective_place_id} for {usernames[0]}")
            actions.join_place(
                self.manager, usernames[0], place_id, private,
                on_done=self._emit_launch_done,
            )
        else:
            print(f"[INFO] Joining place {effective_place_id} for {len(usernames)} accounts")
            actions.join_place_all(
                self.manager, usernames, place_id, private,
                on_done=self._emit_launch_done,
            )

        # Fetch the game name fresh instead of trusting the "Current Place" label,
        # which is populated by an independent debounced fetch that may not have
        # finished yet (especially for share links, which need two network calls).
        def _save_recent_worker():
            name = actions.fetch_game_name(effective_place_id)
            actions.save_recent_game(effective_place_id, name, private)
            self._bridge.recent_game_saved.emit()

        threading.Thread(target=_save_recent_worker, daemon=True, name="save-recent-game").start()

    def _on_join_user(self):
        usernames = self._get_selected_usernames()
        if not usernames:
            _show_error(self, "No selection", "Please select at least one account.")
            return

        target_user, ok = QInputDialog.getText(self, "Join User", "Enter the target username to join:")
        if not ok or not target_user.strip():
            return

        if not self._guard_invalid(usernames):
            return

        if not self._confirm_launch("Join User", usernames):
            return

        actions.join_user(
            self.manager,
            usernames,
            target_user.strip(),
            on_done=self._emit_launch_done
        )

    def _on_join_job_id(self):
        usernames = self._get_selected_usernames()
        if not usernames:
            _show_error(self, "No selection", "Please select at least one account.")
            return

        place_id = self._place_id_edit.currentText().strip()
        if not place_id:
            _show_error(self, "Missing Info", "Please enter a Place ID first.")
            return

        job_id, ok = QInputDialog.getText(self, "Join by Job ID", "Enter the Job ID (Game ID):")
        if not ok or not job_id.strip():
            return

        if not self._guard_invalid(usernames):
            return

        if not self._confirm_launch("Join by Job ID", usernames):
            return

        actions.join_job_id(
            self.manager,
            usernames,
            place_id,
            job_id.strip(),
            on_done=self._emit_launch_done
        )

    def _on_join_small_server(self):
        usernames = self._get_selected_usernames()
        if not usernames:
            _show_error(self, "No selection", "Please select at least one account.")
            return

        place_id = self._place_id_edit.currentText().strip()
        if not place_id:
            _show_error(self, "Missing Info", "Please enter a Place ID first.")
            return

        if not self._guard_invalid(usernames):
            return

        if not self._confirm_launch("Join Small Server", usernames):
            return

        actions.join_small_server(
            self.manager,
            usernames,
            place_id,
            on_done=self._emit_launch_done
        )

    # Edit Note
    def _on_edit_note(self):
        usernames = self._get_selected_usernames()
        if not usernames:
            _show_error(self, "No selection", "Please select at least one account first.")
            return
        # Use first selected username as the dialog reference
        first = usernames[0]
        current = actions.get_note(self.manager, first) if len(usernames) == 1 else ""
        dlg = _EditNoteDialog(first if len(usernames) == 1 else f"{len(usernames)} accounts", current, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            for u in usernames:
                actions.set_note(self.manager, u, dlg.note_value)
            print(f"[INFO] Note updated for {len(usernames)} account(s)")
            self._refresh_account_list()

    # Launch Roblox Home
    def _on_launch_home(self):
        username = self._get_selected_username()
        if not username:
            _show_error(self, "No selection", "Please select an account first.")
            return
        if not self._guard_invalid([username]):
            return
        if not self._confirm_launch("Launch Roblox Home", [username]):
            return
        print(f"[INFO] Launching Roblox Home for {username}")
        actions.launch_home(
            self.manager, username,
            on_done=self._emit_launch_done,
        )

    def _emit_launch_done(self, success: bool, result):
        if isinstance(result, OperationResult):
            operation_result = result
        elif success:
            operation_result = OperationResult.success(str(result or ""))
        else:
            operation_result = OperationResult.failure(
                "ROBLOX_LAUNCH_FAILED",
                "Roblox Could Not Start",
                str(result or "Roblox could not be launched."),
            )
        self._bridge.launch_done.emit(operation_result)

    def _on_launch_and_refresh(self, result):
        self._refresh_recent_games()
        operation_result = ensure_result(
            result,
            failure_code="ROBLOX_LAUNCH_FAILED",
            failure_title="Roblox Could Not Start",
            failure_message="Roblox could not be launched.",
        )
        if not operation_result:
            self._show_operation_error(operation_result)

    def _operation_error_message_text(self, result: OperationResult) -> str:
        lines = [
            result.title or "Operation Failed",
            result.message or "The operation could not be completed.",
        ]
        if result.code:
            lines.append(f"Error code: {result.code}")
        if result.detail:
            lines.extend([
                "",
                "Technical details:",
                diagnostics.redact(result.detail),
            ])
        return "\n".join(lines)

    @staticmethod
    def _session_log_copy_text() -> str:
        diagnostics.flush_session_log()
        session_log = diagnostics.get_session_log_path()
        if not session_log:
            return "The session log is unavailable."
        try:
            with open(session_log, "r", encoding="utf-8") as handle:
                return handle.read()
        except Exception as exc:
            return (
                f"Failed to read the session log.\n"
                f"Path: {session_log}\n"
                f"Error: {type(exc).__name__}: {exc}"
            )

    def _show_operation_error(self, result: OperationResult) -> None:
        now = time.monotonic()
        key = f"{result.code}|{result.title}|{result.message}"
        if self._last_operation_error[0] == key and now - self._last_operation_error[1] < 3:
            return
        self._last_operation_error = (key, now)

        dlg = QMessageBox(self)
        dlg.setWindowTitle(result.title or "Operation Failed")
        dlg.setText(result.message or "The operation could not be completed.")
        information = []
        if result.code:
            information.append(f"Error code: {result.code}")
        if result.code == "UNEXPECTED_ERROR":
            information.append(
                f"Session log: {diagnostics.get_session_log_path()}"
            )
        if information:
            dlg.setInformativeText("\n".join(information))
        if result.detail:
            dlg.setDetailedText(diagnostics.redact(result.detail))
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
        dlg.setDefaultButton(QMessageBox.StandardButton.Ok)
        ok_button = dlg.button(QMessageBox.StandardButton.Ok)
        if ok_button:
            dlg.setEscapeButton(ok_button)

        error_text = self._operation_error_message_text(result)
        copy_error_button = dlg.addButton(
            "Copy Error Message",
            QMessageBox.ButtonRole.ActionRole,
        )
        copy_error_button.clicked.disconnect()
        copy_error_button.clicked.connect(
            lambda: QApplication.clipboard().setText(error_text)
        )

        copy_log_button = dlg.addButton(
            "Copy Full Log",
            QMessageBox.ButtonRole.ActionRole,
        )
        copy_log_button.clicked.disconnect()
        copy_log_button.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self._session_log_copy_text()
            )
        )
        dlg.setStyleSheet(f"QMessageBox {{ background: {BG}; color: {TEXT}; }}")
        dlg.exec()

    # Right-click context menu on account list
    def _on_account_context_menu(self, pos):
        item = self._account_list.itemAt(pos)
        if item is None:
            return
        username = item.data(Qt.ItemDataRole.UserRole)
        if not username:
            return

        if username not in self._get_selected_usernames():
            self._account_list.setCurrentItem(item)

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {PANEL}; border: 1px solid {LINE};"
            f"  color: {TEXT}; font-size: 11px; }}"
            f"QMenu::item:selected {{ background: {SELECT}; }}"
            f"QMenu::item:disabled {{ color: {MUTED}; }}"
        )

        S = actions.load_ui_settings()
        multi_sel = self._get_selected_usernames()
        is_multi = len(multi_sel) > 1

        act_join = menu.addAction("Join Place ID")
        act_note = menu.addAction("Edit Note")
        menu.addSeparator()

        # Copy Contents submenu
        copy_menu = menu.addMenu("Copy Contents")
        copy_menu.setStyleSheet(
            f"QMenu {{ background: {PANEL}; border: 1px solid {LINE};"
            f"  color: {TEXT}; font-size: 11px; }}"
            f"QMenu::item:selected {{ background: {SELECT}; }}"
        )
        act_copy_user = copy_menu.addAction("Copy Username")
        act_copy_pass = copy_menu.addAction("Copy Password")
        act_copy_up = copy_menu.addAction("Copy User:Pass")
        copy_cookie_enabled = S.get("enable_copy_cookie", False)
        act_copy_cookie = copy_menu.addAction("Copy Cookie")
        act_copy_cookie.setEnabled(copy_cookie_enabled)

        menu.addSeparator()

        move_menu = menu.addMenu("Move to Group")
        move_menu.setStyleSheet(
            f"QMenu {{ background: {PANEL}; border: 1px solid {LINE};"
            f"  color: {TEXT}; font-size: 11px; }}"
            f"QMenu::item:selected {{ background: {SELECT}; }}"
        )
        group_list = groups.get_group_names()
        usernames = self._get_selected_usernames()

        if group_list:
            for gname in group_list:
                act_grp = move_menu.addAction(gname)
                act_grp.triggered.connect(
                    lambda _=False, users=list(usernames), g=gname:
                        self._on_assign_to_group(users, g)
                )
        move_menu.addSeparator()
        act_ungrp = move_menu.addAction("Remove from Group")
        usernames = self._get_selected_usernames()

        act_ungrp.triggered.connect(
            lambda _=False, users=list(usernames): self._on_remove_from_group(users)
        )

        menu.addSeparator()
        act_remove = menu.addAction("Remove Account")

        chosen = menu.exec(self._account_list.mapToGlobal(pos))
        if chosen == act_join:
            self._on_join_place()
        elif chosen == act_note:
            self._on_edit_note()
        elif chosen == act_remove:
            self._on_remove_account()
        elif chosen in (act_copy_user, act_copy_pass, act_copy_up, act_copy_cookie):
            self._on_copy_contents(chosen, act_copy_user, act_copy_pass, act_copy_up, act_copy_cookie, username, is_multi, multi_sel)

    def _on_copy_contents(self, chosen, act_user, act_pass, act_up, act_cookie, username: str, is_multi: bool, multi_sel):
        def _get_data(u):
            d = self.manager.accounts.get(u, {})
            return {"username": u, "password": d.get("password", ""), "cookie": d.get("cookie", "")}
        targets = multi_sel if is_multi else [username]
        if chosen == act_user:
            field, fmt = "username", lambda d: d["username"]
        elif chosen == act_pass:
            field, fmt = "password", lambda d: d["password"]
        elif chosen == act_up:
            field, fmt = "user_pass", lambda d: d["username"] + ":" + d["password"]
        else:
            field, fmt = "cookie", lambda d: d["cookie"]
        lines = [fmt(_get_data(u)) for u in targets]
        if is_multi:
            filter_str = "Text Files (*.txt);;All Files (*)"
            default_name = "export_" + field + ".txt"
            path2, _ = QFileDialog.getSaveFileName(self, "Save Export", default_name, filter_str)
            if path2:
                try:
                    with open(path2, "w", encoding="utf-8") as fp:
                        fp.write("\n".join(lines))
                    print("[SUCCESS] Exported " + str(len(lines)) + " entries to " + os.path.basename(path2))
                    QMessageBox.information(self, "Export Done",
                        "Exported " + str(len(lines)) + " account(s) to:\n" + path2)
                except Exception as e:
                    print("[ERROR] Export failed: " + str(e))
        else:
            QApplication.clipboard().setText(lines[0] if lines else "")
            print("[INFO] Copied " + field + " for " + username + " to clipboard")

    def _drain_console_queue(self):
        q = getattr(self, "_console_queue", None)
        if not q:
            return
        widget = getattr(self, "_console_view", None)
        if widget is None:
            return
        batch: list[tuple[str, str | None]] = []
        for _ in range(50):
            try:
                batch.append(q.popleft())
            except IndexError:
                break
        if not batch:
            return
        cursor = widget.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        for text, color in batch:
            fmt = QTextCharFormat()
            if color:
                fmt.setForeground(QColor(color))
            else:
                fmt.clearForeground()
            cursor.setCharFormat(fmt)
            cursor.insertText(text + "\n")
        widget.setTextCursor(cursor)
        widget.ensureCursorVisible()
        if q:
            QTimer.singleShot(0, self._drain_console_queue)

    _DONATION_URL = "https://www.roblox.com/games/718090786/donation#!/store"
    _DONATION_USERNAME = "evedkdmdj"

    def _build_donations_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("settingsPanel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("donationCard")
        card.setStyleSheet(f"""
            #donationCard {{
                background: {PANEL};
                border: 1px solid {LINE};
                border-radius: 10px;
            }}
        """)
        card.setMaximumWidth(420)
        card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(32, 32, 32, 32)
        card_lay.setSpacing(18)
        card_lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)


        title_lbl = QLabel("Support the Creator")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {TEXT}; background: transparent;"
        )
        card_lay.addWidget(title_lbl)

        desc_lbl = QLabel("Support the creator by donating via Robux!")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"font-size: 11px; color: {MUTED}; background: transparent;"
        )
        card_lay.addWidget(desc_lbl)

        copy_btn = QPushButton("Copy Link")
        copy_btn.setFixedHeight(34)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {FG_ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #1a8fe0;
            }}
            QPushButton:pressed {{
                background: #006dc4;
            }}
        """)

        def _copy_link():
            QApplication.clipboard().setText(self._DONATION_URL)
            copy_btn.setText("Copied!")
            QTimer.singleShot(2000, lambda: copy_btn.setText("Copy Link"))

        copy_btn.clicked.connect(_copy_link)
        card_lay.addWidget(copy_btn)

        plus_lbl = QLabel("Or donate robux via plus")
        plus_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        plus_lbl.setWordWrap(True)
        plus_lbl.setStyleSheet(
            f"font-size: 11px; color: {MUTED}; background: transparent;"
        )
        card_lay.addWidget(plus_lbl)

        copy_user_btn = QPushButton("Copy Username")
        copy_user_btn.setFixedHeight(34)
        copy_user_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_user_btn.setStyleSheet(f"""
            QPushButton {{
                background: {FG_ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #1a8fe0;
            }}
            QPushButton:pressed {{
                background: #006dc4;
            }}
        """)

        def _copy_username():
            QApplication.clipboard().setText(self._DONATION_USERNAME)
            copy_user_btn.setText("Copied!")
            QTimer.singleShot(2000, lambda: copy_user_btn.setText("Copy Username"))

        copy_user_btn.clicked.connect(_copy_username)
        card_lay.addWidget(copy_user_btn)

        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(card)
        h.addStretch(1)
        outer.addLayout(h)

        outer.addStretch(1)
        return panel

    def _build_console_panel(self) -> QFrame: # Console panel
        panel = QFrame()
        panel.setObjectName("centerPanel")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        ttl = QLabel("Console")
        ttl.setObjectName("sectionTitle")
        hdr.addWidget(ttl)
        hdr.addStretch(1)
        lay.addLayout(hdr)

        self._console_view = QTextEdit()
        self._console_view.setReadOnly(True)
        self._console_view.document().setMaximumBlockCount(3000)
        self._console_view.setStyleSheet(
            f"QTextEdit {{"
            f"  background: {INPUT};"
            f"  border: 1px solid {LINE};"
            f"  color: {TEXT};"
            f"  font-family: Consolas, 'Courier New', monospace;"
            f"  font-size: 11px;"
            f"  padding: 4px;"
            f"}}"
        )
        lay.addWidget(self._console_view, 1)

        _BTN_STYLE = (
            f"QPushButton {{"
            f"  background: {INPUT}; border: 1px solid {LINE};"
            f"  color: {TEXT}; font-size: 11px; min-height: 26px; padding: 2px 8px;"
            f"}}"
            f"QPushButton:hover   {{ background: {SELECT}; }}"
            f"QPushButton:pressed {{ background: {SELECT}; }}"
        )
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(0, 0, 0, 0)

        copy_btn = QPushButton("Copy")
        copy_btn.setStyleSheet(_BTN_STYLE)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(
            self._console_view.toPlainText()
        ))
        btn_row.addWidget(copy_btn)

        clr_btn = QPushButton("Clear")
        clr_btn.setStyleSheet(_BTN_STYLE)
        clr_btn.clicked.connect(self._console_view.clear)
        btn_row.addWidget(clr_btn)

        lay.addLayout(btn_row)

        return panel

# Dialogs
_DLG_STYLE = f"""
    QDialog   {{ background: {BG}; }}
    QLabel    {{ color: {TEXT}; font-size: 11px; }}
    QLineEdit {{ background: {INPUT}; border: 1px solid {LINE};
                color: {TEXT}; padding: 4px 6px; min-height: 24px; }}
    QTextEdit {{ background: {INPUT}; border: 1px solid {LINE};
                color: {TEXT}; font-family: Consolas, monospace; font-size: 11px; }}
    QPushButton {{
        background: {INPUT}; border: 1px solid {LINE};
        color: {TEXT}; min-height: 26px; padding: 2px 12px; font-size: 11px;
    }}
    QPushButton:hover   {{ background: {SELECT}; }}
    QPushButton:pressed {{ background: {SELECT}; }}
"""


class _ImportCookieDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.cookie_value = ""
        self.setWindowTitle("Import Cookie")
        self.setFixedSize(480, 200)
        self.setStyleSheet(_DLG_STYLE)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel("Import Account from Cookie"))
        lay.addWidget(QLabel("Paste one or more .ROBLOSECURITY cookie(s) below:"))

        self._text = QTextEdit()
        self._text.setPlaceholderText("_|WARNING:-Cookie1 _|WARNING:-Cookie2")
        self._text.setFixedHeight(70)
        lay.addWidget(self._text)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Import")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._accept)
        cn_btn = QPushButton("Cancel")
        cn_btn.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cn_btn)
        lay.addLayout(btn_row)

    def _accept(self):
        self.cookie_value = self._text.toPlainText().strip()
        if self.cookie_value:
            self.accept()

class _AccountCreatorDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.amount = 1
        self.options: dict = {}
        self.setWindowTitle("Account Creator")
        self.setFixedSize(540, 320)
        self.setStyleSheet(_DLG_STYLE + f"""
            QTabWidget::pane {{
                background: {PANEL};
                border: 1px solid {LINE};
                border-radius: 0;
            }}
            QTabBar::tab {{
                background: {INPUT};
                color: {MUTED};
                border: 1px solid {LINE};
                border-bottom: none;
                border-radius: 0;
                min-width: 80px;
                min-height: 24px;
                padding: 2px 10px;
            }}
            QTabBar::tab:selected {{
                background: {SELECT};
                color: {TEXT};
            }}
            QSpinBox {{
                background: {INPUT};
                color: {TEXT};
                border: 1px solid {LINE};
                border-radius: 0;
                min-height: 24px;
                padding: 2px 6px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel("Create Roblox Accounts")
        title.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 700;")
        lay.addWidget(title)

        warning = QLabel(
            "CAPTCHAs must be completed manually. This program does not "
            "bypass Roblox CAPTCHA protection."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(f"color: {NOTE}; font-size: 10px;")
        lay.addWidget(warning)

        tabs = QTabWidget()

        basic_page = QWidget()
        basic_lay = QVBoxLayout(basic_page)
        basic_lay.setContentsMargins(12, 12, 12, 12)
        basic_lay.setSpacing(8)

        amount_row = QHBoxLayout()
        amount_label = QLabel("Amount of Accounts")
        amount_label.setToolTip(
            "Create between 1 and 100 accounts.\n"
            "No more than 5 browsers are open at the same time."
        )
        amount_row.addWidget(amount_label)
        amount_row.addStretch(1)
        self._amount_spin = QSpinBox()
        self._amount_spin.setRange(1, account_creator_mod.MAX_CREATOR_ACCOUNTS)
        self._amount_spin.setValue(1)
        self._amount_spin.setFixedWidth(70)
        self._amount_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        amount_row.addWidget(self._amount_spin)
        basic_lay.addLayout(amount_row)
        basic_lay.addStretch(1)
        tabs.addTab(basic_page, "Basic")

        advanced_page = QWidget()
        advanced_lay = QVBoxLayout(advanced_page)
        advanced_lay.setContentsMargins(12, 12, 12, 12)
        advanced_lay.setSpacing(8)

        advanced_desc = QLabel("Optionally add your own prefix and set one password for every created account. Max 14 characters.")
        advanced_desc.setWordWrap(True)
        advanced_desc.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        advanced_desc.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        advanced_desc.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        advanced_lay.addWidget(advanced_desc)

        self._enable_prefix_chk = QCheckBox("Enable Custom Prefix")
        self._enable_prefix_chk.setChecked(False)
        advanced_lay.addWidget(self._enable_prefix_chk)

        prefix_row = QHBoxLayout()
        prefix_label = QLabel("Custom Prefix")
        prefix_label.setFixedWidth(105)
        prefix_row.addWidget(prefix_label)
        self._username_prefix_edit = QLineEdit()
        self._username_prefix_edit.setPlaceholderText("Example: alts_")
        self._username_prefix_edit.setMaxLength(
            account_creator_mod.MAX_PREFIX_LENGTH
        )
        self._username_prefix_edit.setEnabled(False)
        prefix_row.addWidget(self._username_prefix_edit, 1)
        advanced_lay.addLayout(prefix_row)

        password_row = QHBoxLayout()
        password_label = QLabel("Set Password")
        password_label.setFixedWidth(105)
        password_row.addWidget(password_label)
        self._creator_password_edit = QLineEdit()
        self._creator_password_edit.setPlaceholderText(
            "Leave blank to generate a password for each account"
        )
        self._creator_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_row.addWidget(self._creator_password_edit, 1)
        advanced_lay.addLayout(password_row)
        advanced_lay.addStretch(1)

        self._enable_prefix_chk.toggled.connect(
            self._username_prefix_edit.setEnabled
        )
        tabs.addTab(advanced_page, "Advanced")

        lay.addWidget(tabs, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        create_btn = QPushButton("Create Accounts")
        create_btn.setDefault(True)
        create_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(create_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    def _accept(self):
        enable_custom_prefix = self._enable_prefix_chk.isChecked()
        prefix = self._username_prefix_edit.text().strip()
        if (
            enable_custom_prefix
            and not account_creator_mod.is_valid_prefix(prefix)
        ):
            _show_error(
                self,
                "Invalid Prefix",
                "The prefix must only contain letters, numbers, and _. "
                "It cannot start with _.\n\n"
                "Roblox account creation was not launched.",
            )
            return

        password = self._creator_password_edit.text()
        if password and len(password) < 8:
            _show_error(
                self,
                "Invalid Password",
                "The custom password must contain at least 8 characters.",
            )
            return

        self.amount = self._amount_spin.value()
        self.options = {
            "enable_custom_prefix": enable_custom_prefix,
            "prefix": prefix,
            "password": password,
        }
        self.accept()


class _ImportUserPassDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.pairs: list[tuple[str, str]] = []
        self._row_widgets: list[tuple[QLineEdit, QLineEdit, QWidget]] = []
        self.setWindowTitle("Import User:Pass")
        self.setFixedSize(460, 380)
        self.setStyleSheet(_DLG_STYLE)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel("Import Accounts from Username:Password"))
        desc = QLabel("Enter one account per row, or import a .txt file of Username:Password lines.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        lay.addWidget(desc)

        self._rows_scroll = QScrollArea()
        self._rows_scroll.setWidgetResizable(True)
        self._rows_scroll.setFrameShape(QFrame.Shape.NoFrame)
        rows_widget = QWidget()
        self._rows_lay = QVBoxLayout(rows_widget)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(6)
        self._rows_lay.addStretch(1)
        self._rows_scroll.setWidget(rows_widget)
        lay.addWidget(self._rows_scroll, 1)

        self._add_row()

        btn_row = QHBoxLayout()
        file_btn = QPushButton("Import from .txt")
        file_btn.clicked.connect(self._on_import_file)
        btn_row.addWidget(file_btn)
        btn_row.addStretch(1)
        ok_btn = QPushButton("Import")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._accept)
        cn_btn = QPushButton("Cancel")
        cn_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cn_btn)
        lay.addLayout(btn_row)

    def _add_row(self, username: str = "", password: str = ""):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        user_edit = QLineEdit()
        user_edit.setPlaceholderText("Username")
        user_edit.setText(username)
        pass_edit = QLineEdit()
        pass_edit.setPlaceholderText("Password")
        pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pass_edit.setText(password)

        row.addWidget(user_edit, 1)
        row.addWidget(pass_edit, 1)

        row_widget = QWidget()
        row_widget.setLayout(row)
        self._rows_lay.insertWidget(self._rows_lay.count() - 1, row_widget)
        self._row_widgets.append((user_edit, pass_edit, row_widget))
        user_edit.textChanged.connect(lambda text, ue=user_edit: self._on_row_username_typed(ue, text))

    def _remove_row(self, index: int):
        _, _, row_widget = self._row_widgets.pop(index)
        self._rows_lay.removeWidget(row_widget)
        row_widget.setParent(None)
        row_widget.deleteLater()

    def _on_row_username_typed(self, user_edit: QLineEdit, text: str):
        idx = next((i for i, (u, _, _) in enumerate(self._row_widgets) if u is user_edit), None)
        if idx is None:
            return
        is_last = idx == len(self._row_widgets) - 1

        if text.strip():
            if is_last:
                self._add_row()
        else:
            if not is_last and idx == len(self._row_widgets) - 2:
                last_user, last_pass, _ = self._row_widgets[-1]
                if not last_user.text().strip() and not last_pass.text().strip():
                    self._remove_row(len(self._row_widgets) - 1)

    def _on_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import User:Pass File", "", "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        pairs = actions.parse_user_pass_file(path)
        if not pairs:
            _show_error(self, "No accounts found", "No valid Username:Password lines were found in that file.")
            return
        for username, password in pairs:
            self._add_row(username, password)
        self._add_row()

    def _accept(self):
        pairs: list[tuple[str, str]] = []
        for user_edit, pass_edit, _ in self._row_widgets:
            username = user_edit.text().strip()
            password = pass_edit.text()
            if username and password:
                pairs.append((username, password))
        if not pairs:
            _show_error(self, "Missing Info", "Enter at least one Username:Password pair.")
            return
        self.pairs = pairs
        self.accept()


class _AddJavascriptDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.js_value = ""
        self.setWindowTitle("Add via Javascript")
        self.setFixedSize(480, 260)
        self.setStyleSheet(_DLG_STYLE)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel(
            "A browser will open for login.\n"
            "Optionally paste Javascript to execute after the page loads:"
        ))

        self._edit = QTextEdit()
        self._edit.setPlaceholderText("// optional JS\nconsole.log('hello');")
        lay.addWidget(self._edit, 1)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Open Browser")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._accept)
        cn_btn = QPushButton("Cancel")
        cn_btn.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cn_btn)
        lay.addLayout(btn_row)

    def _accept(self):
        self.js_value = self._edit.toPlainText()
        self.accept()


class _EditNoteDialog(QDialog):
    def __init__(self, username: str, current_note: str, parent):
        super().__init__(parent)
        self.note_value = current_note
        self.setWindowTitle(f"Edit Note - {username}")
        self.setFixedSize(380, 150)
        self.setStyleSheet(_DLG_STYLE)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel(f"Note for {username}:"))

        self._entry = QLineEdit(current_note)
        self._entry.setPlaceholderText("Enter a note…")
        lay.addWidget(self._entry)

        btn_row = QHBoxLayout()
        clr_btn = QPushButton("Clear")
        clr_btn.clicked.connect(self._entry.clear)
        ok_btn = QPushButton("Save")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._accept)
        cn_btn = QPushButton("Cancel")
        cn_btn.clicked.connect(self.reject)
        btn_row.addWidget(clr_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cn_btn)
        lay.addLayout(btn_row)

    def _accept(self):
        self.note_value = self._entry.text()
        self.accept()


class _AutoRejoinAddWindow(QDialog):
    # Panel for adding accounts to auto rejoin and edit accounts
    # Left side: List of accounts
    # Right side: config form
    def __init__(self, manager, parent=None, edit_account=None, edit_config=None):
        super().__init__(parent)
        self.manager = manager
        self.result_configs: dict = {}
        self._edit_mode = edit_account is not None
        self._edit_account = edit_account
        self._edit_config = edit_config or {}

        self.setWindowTitle("Edit Auto-Rejoin" if self._edit_mode else "Add Account to Auto-Rejoin")
        # Size to tweak i keep forgetting
        # the 225 one is for edit
        # the other one is for add
        self.setFixedSize(225 if self._edit_mode else 550, 420)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(_DLG_STYLE + f"""
            QListWidget {{
                background: {INPUT}; border: 1px solid {LINE};
                font-size: 11px; color: {TEXT};
            }}
            QListWidget::item:selected {{ background: {SELECT}; }}
            QPushButton#groupTab {{
                background: transparent; border: 1px solid {LINE};
                color: {MUTED}; font-size: 10px; padding: 2px 8px;
                min-height: 20px;
            }}
            QPushButton#groupTab:checked {{ background: {SELECT}; color: {TEXT}; }}
            QPushButton#groupTab:hover   {{ background: {SELECT}; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        # Title bar row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("Edit Auto-Rejoin" if self._edit_mode else "Add Account to Auto-Rejoin")
        lbl.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        title_row.addWidget(lbl)
        title_row.addStretch(1)
        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {MUTED}; font-size: 13px; }}"
            f"QPushButton:hover {{ color: {TEXT}; }}"
        )
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # Sub-title hint directly below the title
        self._hint_label = QLabel("Ctrl / Shift to select multiple accounts")
        self._hint_label.setStyleSheet(f"color: {MUTED}; font-size: 9px;")
        root.addWidget(self._hint_label)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)

        # Left side
        self._left_widget = QWidget()
        left = QVBoxLayout(self._left_widget)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(4)

        self._current_group: str | None = None

        # Group scroll bar
        self._gscroll = QScrollArea()
        self._gscroll.setWidgetResizable(True)
        self._gscroll.setFixedHeight(28)
        self._gscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._gscroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gscroll.setStyleSheet("background: transparent; border: none;")

        _gbar_widget = QWidget()
        _gbar_widget.setStyleSheet("background: transparent;")
        self._gbar_lay = QHBoxLayout(_gbar_widget)
        self._gbar_lay.setContentsMargins(0, 0, 0, 0)
        self._gbar_lay.setSpacing(4)
        self._gscroll.setWidget(_gbar_widget)
        left.addWidget(self._gscroll)

        self._acc_list = QListWidget()
        self._acc_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        left.addWidget(self._acc_list, 1)

        body.addWidget(self._left_widget, 1)

        # Right side
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)

        _LBL = f"color: {MUTED}; font-size: 10px;"
        _INP = (
            f"QLineEdit {{ background: {INPUT}; border: 1px solid {LINE};"
            f" color: {TEXT}; padding: 3px 5px; font-size: 11px; }}"
        )
        _SPN = (
            f"QSpinBox {{ background: {INPUT}; border: 1px solid {LINE};"
            f" color: {TEXT}; padding: 2px 4px; font-size: 11px; }}"
        )
        _CHK = (
            f"QCheckBox {{ color: {TEXT}; font-size: 11px; }}"
            f"QCheckBox::indicator {{ width: 13px; height: 13px; }}"
        )

        cfg_hdr = QLabel("Configuration")
        cfg_hdr.setStyleSheet(f"color: {TEXT}; font-size: 11px; font-weight: bold;")
        right.addWidget(cfg_hdr)

        # Account label for edit mode
        self._account_lbl = QLabel()
        self._account_lbl.setStyleSheet(f"color: {TEXT}; font-size: 11px; font-weight: bold;")
        right.addWidget(self._account_lbl)

        right.addWidget(QLabel("Place ID:", styleSheet=_LBL))
        self._place = QLineEdit()
        self._place.setPlaceholderText("e.g. 8562822414")
        self._place.setStyleSheet(_INP)
        self._place.setFixedWidth(200)
        right.addWidget(self._place)

        right.addWidget(QLabel("Private Server ID:", styleSheet=_LBL))
        self._ps = QLineEdit()
        self._ps.setPlaceholderText("optional")
        self._ps.setStyleSheet(_INP)
        self._ps.setFixedWidth(200)
        right.addWidget(self._ps)

        right.addWidget(QLabel("Job ID:", styleSheet=_LBL))
        self._job = QLineEdit()
        self._job.setPlaceholderText("optional")
        self._job.setStyleSheet(_INP)
        self._job.setFixedWidth(200)
        right.addWidget(self._job)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Interval:", styleSheet=_LBL))
        self._interval = QSpinBox()
        self._interval.setRange(5, 300)
        self._interval.setValue(10)
        self._interval.setSingleStep(5)
        self._interval.setSuffix(" s")
        self._interval.setStyleSheet(_SPN)
        self._interval.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row1.addWidget(self._interval)
        right.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Retries:", styleSheet=_LBL))
        self._retries = QSpinBox()
        self._retries.setRange(1, 50)
        self._retries.setValue(5)
        self._retries.setStyleSheet(_SPN)
        self._retries.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row2.addWidget(self._retries)
        right.addLayout(row2)

        self._presence_chk = QCheckBox("Check player presence")
        self._presence_chk.setChecked(True)
        self._presence_chk.setStyleSheet(_CHK)
        right.addWidget(self._presence_chk)

        self._internet_chk = QCheckBox("Check internet before launch")
        self._internet_chk.setChecked(True)
        self._internet_chk.setStyleSheet(_CHK)
        right.addWidget(self._internet_chk)

        right.addStretch(1)

        # Save changes if edit mode
        # Add account if add mode
        self._add_btn = QPushButton("Save Changes" if self._edit_mode else "Add Account")
        self._add_btn.setFixedHeight(30)
        self._add_btn.setFixedWidth(200)
        self._add_btn.setStyleSheet(
            f"QPushButton {{ background: {SELECT}; border: 1px solid {LINE};"
            f"  min-height: 30px; font-weight: 700; text-align: center; color: {TEXT}; }}"
            f"QPushButton:hover   {{ background: #3A3A3A; }}"
            f"QPushButton:pressed {{ background: #1E1E1E; }}"
        )
        self._add_btn.clicked.connect(self._on_add)
        right.addWidget(self._add_btn)

        body.addLayout(right)
        root.addLayout(body, 1)

        if self._edit_mode:
            self._apply_edit_mode()
        else:
            self._rebuild_group_bar()
            self._populate_list()

    def _apply_edit_mode(self):
        # Hide left panel for single account editing
        self._left_widget.hide()
        self._hint_label.hide()
        self._account_lbl.hide()

        # Pre-fill config values for the account being edited
        cfg = self._edit_config
        self._place.setText(cfg.get("place_id", ""))
        self._ps.setText(cfg.get("private_server", ""))
        self._job.setText(cfg.get("job_id", ""))
        self._interval.setValue(int(cfg.get("check_interval", 10)))
        self._retries.setValue(int(cfg.get("max_retries", 5)))
        self._presence_chk.setChecked(bool(cfg.get("check_presence", True)))
        self._internet_chk.setChecked(bool(cfg.get("check_internet", True)))

    def _rebuild_group_bar(self):
        while self._gbar_lay.count():
            child = self._gbar_lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for gval, glabel in [(None, "All")] + [(g, g) for g in groups.get_group_names()]:
            btn = QPushButton(glabel)
            btn.setObjectName("groupTab")
            btn.setCheckable(True)
            btn.setChecked(self._current_group == gval)
            btn.clicked.connect(lambda _=False, g=gval: self._set_group(g))
            self._gbar_lay.addWidget(btn)
        self._gbar_lay.addStretch(1)

    def _set_group(self, group_name):
        self._current_group = group_name
        self._rebuild_group_bar()
        self._populate_list()
    
    # Account list population
    def _populate_list(self):
        self._acc_list.clear()
        AV = avatars.AVATAR_SIZE
        ITEM_H = AV + 6

        items = list(self.manager.accounts.items())
        if self._current_group is not None:
            items = [(u, d) for u, d in items if groups.get_account_group(u) == self._current_group]

        for username, data in items:
            note = data.get("note", "") if isinstance(data, dict) else ""
            item = QListWidgetItem("")
            item.setSizeHint(QSize(0, ITEM_H))
            item.setData(Qt.ItemDataRole.UserRole, username)

            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 0, 6, 0)
            rl.setSpacing(6)

            # Avatar
            av = QLabel()
            av.setFixedSize(AV, AV)
            av.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)

            # Use cached pixmap from main account list
            par = self.parent()
            cached_pix = None
            if par and hasattr(par, "_avatar_labels"):
                src_lbl = par._avatar_labels.get(username)
                if src_lbl:
                    cached_pix = src_lbl.pixmap()
            if cached_pix and not cached_pix.isNull():
                av.setPixmap(cached_pix)
            else:
                if par and hasattr(par, "_make_placeholder_pixmap"):
                    av.setPixmap(par._make_placeholder_pixmap(AV))
            rl.addWidget(av)

            name_lbl = QLabel(username)
            name_lbl.setObjectName("accountName")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            rl.addWidget(name_lbl)

            if note:
                sep = QLabel("|")
                sep.setObjectName("noteSep")
                sep.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                rl.addWidget(sep)
                note_lbl = QLabel(note)
                note_lbl.setObjectName("noteText")
                note_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                rl.addWidget(note_lbl)

            rl.addStretch(1)
            row.setFixedHeight(ITEM_H)

            self._acc_list.addItem(item)
            self._acc_list.setItemWidget(item, row)

    def _on_add(self):
        place_id = self._place.text().strip()
        if not place_id:
            QMessageBox.warning(self, "Missing Place ID", "Enter a Place ID to monitor.")
            return
        if not place_id.isdigit():
            QMessageBox.critical(self, "Invalid Place ID", "Place ID must be a number.")
            return

        cfg = {
            "place_id": place_id,
            "private_server": self._ps.text().strip(),
            "job_id": self._job.text().strip(),
            "check_interval": self._interval.value(),
            "max_retries": self._retries.value(),
            "check_presence": self._presence_chk.isChecked(),
            "check_internet": self._internet_chk.isChecked(),
        }

        if self._edit_mode:
            self.result_configs[self._edit_account] = cfg
        else:
            # In add mode, require account selection
            selected = [
                self._acc_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self._acc_list.count())
                if self._acc_list.item(i).isSelected()
            ]
            if not selected:
                QMessageBox.warning(self, "No Selection", "Select at least one account from the list.")
                return
            for account in selected:
                self.result_configs[account] = cfg.copy()
        self.accept()

# Tiny message helpers
def _show_error(parent, title: str, msg: str):
    if not msg:
        return
    dlg = QMessageBox(parent)
    dlg.setWindowTitle(title)
    dlg.setText(msg)
    dlg.setIcon(QMessageBox.Icon.Critical)
    dlg.setStyleSheet(f"QMessageBox {{ background: {BG}; color: {TEXT}; }}")
    dlg.exec()


def _show_info(parent, title: str, msg: str):
    dlg = QMessageBox(parent)
    dlg.setWindowTitle(title)
    dlg.setText(msg)
    dlg.setIcon(QMessageBox.Icon.Information)
    dlg.setStyleSheet(f"QMessageBox {{ background: {BG}; color: {TEXT}; }}")
    dlg.exec()


# Palette
def apply_palette(app: QApplication) -> None:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(BG))
    p.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Base, QColor(INPUT))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL))
    p.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Button, QColor(INPUT))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Highlight, QColor(SELECT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
    app.setPalette(p)


class _PasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.password_value = ""
        self.setWindowTitle("Password Required")
        self.setFixedSize(360, 130)
        self.setStyleSheet(_DLG_STYLE)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.MSWindowsFixedSizeDialogHint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel("Enter your password to unlock:"))

        self._entry = QLineEdit()
        self._entry.setEchoMode(QLineEdit.EchoMode.Password)
        self._entry.setPlaceholderText("Password")
        self._entry.returnPressed.connect(self._on_accept)
        lay.addWidget(self._entry)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        ok_btn = QPushButton("Unlock")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_accept)
        cn_btn = QPushButton("Cancel")
        cn_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cn_btn)
        lay.addLayout(btn_row)

    def _on_accept(self):
        self.password_value = self._entry.text()
        self.accept()


def main(icon_path: str | None = None) -> int:
    # QApplication MUST exist before any QWidget / QDialog is created.
    # Create it first, before setup_encryption() and before _PasswordDialog.
    diagnostics.set_startup_stage("creating QApplication")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Roblox Account Manager")
    app.setFont(QFont("Segoe UI", 10))
    apply_palette(app)
    diagnostics.set_startup_stage("QApplication ready")

    password = None
    try:
        diagnostics.set_startup_stage("loading encryption settings")
        data_folder = get_data_dir()
        os.makedirs(data_folder, exist_ok=True)
        enc_cfg = EncryptionConfig(os.path.join(data_folder, "encryption_config.json"))

        if (enc_cfg.is_encryption_enabled()
                and enc_cfg.get_encryption_method() == "password"):
            dlg = _PasswordDialog()
            if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.password_value:
                _show_error(None, "Error", "Password is required.")
                return 1
            password = dlg.password_value
    except Exception as exc:
        crash_path = diagnostics.report_exception(
            "Loading encryption settings",
            exc,
            fatal=True,
        )
        _show_error(
            None,
            "Encryption Settings Error",
            "The encryption settings could not be loaded.\n\n"
            f"Details were saved to:\n{crash_path}",
        )
        return 1

    try:
        diagnostics.set_startup_stage("initializing account manager")
        manager = RobloxAccountManager(password=password)
    except ValueError:
        _show_error(None, "Error", "Invalid password. Please try again.")
        return 1
    except Exception as exc:
        crash_path = diagnostics.report_exception(
            "Initializing account manager",
            exc,
            fatal=True,
        )
        _show_error(
            None,
            "Account Manager Could Not Start",
            "The account data could not be loaded.\n\n"
            f"Details were saved to:\n{crash_path}",
        )
        return 1

    if not icon_path or not os.path.exists(icon_path):
        icon_path = os.path.join(get_data_dir(), "icon.ico")
        if not os.path.exists(icon_path):
            _alt = get_resource_path("icon.ico")
            icon_path = _alt if os.path.exists(_alt) else None

    if icon_path and os.path.exists(icon_path):
        try:
            app.setApplicationIcon(QIcon(icon_path))
            app.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

    try:
        diagnostics.set_startup_stage("creating main window")
        window = AccountManagerUIQt(manager, icon_path=icon_path)
        app.aboutToQuit.connect(window._perform_shutdown_cleanup)
    except Exception as exc:
        crash_path = diagnostics.report_exception(
            "Creating the main window",
            exc,
            fatal=True,
        )
        _show_error(
            None,
            "Evanovar RAM Could Not Start",
            "The main window could not be created.\n\n"
            f"Details were saved to:\n{crash_path}",
        )
        return 1

    window.show()
    diagnostics.mark_ui_ready()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
