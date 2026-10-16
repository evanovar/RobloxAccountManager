import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QListWidget

from features import account_status
from utils import ui


class AccountStatusUITests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.settings = {"presence_indicator": True}
        self.enterContext(patch.object(ui.actions, "load_ui_settings", side_effect=lambda: self.settings))
        self.list = QListWidget()
        self.addCleanup(self.list.close)
        self.addCleanup(self.list.deleteLater)
        self.headless = set()
        manager = MagicMock()
        manager.get_headless_identities.side_effect = lambda: self.headless
        self.window = SimpleNamespace(
            _account_list=self.list, _current_group=None, _account_query="",
            manager=SimpleNamespace(accounts={"Account": {}, "Other": {}}),
            _avatar_labels={}, _presence_dots={}, _activity_widgets={}, _activity_labels={},
            _invalid_badges={}, _account_avatar_containers={}, _account_name_labels={}, _account_rows={},
            _online_usernames=set(), _activity_snapshot={}, _headless_manager=manager,
            _cv_mod=SimpleNamespace(is_flagged=lambda data: False),
            _make_placeholder_pixmap=lambda size: QPixmap(size, size),
            _rebuild_group_bar=MagicMock(), _load_avatars_async=MagicMock(),
            _presence_scanner=object(), _presence_generation=1,
        )
        for name in ("_update_presence_dots", "_update_activity_rows", "_refresh_account_list"):
            method = getattr(ui.AccountManagerUIQt, name)
            setattr(self.window, name, lambda method=method: method(self.window))

    def update(self, state="game", visible=True):
        snapshot = {"Account": {"pids": [123], "ram_mb": 128, "cpu_percent": 1.5,
                                "ram_available": True, "cpu_available": True, "clients": [{
            "pid": 123, "created": 100.0, "client_state": state,
            "window_visible": visible, "reason": "Connected to a game server." if state == "game" else state,
        }]}}
        snapshot["Account"].update(account_status.summarize_processes(snapshot["Account"]["clients"], self.headless))
        ui.AccountManagerUIQt._on_presence_update(self.window, (1, snapshot))

    def test_dot_is_left_of_avatar_and_reserves_space_when_absent(self):
        self.window._refresh_account_list()
        self.update()
        row = self.window._account_rows["Account"]
        dot = self.window._presence_dots["Account"]
        leading = row.layout().itemAt(0).layout()
        self.assertIs(leading.itemAt(0).widget(), dot.parentWidget())
        self.assertIs(leading.itemAt(1).widget(), self.window._account_avatar_containers["Account"])
        self.assertEqual(leading.spacing(), 2)
        self.assertEqual(row.layout().contentsMargins().left(), 2)
        self.assertEqual(dot.parentWidget().width(), 8)
        self.assertIsNot(dot.parentWidget(), self.window._account_avatar_containers["Account"])
        other = self.window._presence_dots["Other"]
        self.assertTrue(other.isHidden())
        self.assertFalse(other.parentWidget().isHidden())
        self.assertEqual(other.toolTip(), "")
        self.assertEqual(other.parentWidget().toolTip(), "")
        self.assertEqual(dot.parentWidget().width(), other.parentWidget().width())

    def test_all_color_states_have_explanatory_tooltips(self):
        self.window._refresh_account_list()
        for state, visible in (("home", True), ("game", True), ("error", True), ("game", False)):
            self.update(state, visible)
            dot = self.window._presence_dots["Account"]
            expected = "background" if not visible else state
            color = ui.ACCENT_TEXT if expected == "home" else account_status.COLORS[expected]
            self.assertIn(color, dot.styleSheet())
            self.assertTrue(dot.toolTip())
            self.assertFalse(dot.isHidden())

    def test_headless_outline_updates_without_waiting_for_new_scan(self):
        self.window._refresh_account_list()
        self.update()
        dot = self.window._presence_dots["Account"]
        self.headless.add((123, 100.0))
        self.window._update_presence_dots()
        self.assertIn("background: transparent", dot.styleSheet())
        self.assertEqual(dot.toolTip(), "In Game (Headless)")
        self.headless.clear()
        self.window._update_presence_dots()
        self.assertNotIn("background: transparent", dot.styleSheet())

    def test_refresh_keeps_selection_and_reapplies_cached_status(self):
        self.window._refresh_account_list()
        self.update("home")
        self.list.setCurrentRow(1)
        self.window._refresh_account_list()
        self.assertEqual(self.list.currentItem().data(Qt.ItemDataRole.UserRole), "Other")
        self.assertIn(ui.ACCENT_TEXT, self.window._presence_dots["Account"].styleSheet())

    def test_disabled_performance_monitor_keeps_status_dots_and_hides_metrics(self):
        self.window._refresh_account_list()
        self.update()
        self.settings["presence_indicator"] = False
        self.window._refresh_account_list()
        self.assertFalse(self.window._presence_dots["Account"].parentWidget().isHidden())
        self.assertFalse(self.window._presence_dots["Account"].isHidden())
        self.assertEqual(self.window._presence_dots["Account"].toolTip(), "In Game")
        self.assertEqual(self.window._activity_widgets, {})
        self.update("home")
        self.assertEqual(self.window._presence_dots["Account"].toolTip(), "In Main Screen")

    def test_old_scanner_cannot_restore_stale_status_after_restart(self):
        self.window._refresh_account_list()
        self.window._presence_generation = 2
        self.update()
        self.assertEqual(self.window._activity_snapshot, {})
        self.assertTrue(self.window._presence_dots["Account"].isHidden())

    def test_ignored_state_keeps_color_across_refresh(self):
        self.window._refresh_account_list()
        self.update("home")
        self.update(None)
        self.window._refresh_account_list()
        self.assertIn(ui.ACCENT_TEXT, self.window._presence_dots["Account"].styleSheet())

    def test_no_dot_before_first_supported_state(self):
        self.window._refresh_account_list()
        self.update(None)
        self.assertTrue(self.window._presence_dots["Account"].isHidden())
        self.assertEqual(self.window._presence_dots["Account"].toolTip(), "")
        self.assertEqual(self.window._presence_dots["Account"].parentWidget().toolTip(), "")

    def test_stopped_account_clears_both_previous_tooltips(self):
        self.window._refresh_account_list()
        self.update()
        dot = self.window._presence_dots["Account"]
        self.assertEqual(dot.toolTip(), "In Game")
        ui.AccountManagerUIQt._on_presence_update(self.window, (1, {}))
        self.assertTrue(dot.isHidden())
        self.assertEqual(dot.toolTip(), "")
        self.assertEqual(dot.parentWidget().toolTip(), "")

    def test_home_color_uses_memory_text_theme_color(self):
        self.window._refresh_account_list()
        with patch.object(ui, "ACCENT_TEXT", "#123ABC"):
            self.update("home")
        self.assertIn("#123ABC", self.window._presence_dots["Account"].styleSheet())

    def test_startup_and_performance_toggle_leave_status_scanner_running(self):
        self.settings["presence_indicator"] = False
        manager = MagicMock()
        manager.accounts = {"Account": {}}
        manager.get_encryption_method.return_value = "none"
        manager.get_secure_setting.return_value = ""
        with patch.object(ui.QTimer, "singleShot"), \
                patch.object(ui.AccountManagerUIQt, "_load_avatars_async"), \
                patch.object(ui.AccountManagerUIQt, "_start_chromium_status_check"), \
                patch.object(ui.AccountManagerUIQt, "_load_roblox_settings"), \
                patch.object(ui.AccountManagerUIQt, "_setup_system_tray"), \
                patch.object(ui.EncryptionConfig, "is_setup_complete", return_value=True), \
                patch.object(ui.presence_mod, "PresenceScanner") as scanner, \
                patch.object(ui.actions, "save_ui_setting", side_effect=self.settings.__setitem__):
            window = ui.AccountManagerUIQt(manager)
            self.addCleanup(window.deleteLater)
            self.addCleanup(window.close)
            scanner.assert_called_once()
            scanner.return_value.start.assert_called_once()
            window._ensure_page_built(4)
            self.assertEqual(window._sett_monitoring_chk.text(), "Performance Monitor")
            self.assertFalse(window._sett_monitoring_chk.isChecked())
            self.assertEqual(window._activity_widgets, {})
            generation = window._presence_generation
            self.update()
            window._on_presence_update((generation, self.window._activity_snapshot))
            for enabled in (True, False, True):
                window._sett_monitoring_chk.click()
                self.assertEqual(self.settings["presence_indicator"], enabled)
                self.assertEqual(bool(window._activity_widgets), enabled)
                self.assertFalse(window._presence_dots["Account"].isHidden())
                self.assertEqual(window._presence_dots["Account"].toolTip(), "In Game")
                self.assertEqual(window._presence_generation, generation)
                if enabled:
                    ram, cpu = window._activity_labels["Account"]
                    self.assertEqual((ram.text(), cpu.text()), ("128 MB", "1.5%"))
            scanner.return_value.stop.assert_not_called()
