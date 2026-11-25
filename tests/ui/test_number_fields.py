import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QAbstractSpinBox, QApplication

from features import settings_store
from utils import ui


class NumberFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(settings_store, "_SETTINGS_PATH", str(Path(directory) / "ui_settings.json")))
        settings_store.invalidate()
        self.addCleanup(settings_store.invalidate)

    def main_window(self):
        manager = MagicMock()
        manager.accounts = {}
        manager.get_encryption_method.return_value = "none"
        manager.get_secure_setting.return_value = ""
        with patch.object(ui.QTimer, "singleShot"), \
                patch.object(ui.threading.Thread, "start"), \
                patch.object(ui.AccountManagerUIQt, "_setup_system_tray"), \
                patch.object(ui.EncryptionConfig, "is_setup_complete", return_value=True):
            window = ui.AccountManagerUIQt(manager)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    def assert_numbers_fit(self, fields):
        self.assertTrue(fields)
        for field in fields:
            editor = field.lineEdit()
            with self.subTest(field=field.objectName() or field.text()):
                # a local stylesheet with border and padding used to squash this to 1px
                self.assertGreaterEqual(editor.width(), editor.fontMetrics().horizontalAdvance(field.text()) + 4)

    def test_anti_afk_numbers_are_visible(self):
        window = self.main_window()
        window.show()
        fields = [window._afk_press_spin, window._afk_interval_spin, window._afk_tooltip_size_spin]
        # open the page that holds the anti-afk panel
        page = fields[0]
        while page.parentWidget() is not None and page.parentWidget() is not window._page_stack:
            page = page.parentWidget()
        window._page_stack.setCurrentWidget(page)
        self.app.processEvents()
        self.assertTrue(all(field.isVisible() for field in fields))
        self.assert_numbers_fit(fields)

    def test_account_creator_amount_is_visible(self):
        window = self.main_window()
        window.show()
        dialog = ui._AccountCreatorDialog(window)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        self.assert_numbers_fit(dialog.findChildren(QAbstractSpinBox))


if __name__ == "__main__":
    unittest.main()
