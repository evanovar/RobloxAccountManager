import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QObject, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox

from classes.operation_result import OperationResult
from utils import ui


def wait_until(condition, limit_ms=3000):
    waited = 0
    while not condition() and waited < limit_ms:
        QTest.qWait(20)
        waited += 20
    return condition()


class WaitForRobloxExitTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.owner = QObject()
        self.calls = []

    def wait(self, timeout):
        ui.AccountManagerUIQt._wait_for_roblox_exit(self.owner, timeout, lambda: self.calls.append("done"))

    def test_callback_runs_once_roblox_has_exited(self):
        with patch.object(ui.actions, "is_roblox_running", side_effect=[True, True, False, False]):
            self.wait(3.0)
            self.assertTrue(wait_until(lambda: self.calls))
        self.assertEqual(self.calls, ["done"])

    def test_callback_runs_when_the_timeout_passes(self):
        with patch.object(ui.actions, "is_roblox_running", return_value=True):
            self.wait(0.3)
            self.assertTrue(wait_until(lambda: self.calls))
        self.assertEqual(self.calls, ["done"])

    def test_callback_is_only_called_once(self):
        with patch.object(ui.actions, "is_roblox_running", return_value=False):
            self.wait(3.0)
            wait_until(lambda: self.calls)
            QTest.qWait(500)
        self.assertEqual(self.calls, ["done"])

    def test_the_event_loop_keeps_running_while_waiting(self):
        ticks = []
        ticker = QTimer()
        ticker.setInterval(30)
        ticker.timeout.connect(lambda: ticks.append(1))
        ticker.start()
        with patch.object(ui.actions, "is_roblox_running", return_value=True):
            self.wait(0.6)
            wait_until(lambda: self.calls)
        ticker.stop()
        self.assertGreaterEqual(len(ticks), 8)


class StartMultiRobloxTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.window = SimpleNamespace(
            _mr_method="default",
            _mr_enabled=True,
            _mr_enabled_chk=QCheckBox(),
            _update_mr_status=MagicMock(),
            _wait_for_roblox_exit=MagicMock(),
            _finish_start_multi_roblox=MagicMock(),
        )
        self.enterContext(patch.object(ui.actions, "is_multi_roblox_running", return_value=False))
        self.enterContext(patch.object(ui.actions, "is_roblox_running", return_value=True))
        self.save = self.enterContext(patch.object(ui.actions, "save_ui_setting"))
        self.kill = self.enterContext(patch.object(ui.actions, "kill_roblox"))

    def start(self, answer):
        with patch.object(ui.QMessageBox, "question", return_value=answer):
            ui.AccountManagerUIQt._start_multi_roblox(self.window)

    def test_closing_roblox_waits_without_blocking_and_then_continues(self):
        self.start(QMessageBox.StandardButton.Yes)
        self.kill.assert_called_once()
        self.window._wait_for_roblox_exit.assert_called_once_with(3.0, self.window._finish_start_multi_roblox)
        self.window._finish_start_multi_roblox.assert_not_called()

    def test_declining_leaves_multi_roblox_off(self):
        self.window._mr_enabled_chk.setChecked(True)
        self.start(QMessageBox.StandardButton.No)
        self.kill.assert_not_called()
        self.window._wait_for_roblox_exit.assert_not_called()
        self.assertFalse(self.window._mr_enabled)
        self.assertFalse(self.window._mr_enabled_chk.isChecked())
        self.save.assert_called_once_with("multi_roblox_enabled", False)

    def test_without_a_running_client_it_continues_straight_away(self):
        with patch.object(ui.actions, "is_roblox_running", return_value=False):
            self.start(QMessageBox.StandardButton.Yes)
        self.window._finish_start_multi_roblox.assert_called_once()
        self.window._wait_for_roblox_exit.assert_not_called()


class ShortcutToggleTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.bridge = ui._Bridge()
        self.startup_chk = QCheckBox()
        self.menu_chk = QCheckBox()
        self.window = SimpleNamespace(
            _bridge=self.bridge,
            _sett_startup_chk=self.startup_chk,
            _sett_startmenu_chk=self.menu_chk,
            _show_operation_error=MagicMock(),
        )
        self.window._run_shortcut_toggle = lambda *a: ui.AccountManagerUIQt._run_shortcut_toggle(self.window, *a)
        self.window._on_shortcut_toggle_done = lambda *a: ui.AccountManagerUIQt._on_shortcut_toggle_done(self.window, *a)
        self.bridge.shortcut_toggle_done.connect(self.window._on_shortcut_toggle_done)
        self.save = self.enterContext(patch.object(ui.actions, "save_ui_setting"))

    def test_the_work_runs_on_another_thread_and_the_box_is_locked_meanwhile(self):
        release = threading.Event()
        seen = {}

        def work():
            seen["thread"] = threading.current_thread().name
            seen["enabled_during_work"] = self.startup_chk.isEnabled()
            release.wait(5)
            return OperationResult.success()

        ui.AccountManagerUIQt._run_shortcut_toggle(self.window, "startup", True, self.startup_chk, work)
        self.assertTrue(wait_until(lambda: "thread" in seen))
        self.assertEqual(seen["thread"], "shortcut-startup")
        self.assertFalse(self.startup_chk.isEnabled())
        release.set()
        self.assertTrue(wait_until(self.startup_chk.isEnabled))

    def test_successful_startup_toggle_saves_the_setting(self):
        self.startup_chk.setChecked(True)
        ui.AccountManagerUIQt._run_shortcut_toggle(
            self.window, "startup", True, self.startup_chk, lambda: OperationResult.success()
        )
        self.assertTrue(wait_until(lambda: self.save.called))
        self.save.assert_called_once_with("start_with_windows", True)
        self.assertTrue(self.startup_chk.isChecked())
        self.window._show_operation_error.assert_not_called()

    def test_failed_startup_toggle_resets_the_box_and_shows_the_error(self):
        self.startup_chk.setChecked(True)
        failure = OperationResult.failure("X", "Title", "Message")
        ui.AccountManagerUIQt._run_shortcut_toggle(self.window, "startup", True, self.startup_chk, lambda: failure)
        self.assertTrue(wait_until(lambda: self.window._show_operation_error.called))
        self.assertFalse(self.startup_chk.isChecked())
        self.assertTrue(self.startup_chk.isEnabled())
        self.save.assert_called_once_with("start_with_windows", False)
        self.window._show_operation_error.assert_called_once_with(failure)

    def test_failed_start_menu_toggle_resets_only_its_own_box(self):
        self.menu_chk.setChecked(True)
        self.startup_chk.setChecked(True)
        failure = OperationResult.failure("X", "Title", "Message")
        ui.AccountManagerUIQt._run_shortcut_toggle(self.window, "start_menu", True, self.menu_chk, lambda: failure)
        self.assertTrue(wait_until(lambda: self.window._show_operation_error.called))
        self.assertFalse(self.menu_chk.isChecked())
        self.assertTrue(self.startup_chk.isChecked())
        self.save.assert_not_called()

    def test_successful_start_menu_toggle_keeps_the_box_and_saves_nothing(self):
        self.menu_chk.setChecked(True)
        ui.AccountManagerUIQt._run_shortcut_toggle(
            self.window, "start_menu", True, self.menu_chk, lambda: OperationResult.success()
        )
        self.assertTrue(wait_until(self.menu_chk.isEnabled))
        QTest.qWait(50)
        self.assertTrue(self.menu_chk.isChecked())
        self.save.assert_not_called()

    def test_handlers_pick_the_matching_action(self):
        calls = []
        self.window._run_shortcut_toggle = lambda kind, enabled, box, work: calls.append((kind, enabled, box, work))
        checked, unchecked = ui.Qt.CheckState.Checked.value, ui.Qt.CheckState.Unchecked.value

        ui.AccountManagerUIQt._on_sett_startup(self.window, checked)
        ui.AccountManagerUIQt._on_sett_startup(self.window, unchecked)
        ui.AccountManagerUIQt._on_sett_start_menu(self.window, checked)
        ui.AccountManagerUIQt._on_sett_start_menu(self.window, unchecked)

        ws = ui.windows_startup_mod
        self.assertEqual(
            [(kind, enabled, work) for kind, enabled, _box, work in calls],
            [
                ("startup", True, ws.enable_startup),
                ("startup", False, ws.disable_startup),
                ("start_menu", True, ws.enable_start_menu),
                ("start_menu", False, ws.disable_start_menu),
            ],
        )


if __name__ == "__main__":
    unittest.main()
