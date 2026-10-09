import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import shiboken6
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QMainWindow, QMessageBox, QRadioButton

from utils import splash, ui


class MultiRobloxWindow(ui.AccountManagerUIQt):
    def __init__(self):
        QMainWindow.__init__(self)
        self._admin_restart_pending = False
        self._mr_method = "handle64"
        self._mr_enabled = True
        self._mr_enabled_chk = QCheckBox(self)
        self._mr_enabled_chk.setChecked(True)
        self._mr_default_radio = QRadioButton(self)
        self._mr_handle64_radio = QRadioButton(self)
        self._update_mr_status = Mock()
        self._update_mr_h64_status = Mock()
        self._perform_shutdown_cleanup = Mock()

    def closeEvent(self, event):
        QMainWindow.closeEvent(self, event)


class Handle64StartupTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = MultiRobloxWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)
        self.addCleanup(splash.dismiss)
        self.saved = self.enterContext(patch.object(ui.actions, "save_ui_setting"))
        self.enterContext(patch.object(ui.actions, "is_multi_roblox_running", return_value=False))
        self.enterContext(patch.object(ui.actions, "enable_multi_roblox", return_value=(False, "NEEDS_ADMIN")))
        self.shell = self.enterContext(patch.object(ui.ctypes.windll.shell32, "ShellExecuteW", return_value=42))
        self.question = self.enterContext(patch.object(ui.QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes))
        self.error = self.enterContext(patch.object(ui.QMessageBox, "critical"))
        self._quit_application = self.app.quit
        self.quit = self.enterContext(patch.object(ui.QApplication, "quit"))

    def test_saved_handle64_is_loaded_without_prompting_during_construction(self):
        with patch.object(ui.actions, "load_ui_settings", return_value={
            "multi_roblox_method": "handle64", "multi_roblox_enabled": True,
        }), patch.object(ui.actions, "find_handle64", return_value="handle64.exe"):
            self.window._load_mr_settings()
        self.question.assert_not_called()
        self.shell.assert_not_called()
        self.assertTrue(self.window._mr_enabled)

    def test_relaunch_keeps_handle64_enabled_and_quits_the_original(self):
        self.window.show()
        self.window._finish_start_multi_roblox()
        self.shell.assert_called_once()
        self.quit.assert_called_once_with()
        self.assertTrue(self.window._admin_restart_pending)
        self.assertFalse(self.window.isVisible())
        self.assertTrue(self.window._mr_enabled)
        self.assertTrue(self.window._mr_enabled_chk.isChecked())
        self.saved.assert_not_called()

    def test_pending_relaunch_does_not_launch_another_copy(self):
        self.assertTrue(self.window._mr_ask_restart_as_admin())
        self.assertTrue(self.window._mr_ask_restart_as_admin())
        self.window._start_multi_roblox()
        self.shell.assert_called_once()
        self.question.assert_called_once()

    def test_declining_admin_does_not_launch_or_quit(self):
        self.question.return_value = QMessageBox.StandardButton.No
        self.window._finish_start_multi_roblox()
        self.shell.assert_not_called()
        self.quit.assert_not_called()
        self.assertFalse(self.window._mr_enabled)
        self.saved.assert_called_once_with("multi_roblox_enabled", False)

    def test_cancelled_or_failed_elevation_keeps_the_original_open(self):
        self.window.show()
        for code in (0, 5, 31, 32):
            with self.subTest(code=code):
                self.shell.return_value = code
                self.assertFalse(self.window._mr_ask_restart_as_admin())
                self.assertFalse(self.window._admin_restart_pending)
                self.assertTrue(self.window.isVisible())
                self.quit.assert_not_called()
        self.assertEqual(self.error.call_count, 4)

    def test_shell_exception_keeps_the_original_open(self):
        self.window.show()
        self.shell.side_effect = OSError("launch failed")
        self.assertFalse(self.window._mr_ask_restart_as_admin())
        self.assertTrue(self.window.isVisible())
        self.quit.assert_not_called()
        self.error.assert_called_once()

    def test_relaunch_quotes_arguments_and_preserves_the_data_directory(self):
        data_dir = "C:\\Profiles\\App $Dir's\\"
        for frozen in (False, True):
            with self.subTest(frozen=frozen):
                self.window._admin_restart_pending = False
                argv = ["src/main.py", "argument with spaces", 'argument"with-quote']
                with patch.object(ui.sys, "frozen", frozen, create=True), \
                        patch.object(ui.sys, "argv", argv), \
                        patch.object(ui, "get_data_dir", return_value=data_dir):
                    self.assertTrue(self.window._mr_ask_restart_as_admin())
                arguments = argv[1:] if frozen else [os.path.abspath(argv[0]), *argv[1:]]
                call = self.shell.call_args.args
                self.assertEqual(call[1:3], ("runas", ui.sys.executable))
                self.assertEqual(call[3], subprocess.list2cmdline([*arguments, "--data-dir", data_dir]))
                self.assertEqual(call[4], os.getcwd())

    def test_selecting_handle64_keeps_that_method_for_the_elevated_copy(self):
        self.window._mr_method = "default"
        self.window._mr_handle64_radio.setChecked(True)
        with patch.object(self.window, "_is_admin", return_value=False):
            self.window._on_mr_method_changed(True)
        self.assertEqual(self.window._mr_method, "handle64")
        self.saved.assert_called_once_with("multi_roblox_method", "handle64")
        self.shell.assert_called_once()

    def test_startup_relaunch_exits_the_real_event_loop_after_splash_reveal(self):
        self.check_startup_relaunch(animate=True)

    def test_startup_relaunch_exits_with_animations_disabled(self):
        self.check_startup_relaunch(animate=False)

    def check_startup_relaunch(self, animate):
        self.quit.side_effect = self._quit_application
        self.enterContext(patch.object(ui, "EncryptionConfig"))
        ui.EncryptionConfig.return_value.is_encryption_enabled.return_value = False
        manager = SimpleNamespace(accounts_recovery_source=None)
        self.enterContext(patch.object(ui, "RobloxAccountManager", return_value=manager))
        self.enterContext(patch.object(ui, "AccountManagerUIQt", return_value=self.window))
        self.enterContext(patch.object(ui.motion, "install"))
        self.enterContext(patch.object(splash, "_enabled", return_value=True))
        self.enterContext(patch.object(splash.settings_store, "load", return_value={}))
        self.enterContext(patch.object(splash.motion, "animations_enabled", return_value=animate))
        splash.show("9.9.9")
        startup = splash._active
        seen = []

        def answer(*_args):
            seen.append((QThread.currentThread().loopLevel(), self.window.isVisible(),
                         shiboken6.isValid(startup) and startup.isVisible()))
            return QMessageBox.StandardButton.Yes

        self.question.side_effect = answer
        timed_out = []
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(lambda: (timed_out.append(True), self.app.quit()))
        guard.start(3000)
        try:
            self.assertEqual(ui.main(), 0)
        finally:
            guard.stop()
            self.app.aboutToQuit.disconnect(self.window._perform_shutdown_cleanup)
        self.assertEqual(timed_out, [])
        self.assertEqual(seen, [(1, True, False)])
        self.shell.assert_called_once()
        self.window._perform_shutdown_cleanup.assert_called_once_with()
        self.assertTrue(self.window._mr_enabled)


if __name__ == "__main__":
    unittest.main()
