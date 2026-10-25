from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import QElapsedTimer, QEventLoop, QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QMovie, QPainter, QPixmap
lazy from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

from features.color_themes import DERIVED_KEYS, contrast_ratio
from features.theme_model import ThemeError, validate_theme
from utils.theme_runtime import bind_style


_LABELS = {
    "ACCENT": "Accent", "BG": "Background", "PANEL": "Surface",
    "INPUT": "Input", "TEXT": "Text", "MUTED": "Muted text",
    "LINE": "Border", "SELECT": "Selection", "NOTE": "Note text",
}
_BASIC = tuple(_LABELS)
_MEDIA_FILTER = "Background media (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp4 *.webm *.avi *.mov *.mkv)"
_PREVIEW_ROLES = (
    'TEXT', 'MUTED', 'NOTE', 'ACCENT', 'ON_ACCENT', 'BG', 'PANEL', 'INPUT',
    'LINE', 'SELECT', 'HOVER', 'PRESSED', 'RAISED', 'ACCENT_HOVER',
    'ACCENT_PRESSED', 'ACCENT_BRIGHT', 'ACCENT_SOFT', 'ACCENT_TEXT', 'ACCENT_DEEP',
)
_TEXT_ROLES = {'TEXT', 'MUTED', 'NOTE', 'ACCENT_TEXT', 'ON_ACCENT'}


class _WorkerBridge(QObject):
    completed = Signal(object)


class _AppearancePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors = {}
        self.setMouseTracking(True)
        self.setAccessibleName("Theme appearance preview")

    def set_colors(self, colors):
        self._colors = dict(colors)
        self.setAccessibleDescription(', '.join(
            f'{_LABELS.get(role, role.replace("_", " ").capitalize())}: {colors[role]}'
            for role in _PREVIEW_ROLES
        ))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = max(1, min(6, self.width() // 80))
        height = ((len(_PREVIEW_ROLES) + columns - 1) // columns) * 36
        if self.height() != height:
            self.setFixedHeight(height)

    def mouseMoveEvent(self, event):
        columns = max(1, min(6, self.width() // 80))
        column = min(columns - 1, int(event.position().x() / (self.width() / columns)))
        index = int(event.position().y() // 36) * columns + column
        if 0 <= index < len(_PREVIEW_ROLES) and self._colors:
            role = _PREVIEW_ROLES[index]
            self.setToolTip(f'{_LABELS.get(role, role.replace("_", " ").capitalize())}: {self._colors[role]}')
        else:
            self.setToolTip('')
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        if not self._colors:
            return
        c = self._colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        columns = max(1, min(6, self.width() // 80))
        width = self.width() / columns
        label_font = QFont(self.font())
        label_font.setPixelSize(9)
        sample_font = QFont(self.font())
        sample_font.setPixelSize(11)
        sample_font.setBold(True)
        for index, role in enumerate(_PREVIEW_ROLES):
            row, column = divmod(index, columns)
            label = QRectF(column * width, row * 36, width - 8, 12)
            sample = QRectF(column * width, row * 36 + 14, width - 8, 18)
            painter.setFont(label_font)
            painter.setPen(QColor(c['MUTED']))
            painter.drawText(label, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             _LABELS.get(role, role.replace('_', ' ').capitalize()))
            background = 'ACCENT' if role == 'ON_ACCENT' else 'BG' if role in _TEXT_ROLES else role
            painter.fillRect(sample, QColor(c[background]))
            painter.setFont(sample_font)
            foreground = role if role in _TEXT_ROLES else 'TEXT'
            if role.startswith('ACCENT') and role not in _TEXT_ROLES and role != 'ACCENT_DEEP':
                foreground = 'ON_ACCENT'
            painter.setPen(QColor(c[foreground]))
            painter.drawText(sample, Qt.AlignmentFlag.AlignCenter, 'Text')


class ThemeEditor(QWidget):
    operation_finished = Signal()

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.library = manager.library
        self._baseline = manager.theme.clone()
        self._draft = self._baseline.clone()
        self._forced_dirty = False
        self._imported = None
        self._busy = False
        self._refreshing = False
        self._color_grids = []
        self._columns = 0
        self._bridge = _WorkerBridge(self)
        self._bridge.completed.connect(self._worker_finished)
        self._build()
        self._reload_library()
        self._refresh()

    @property
    def theme(self):
        return self._draft.clone()

    @property
    def dirty(self):
        return self._forced_dirty or self._draft != self._baseline

    @property
    def busy(self):
        return self._busy

    def _button(self, text, callback, layout):
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def _section(self, text, layout):
        label = QLabel(text)
        bind_style(label, 'color: @RAM_MUTED@; font-size: 9px; font-weight: 700;'
                         ' letter-spacing: 0.5px; margin-top: 8px;')
        layout.addWidget(label)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        self._section('THEME LIBRARY', layout)
        self.selector = QComboBox()
        self.selector.setAccessibleName("Selected theme")
        self.selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.selector.setMinimumContentsLength(16)
        self.selector.currentIndexChanged.connect(self._selection_changed)
        layout.addWidget(self.selector)
        self._library_controls = QWidget()
        actions = QHBoxLayout(self._library_controls)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self._button("New", self.new_theme, actions)
        self.rename_button = self._button("Rename", self._rename_clicked, actions)
        self.delete_button = self._button("Delete", self._delete_clicked, actions)
        self._button("Import", self._import_clicked, actions)
        self._button("Export", self._export_clicked, actions)
        layout.addWidget(self._library_controls)
        save_row = QHBoxLayout()
        save_row.setSpacing(6)
        self.status_label = QLabel()
        self.status_label.setAccessibleName("Theme save status")
        bind_style(self.status_label, "color: @RAM_MUTED@; font-size: 10px;")
        save_row.addWidget(self.status_label, 1)
        self.revert_button = self._button("Revert changes", self.revert_changes, save_row)
        self.save_button = self._button("Save theme", lambda: self.save_theme(), save_row)
        bind_style(self.save_button, 'QPushButton { background: @RAM_SELECT@; font-weight: 600; }'
                                    'QPushButton:disabled { background: @RAM_INPUT@; color: @RAM_MUTED@; }')
        layout.addLayout(save_row)
        self.library_notice = QLabel()
        self.library_notice.setWordWrap(True)
        self.library_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.library_notice.setAccessibleName("Theme library notices")
        bind_style(self.library_notice, "color: @RAM_MUTED@; font-size: 10px;")
        layout.addWidget(self.library_notice)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bind_style(scroll, 'QScrollArea { background: transparent; border: none; }')
        self._content = QWidget()
        bind_style(self._content, 'background: transparent;')
        body = QVBoxLayout(self._content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        self._section('PREVIEW', body)
        self.preview = _AppearancePreview()
        body.addWidget(self.preview)
        self._section('BACKGROUND', body)
        self.background_enabled = QCheckBox("Enable background media")
        self.background_enabled.setAccessibleName("Enable background media")
        self.background_enabled.toggled.connect(lambda value: self.set_background(enabled=value))
        body.addWidget(self.background_enabled)
        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self.background_path = QLineEdit()
        self.background_path.setReadOnly(True)
        self.background_path.setAccessibleName("Background media file")
        self.background_path.setPlaceholderText('Image, GIF, or video')
        file_row.addWidget(self.background_path, 1)
        self._button("Browse", self._browse_background, file_row)
        self._button("Remove", lambda: self.set_background(path="", enabled=False), file_row)
        body.addLayout(file_row)
        self.blur_slider = self._slider("Blur", "Background blur", body, "blur")
        self.dim_slider = self._slider("Dim", "Background dim", body, "dim")
        self._section('COLORS', body)
        self.color_buttons = {}
        self._color_grid(_BASIC, body)
        self.advanced_toggle = QCheckBox("Advanced interaction colors")
        self.advanced_toggle.setAccessibleName("Show advanced interaction colors")
        body.addWidget(self.advanced_toggle)
        self._advanced = QWidget()
        advanced_layout = QVBoxLayout(self._advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        self._color_grid(DERIVED_KEYS, advanced_layout)
        self._advanced.hide()
        self.advanced_toggle.toggled.connect(self._advanced.setVisible)
        body.addWidget(self._advanced)
        self.contrast_hint = QLabel()
        self.contrast_hint.setWordWrap(True)
        self.contrast_hint.setAccessibleName("Text contrast hint")
        bind_style(self.contrast_hint, "color: @RAM_MUTED@;")
        body.addWidget(self.contrast_hint)
        body.addStretch()
        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

    def _color_grid(self, roles, layout):
        grid = QGridLayout()
        cells = []
        for index, role in enumerate(roles):
            row, col = divmod(index, 2)
            name = _LABELS.get(role, role.replace("_", " ").capitalize())
            cell = QHBoxLayout()
            button = QPushButton()
            button.setAccessibleName(name + " color")
            button.clicked.connect(lambda checked=False, r=role: self._choose_color(r))
            self.color_buttons[role] = button
            cell.addWidget(button, 1)
            reset = QPushButton("Reset")
            reset.setAccessibleName("Reset " + name.lower() + " to starting value")
            reset.clicked.connect(lambda checked=False, r=role: self.reset_color(r))
            cell.addWidget(reset)
            grid.addLayout(cell, row, col)
            cells.append(cell)
        layout.addLayout(grid)
        self._color_grids.append((grid, cells))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 2 if self.width() >= 600 else 1
        if columns == self._columns:
            return
        self._columns = columns
        for grid, cells in self._color_grids:
            while grid.count():
                grid.takeAt(0)
            for index, cell in enumerate(cells):
                grid.addLayout(cell, index // columns, index % columns)
            grid.invalidate()
            grid.activate()
        self._content.layout().invalidate()
        self._content.layout().activate()

    def _slider(self, label, accessible_name, layout, field):
        row = QHBoxLayout()
        text = QLabel(label)
        text.setMinimumWidth(28)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setAccessibleName(accessible_name)
        text.setBuddy(slider)
        value = QLabel("0%")
        value.setMinimumWidth(32)
        slider.valueChanged.connect(lambda n: value.setText(str(n) + "%"))
        slider.valueChanged.connect(lambda n: self.set_background(**{field: n}))
        row.addWidget(text)
        row.addWidget(slider, 1)
        row.addWidget(value)
        layout.addLayout(row)
        return slider

    def _reload_library(self):
        self.selector.blockSignals(True)
        self.selector.clear()
        themes = self.library.list_themes()
        for theme in themes:
            self.selector.addItem(theme.name, theme.id)
        issues = list(getattr(self.library, "issues", []))
        self.library_notice.setText("\n".join(issues))
        self.library_notice.setVisible(bool(issues))
        self.selector.blockSignals(False)
        self._sync_selection()

    def _sync_selection(self):
        self.selector.blockSignals(True)
        self.selector.setCurrentIndex(self.selector.findData(self._baseline.id))
        self.selector.blockSignals(False)

    def _refresh(self):
        self._refreshing = True
        try:
            for role, button in self.color_buttons.items():
                value = self._draft.colors[role]
                name = _LABELS.get(role, role.replace("_", " ").capitalize())
                button.setText(f"{name}  {value}")
                pixmap = QPixmap(14, 14)
                pixmap.fill(QColor(value))
                button.setIcon(QIcon(pixmap))
            bg = self._draft.background
            self.background_enabled.setChecked(bg.enabled)
            self.background_path.setText(Path(bg.path).name if bg.path else "")
            self.background_path.setToolTip(bg.path or "No background media selected")
            self.blur_slider.setValue(bg.blur)
            self.dim_slider.setValue(bg.dim)
            ratio = contrast_ratio(self._draft.colors["TEXT"], self._draft.colors["PANEL"])
            self.contrast_hint.setText(
                f"Text on surface: {ratio:.1f}:1" +
                (". Below 4.5:1; consider adjusting Text or Surface." if ratio < 4.5 else ".")
            )
            self.preview.set_colors(self._draft.colors)
            self._update_enabled()
        finally:
            self._refreshing = False

    def _update_enabled(self):
        self._content.setEnabled(not self._busy)
        self.selector.setEnabled(not self._busy)
        self._library_controls.setEnabled(not self._busy)
        self.save_button.setEnabled(self.dirty and not self._busy)
        self.revert_button.setEnabled(self.dirty and not self._busy)
        custom = bool(self._baseline.id) and not self._baseline.id.startswith("builtin:")
        self.rename_button.setEnabled(custom)
        self.delete_button.setEnabled(custom)
        self.status_label.setText("Working..." if self._busy else "Unsaved changes" if self.dirty else "Saved")

    def _error(self, error):
        QMessageBox.warning(self, "Theme could not be updated", str(error) or "Try again after checking the theme file and folder permissions.")

    def _edit(self, operation):
        if self._busy or self._refreshing:
            return
        draft = self._draft.clone()
        try:
            operation(draft)
            if draft == self._draft:
                return
            if draft.id.startswith("builtin:"):
                draft.id = ""
            if not self._forced_dirty:
                restored = draft.clone()
                restored.id = self._baseline.id
                if restored == self._baseline:
                    draft = restored
            validate_theme(draft)
            self.manager.apply(draft)
            self._draft = draft
            self._refresh()
        except Exception as error:
            self._error(error)
            self._refresh()

    def set_color(self, role, value):
        self._edit(lambda draft: draft.set_color(role, value))

    def reset_color(self, role):
        self._edit(lambda draft: draft.reset_color(role))

    def set_background(self, **values):
        def update(draft):
            for field, value in values.items():
                if field not in {"enabled", "path", "blur", "dim", "tint"}:
                    raise ThemeError("Unknown background control: " + field)
                setattr(draft.background, field, value)
        self._edit(update)

    def _choose_color(self, role):
        color = QColorDialog.getColor(QColor(self._draft.colors[role]), self, "Choose " + _LABELS.get(role, role.lower()))
        if color.isValid():
            self.set_color(role, color.name().upper())

    def _browse_background(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose background media", "", _MEDIA_FILTER)
        if path:
            self.set_background(path=path, enabled=True)

    def _selection_changed(self, index):
        theme_id = self.selector.itemData(index)
        if theme_id:
            self.select_theme(theme_id)

    def select_theme(self, theme_id):
        if self._busy:
            self._sync_selection()
            return False
        if theme_id == self._baseline.id and not self.dirty:
            return True
        palette_draft = self._draft.clone()
        palette_draft.id = self._baseline.id
        palette_draft.background = self._baseline.background
        background_only = (theme_id.startswith('builtin:') and not self._forced_dirty
                           and palette_draft == self._baseline)
        if not background_only and not self.confirm_discard():
            self._sync_selection()
            return False
        try:
            theme = self.library.load(theme_id)
            combined = theme.clone()
            background = self._draft.background
            if theme_id.startswith('builtin:') and background.enabled and background.path:
                combined.background = self._draft.clone().background
            if combined != theme:
                self.library.activate(theme.id)
                combined.id = ''
                self.manager.apply(combined)
                self._adopt(theme)
                self._draft = combined
                self._refresh()
            else:
                self.manager.activate(theme)
                self._adopt(theme)
            return True
        except Exception as error:
            self._error(error)
            self._sync_selection()
            return False

    def _adopt(self, theme):
        self._baseline = theme.clone()
        self._draft = theme.clone()
        self._forced_dirty = False
        self._sync_selection()
        self._refresh()

    def _discard_import(self):
        if self._imported is not None:
            theme = self._imported
            self.library.discard_import(theme)
            self._imported = None

    def revert_changes(self):
        if self._busy:
            return False
        try:
            self.manager.apply(self._baseline)
            self._discard_import()
            self._draft = self._baseline.clone()
            self._forced_dirty = False
            self._refresh()
            return True
        except Exception as error:
            try:
                self.manager.apply(self._draft)
            except Exception:
                pass
            self._error(error)
            return False

    def confirm_discard(self):
        if self._busy:
            return False
        if not self.dirty:
            try:
                self._discard_import()
                return True
            except Exception as error:
                self._error(error)
                return False
        answer = QMessageBox.warning(
            self, "Unsaved theme changes", "Save your theme changes before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Discard:
            return self.revert_changes()
        if answer != QMessageBox.StandardButton.Save:
            return False
        if not self.save_theme():
            return False
        loop = QEventLoop(self)
        self.operation_finished.connect(loop.quit)
        if self._busy:
            loop.exec()
        self.operation_finished.disconnect(loop.quit)
        return not self.dirty

    def _make_draft(self, source):
        if self._busy:
            return False
        draft = source.clone()
        draft.id = ""
        draft.starting_colors = dict(draft.colors)
        draft.starting_customized = set(draft.customized)
        try:
            self.manager.apply(draft)
            self._draft = draft
            self._forced_dirty = True
            self._refresh()
            return True
        except Exception as error:
            self._error(error)
            return False

    def new_theme(self):
        return self._make_draft(self._draft)

    def _run(self, operation, callback, on_error=None):
        if self._busy:
            return False
        self._busy = True
        self._update_enabled()
        bridge = self._bridge

        def worker():
            try:
                result = operation()
                error = None
            except Exception as exception:
                result, error = None, exception
            try:
                bridge.completed.emit((callback, result, error, on_error))
            except RuntimeError:
                pass

        try:
            threading.Thread(target=worker, daemon=True, name="Theme operation").start()
        except Exception as error:
            self._worker_finished((callback, None, error, on_error))
            return False
        return True

    def _worker_finished(self, payload):
        callback, result, error, on_error = payload
        try:
            if error is not None:
                raise error
            callback(result)
        except Exception as exception:
            message = exception
            if on_error is not None:
                try:
                    message = on_error(exception) or exception
                except Exception as recovery_error:
                    message = f"{exception}\nRecovery also failed: {recovery_error}"
            self._error(message)
        finally:
            self._busy = False
            self._update_enabled()
            self.operation_finished.emit()

    def save_theme(self, name=None):
        if self._busy:
            return False
        if not self.dirty:
            return True
        if not self._draft.id:
            if name is None:
                name, accepted = QInputDialog.getText(self, "Save theme", "Theme name", text=self._draft.name)
                if not accepted:
                    return False
            name = str(name).strip()
            if not name or len(name) > 80:
                self._error("Enter a theme name between 1 and 80 characters.")
                return False
        draft = self._draft.clone()

        def saved(theme):
            self.manager.activate(theme)
            self._adopt(theme)
            self._reload_library()
            self._discard_import()

        return self._run(lambda: self.library.save(draft, name=name), saved)

    def import_theme(self, path):
        if self._busy or not self.confirm_discard():
            return False

        def imported(theme):
            theme.id = ""
            self.manager.apply(theme)
            self._imported = theme.clone()
            self._draft = theme.clone()
            self._forced_dirty = True
            self._refresh()

        return self._run(lambda: self.library.import_theme(path), imported)

    def export_theme(self, path):
        draft = self._draft.clone()
        return self._run(lambda: self.library.export_theme(draft, path), lambda result: None)

    def _import_clicked(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import theme", "", "RAM themes (*.ramtheme)")
        if path:
            self.import_theme(path)

    def _export_clicked(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export theme", "theme.ramtheme", "RAM themes (*.ramtheme)")
        if path:
            if not path.lower().endswith(".ramtheme"):
                path += ".ramtheme"
            self.export_theme(path)

    def _rename_clicked(self):
        if self._busy or not self.confirm_discard():
            return
        name, accepted = QInputDialog.getText(self, "Rename theme", "Theme name", text=self._baseline.name)
        if not accepted:
            return
        theme_id = self._baseline.id

        def renamed(theme):
            self.manager.activate(theme)
            self._adopt(theme)
            self._reload_library()

        self._run(lambda: self.library.rename(theme_id, name), renamed)

    def _delete_clicked(self):
        if self._busy or not self.confirm_discard():
            return
        if QMessageBox.question(self, "Delete theme", f'Delete "{self._baseline.name}"?',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        theme_id = self._baseline.id
        previous = self._baseline.clone()
        fallback = self.library.load("builtin:default")

        def deleted(result):
            self.manager.activate(fallback)
            self._adopt(fallback)
            self._reload_library()

        def recover(error):
            try:
                restored = self.library.load(previous.id)
            except Exception:
                self.manager.activate(fallback)
                self._adopt(fallback)
                self._reload_library()
                return f"{error}\nThe previous theme is no longer available. Default is active; keep any remaining theme files for recovery."
            self.manager.activate(restored)
            self._adopt(restored)
            self._reload_library()
            return f"{error}\nThe previous saved theme is still active. Close programs using its files and try again."

        self._busy = True
        self._update_enabled()
        sources = []
        state = {"started": False, "cancelled": False}
        timer = QTimer(self)
        timer.setInterval(10)
        elapsed = QElapsedTimer()
        elapsed.start()

        def start_delete():
            if state["cancelled"] or state["started"]:
                return
            state["started"] = True
            timer.stop()
            timer.deleteLater()
            self._busy = False
            self._run(lambda: self.library.delete(theme_id), deleted, on_error=recover)

        def release_failed(error):
            if state["cancelled"]:
                return
            state["cancelled"] = True
            timer.stop()
            timer.deleteLater()
            self._worker_finished((deleted, None, error, recover))

        def check_released():
            if state["cancelled"] or state["started"]:
                return
            if all(not isValid(source) for source in sources):
                start_delete()
            elif elapsed.elapsed() >= 5000:
                release_failed(ThemeError("The background decoder did not release its files. Try deleting again after closing the background."))

        try:
            renderer = getattr(self.manager, "background", None)
            if renderer is not None:
                for kind in (QMediaPlayer, QVideoSink, QMovie):
                    sources.extend(renderer.findChildren(kind))
            timer.timeout.connect(check_released)
            self.manager.apply(fallback)
            timer.start()
            QTimer.singleShot(0, check_released)
        except Exception as error:
            release_failed(error)
