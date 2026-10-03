import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from classes import account_manager as am
from classes.encryption import HardwareEncryption

ACCOUNTS = {"alice": {"username": "alice", "cookie": "c1", "note": "keep me", "cookie_valid": None}}


class SwitchEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for patcher in (
            mock.patch.object(am, "get_data_dir", return_value=self.folder.name),
            mock.patch.object(HardwareEncryption, "_get_machine_id", return_value="test-machine"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.manager = am.RobloxAccountManager()
        self.manager.accounts = json.loads(json.dumps(ACCOUNTS))
        self.manager.save_accounts()

    def reopen(self, password=None):
        return am.RobloxAccountManager(password)

    def test_round_trip_through_every_method(self):
        self.manager.switch_encryption_method("hardware")
        self.assertEqual(self.reopen().accounts, ACCOUNTS)
        self.manager.switch_encryption_method("password", password="pw", salt="ab" * 32)
        self.assertEqual(self.reopen("pw").accounts, ACCOUNTS)
        self.manager.switch_encryption_method("none")
        self.assertEqual(self.reopen().accounts, ACCOUNTS)

    def test_missing_password_leaves_current_encryption_untouched(self):
        self.manager.switch_encryption_method("hardware")
        with self.assertRaises(ValueError):
            self.manager.switch_encryption_method("password", password=None)
        self.assertEqual(self.manager.get_encryption_method(), "hardware")
        self.assertEqual(self.reopen().accounts, ACCOUNTS)

    def test_failed_save_restores_previous_encryption(self):
        self.manager.switch_encryption_method("password", password="pw", salt="ab" * 32)
        with mock.patch.object(self.manager, "save_accounts", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.manager.switch_encryption_method("none")
        self.assertEqual(self.manager.get_encryption_method(), "password")
        self.assertEqual(self.reopen("pw").accounts, ACCOUNTS)


if __name__ == "__main__":
    unittest.main()
