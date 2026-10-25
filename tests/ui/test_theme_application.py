import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMainWindow

from features.theme_model import builtin_theme
from tests.ui.test_theme_runtime import MemoryLibrary
from utils import theme_runtime, ui


class ApplicationThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.previous = getattr(self.app, '_ram_theme_manager', None)
        self.manager = theme_runtime.ThemeManager(self.app, MemoryLibrary())
        self.app._ram_theme_manager = self.manager
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.manager.close()
        self.app._ram_theme_manager = self.previous

    def test_main_and_existing_and_new_dialogs_follow_live_colors(self):
        window = QMainWindow()
        self.windows.append(window)
        ui.AccountManagerUIQt._apply_stylesheet(window)
        dialog = ui._ImportCookieDialog(window)
        self.windows.append(dialog)
        self.manager.apply(builtin_theme('forest'))
        self.assertIn('#0D1411', window.styleSheet())
        self.assertIn('#E4EFE8', dialog.styleSheet())
        new_dialog = ui._ImportCookieDialog(window)
        self.windows.append(new_dialog)
        self.assertIn('#E4EFE8', new_dialog.styleSheet())

    def test_canceling_unsaved_theme_exit_prevents_shutdown(self):
        window = ui.AccountManagerUIQt.__new__(ui.AccountManagerUIQt)
        QMainWindow.__init__(window)
        self.windows.append(window)
        window._save_window_size = Mock()
        window._theme_editor = Mock()
        window._theme_editor.confirm_discard.return_value = False
        window._perform_shutdown_cleanup = Mock()
        window._tray_exit_requested = True
        event = Mock()
        with patch.object(ui.actions, 'load_ui_settings', return_value={}):
            window.closeEvent(event)
        event.ignore.assert_called_once()
        window._perform_shutdown_cleanup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
