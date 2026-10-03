"""Account persistence and recovery from encryption or replacement failures."""

import json
import os
import tempfile
import unittest
from unittest import mock

from classes import account_manager as am
from classes.encryption import HardwareEncryption


class SaveAccountsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patcher = mock.patch.object(am, "get_data_dir", return_value=self.folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        machine = mock.patch.object(HardwareEncryption, "_get_machine_id", return_value="test-machine")
        machine.start()
        self.addCleanup(machine.stop)

    def make_manager(self, encrypted):
        if encrypted:
            config = os.path.join(self.folder.name, "encryption_config.json")
            with open(config, "w") as handle:
                json.dump({"encryption_enabled": True, "encryption_method": "hardware"}, handle)
        manager = am.RobloxAccountManager()
        manager.accounts = {"alice": {"username": "alice", "cookie": "c1", "note": "keep me"}}
        manager.save_accounts()
        return manager

    def test_plain_round_trip(self):
        manager = self.make_manager(encrypted=False)
        again = am.RobloxAccountManager()
        self.assertEqual(again.accounts["alice"]["note"], "keep me")

    def test_encrypted_round_trip(self):
        manager = self.make_manager(encrypted=True)
        again = am.RobloxAccountManager()
        self.assertEqual(again.accounts["alice"]["note"], "keep me")

    def test_encryption_failure_leaves_existing_file_intact(self):
        manager = self.make_manager(encrypted=True)
        manager.accounts["bob"] = {"username": "bob", "cookie": "c2"}
        with mock.patch.object(manager.encryptor, "encrypt_data", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                manager.save_accounts()
        again = am.RobloxAccountManager()
        self.assertEqual(sorted(again.accounts), ["alice"])

    def test_replace_failure_falls_back_to_direct_write(self):
        manager = self.make_manager(encrypted=True)
        manager.accounts["bob"] = {"username": "bob", "cookie": "c2"}
        with mock.patch.object(am.os, "replace", side_effect=PermissionError("locked")):
            manager.save_accounts()
        again = am.RobloxAccountManager()
        self.assertEqual(sorted(again.accounts), ["alice", "bob"])
        self.assertFalse(os.path.exists(manager.accounts_file + ".tmp"))


if __name__ == "__main__":
    unittest.main()
