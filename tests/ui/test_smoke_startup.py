from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

from utils import splash, ui


class SmokeStartupTests(unittest.TestCase):
    def test_smoke_check_creates_a_window_then_exits_without_restoring_multi_roblox(self):
        app = QApplication.instance() or QApplication([])
        window = QMainWindow()
        window._perform_shutdown_cleanup = Mock()
        window._restore_multi_roblox = Mock()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        self.addCleanup(splash.dismiss)
        manager = SimpleNamespace(accounts_recovery_source=None)
        shown = []
        original_show = window.show

        def show_window():
            original_show()
            shown.append(window.isVisible())

        timed_out = []
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(lambda: (timed_out.append(True), app.quit()))
        with patch.object(ui, "EncryptionConfig") as config, \
                patch.object(ui, "RobloxAccountManager", return_value=manager), \
                patch.object(ui, "AccountManagerUIQt", return_value=window), \
                patch.object(window, "show", side_effect=show_window), \
                patch.object(ui.motion, "install"):
            config.return_value.is_encryption_enabled.return_value = False
            guard.start(3000)
            try:
                self.assertEqual(ui.main(smoke_test=True), 0)
            finally:
                guard.stop()
                app.aboutToQuit.disconnect(window._perform_shutdown_cleanup)
        self.assertEqual(timed_out, [])
        self.assertEqual(shown, [True])
        window._perform_shutdown_cleanup.assert_called_once_with()
        window._restore_multi_roblox.assert_not_called()


if __name__ == "__main__":
    unittest.main()
