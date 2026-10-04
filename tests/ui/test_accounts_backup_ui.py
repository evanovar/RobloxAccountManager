import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from classes import account_manager as am
from features import account_backup
from utils import ui

PASSWORD = "correct horse battery"


class AccountsBackupUiTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, "accounts.rambak")
        self.enterContext(patch.object(am, "get_data_dir", return_value=os.path.join(self.folder.name, "data")))
        self.manager = am.RobloxAccountManager()
        self.manager.accounts = {"alice": {"username": "alice", "cookie": "C", "note": "n"}}
        self.shown = []
        self.window = SimpleNamespace(
            manager=self.manager,
            _ask_backup_password=MagicMock(return_value=PASSWORD),
            _show_operation_error=MagicMock(),
            _refresh_account_list=MagicMock(),
        )
        self.enterContext(patch.object(ui, "_show_info", side_effect=lambda parent, title, message: self.shown.append((title, message))))
        self.enterContext(patch.object(ui, "_show_error", side_effect=lambda parent, title, message: self.shown.append((title, message))))

    def export(self, path=None):
        chosen = (self.path if path is None else path, "")
        with patch.object(ui.QFileDialog, "getSaveFileName", return_value=chosen):
            ui.AccountManagerUIQt._on_sett_export_accounts(self.window)

    def import_(self, reply=QMessageBox.StandardButton.No, path=None):
        chosen = (self.path if path is None else path, "")
        with patch.object(ui.QFileDialog, "getOpenFileName", return_value=chosen), \
                patch.object(ui.QMessageBox, "question", return_value=reply):
            ui.AccountManagerUIQt._on_sett_import_accounts(self.window)

    def test_export_writes_a_backup_that_can_be_read(self):
        self.export()
        self.assertTrue(os.path.exists(self.path))
        self.assertTrue(account_backup.read_backup(self.path, PASSWORD))
        self.assertEqual(self.shown[-1][0], "Export Accounts")

    def test_export_without_accounts_explains_why(self):
        self.manager.accounts = {}
        self.export()
        self.assertFalse(os.path.exists(self.path))
        self.assertIn("no saved accounts", self.shown[-1][1])

    def test_cancelling_the_file_dialog_does_nothing(self):
        self.export(path="")
        self.window._ask_backup_password.assert_not_called()
        self.assertEqual(self.shown, [])

    def test_cancelling_the_password_does_nothing(self):
        self.window._ask_backup_password.return_value = None
        self.export()
        self.assertFalse(os.path.exists(self.path))

    def test_export_failure_goes_to_the_error_dialog(self):
        self.window._ask_backup_password.return_value = "short"
        self.export()
        self.window._show_operation_error.assert_called_once()
        self.assertEqual(self.window._show_operation_error.call_args.args[0].code, "BACKUP_PASSWORD_TOO_SHORT")

    def test_import_adds_accounts_and_refreshes_the_list(self):
        self.export()
        self.manager.accounts = {}
        self.import_()
        self.assertEqual(list(self.manager.accounts), ["alice"])
        self.window._refresh_account_list.assert_called_once()
        self.assertEqual(self.shown[-1][0], "Import Accounts")

    def test_answering_yes_replaces_existing_accounts(self):
        self.export()
        self.manager.accounts = {"alice": {"username": "alice", "cookie": "LOCAL"}}
        self.import_(reply=QMessageBox.StandardButton.No)
        self.assertEqual(self.manager.accounts["alice"]["cookie"], "LOCAL")
        self.import_(reply=QMessageBox.StandardButton.Yes)
        self.assertEqual(self.manager.accounts["alice"]["cookie"], "C")

    def test_cancelling_the_replace_question_imports_nothing(self):
        self.export()
        self.manager.accounts = {}
        self.import_(reply=QMessageBox.StandardButton.Cancel)
        self.assertEqual(self.manager.accounts, {})
        self.window._refresh_account_list.assert_not_called()

    def test_wrong_password_is_shown_as_an_error(self):
        self.export()
        self.window._ask_backup_password.return_value = "wrong password"
        self.import_()
        self.assertEqual(self.window._show_operation_error.call_args.args[0].code, "BACKUP_PASSWORD_INVALID")


class AskBackupPasswordTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.window = SimpleNamespace()

    def ask(self, answers, confirm):
        with patch.object(QInputDialog, "getText", side_effect=answers), \
                patch.object(ui.QMessageBox, "warning") as warning:
            result = ui.AccountManagerUIQt._ask_backup_password(self.window, confirm)
        return result, warning

    def test_single_prompt_for_import(self):
        self.assertEqual(self.ask([("secret-pass", True)], confirm=False)[0], "secret-pass")

    def test_export_asks_twice_and_returns_the_matching_password(self):
        result, warning = self.ask([("secret-pass", True), ("secret-pass", True)], confirm=True)
        self.assertEqual(result, "secret-pass")
        warning.assert_not_called()

    def test_mismatch_asks_again(self):
        answers = [("one", True), ("two", True), ("secret-pass", True), ("secret-pass", True)]
        result, warning = self.ask(answers, confirm=True)
        self.assertEqual(result, "secret-pass")
        warning.assert_called_once()

    def test_cancelling_either_prompt_returns_none(self):
        self.assertIsNone(self.ask([("", False)], confirm=True)[0])
        self.assertIsNone(self.ask([("secret-pass", True), ("", False)], confirm=True)[0])


if __name__ == "__main__":
    unittest.main()
