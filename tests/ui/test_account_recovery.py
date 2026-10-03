from types import SimpleNamespace
import unittest
from unittest.mock import patch

from utils import ui


class AccountRecoveryWarningTests(unittest.TestCase):
    def test_recovery_displays_backup_path_and_explains_missing_recent_changes(self):
        source = "C:/Synthetic/AccountManagerData/saved_accounts.json.bak"
        with patch.object(ui.QMessageBox, "warning") as warning:
            ui._show_account_recovery_warning(SimpleNamespace(accounts_recovery_source=source))
        warning.assert_called_once()
        parent, title, message = warning.call_args.args
        self.assertIsNone(parent)
        self.assertEqual(title, "Accounts Recovered")
        self.assertIn(source, message)
        self.assertIn("Recent changes may be missing", message)

    def test_healthy_startup_does_not_display_a_recovery_warning(self):
        with patch.object(ui.QMessageBox, "warning") as warning:
            ui._show_account_recovery_warning(SimpleNamespace(accounts_recovery_source=None))
        warning.assert_not_called()
