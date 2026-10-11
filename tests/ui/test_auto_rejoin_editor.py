from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog

from utils import ui


class AutoRejoinEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, **kwargs):
        self.enterContext(patch.object(ui.groups, "get_group_names", return_value=[]))
        window = ui._AutoRejoinAddWindow(SimpleNamespace(accounts={"first": {}, "second": {}}), **kwargs)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        return window

    def test_switching_destinations_shows_only_the_relevant_fields_and_keeps_input(self):
        window = self.window()
        window._place.setText("123")
        window._join_mode.setCurrentIndex(1)
        self.assertFalse(window._place_fields.isVisible())
        self.assertTrue(window._user_fields.isVisible())
        window._target_user.setText("TargetUser")
        window._join_mode.setCurrentIndex(0)
        self.assertTrue(window._place_fields.isVisible())
        self.assertFalse(window._user_fields.isVisible())
        self.assertEqual(window._place.text(), "123")
        self.assertEqual(window._target_user.text(), "TargetUser")

    def test_user_mode_applies_to_multiple_accounts_without_a_place_id(self):
        window = self.window()
        window._join_mode.setCurrentIndex(1)
        window._target_user.setText("TargetUser")
        for i in range(window._acc_list.count()):
            window._acc_list.item(i).setSelected(True)
        window._on_add()
        self.assertEqual(window.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(set(window.result_configs), {"first", "second"})
        first = window.result_configs["first"]
        self.assertEqual((first["join_mode"], first["target_user"], first["place_id"]), ("user", "TargetUser", ""))
        self.assertIsNot(first, window.result_configs["second"])

    def test_existing_place_config_opens_and_saves_without_losing_options(self):
        config = {"place_id": "123", "private_server": "private", "job_id": "job",
                  "check_interval": 30, "max_retries": 8, "check_presence": False,
                  "check_place_id": False, "check_internet": False}
        window = self.window(edit_account="first", edit_config=config)
        self.assertEqual(window._join_mode.currentData(), "place")
        window._on_add()
        self.assertEqual({key: window.result_configs["first"][key] for key in config}, config)

    def test_saved_user_target_is_restored_in_edit_mode(self):
        window = self.window(edit_account="first", edit_config={"join_mode": "user", "target_user": "123"})
        self.assertFalse(window._left_widget.isVisible())
        self.assertEqual(window._join_mode.currentData(), "user")
        self.assertEqual(window._target_user.text(), "123")
        window._on_add()
        self.assertEqual(window.result_configs["first"]["target_user"], "123")

    def test_invalid_target_is_rejected_without_closing_the_editor(self):
        window = self.window(edit_account="first", edit_config={"join_mode": "user"})
        for target in ("", "0", "Display Name", "https://example.com"):
            with self.subTest(target=target), patch.object(ui.QMessageBox, "warning") as warning:
                window._target_user.setText(target)
                window._on_add()
                warning.assert_called_once()
                self.assertEqual(window.result_configs, {})
                self.assertTrue(window.isVisible())

    def test_editor_can_expand_and_save_remains_visible_at_minimum_size(self):
        window = self.window(edit_account="first")
        window.resize(window.width() + 100, window.height() + 100)
        self.app.processEvents()
        self.assertGreater(window.width(), window.minimumWidth())
        window.resize(window.minimumSize())
        self.app.processEvents()
        self.assertTrue(window._add_btn.isVisible())
        self.assertTrue(window.rect().contains(window._add_btn.geometry().bottomRight()))
