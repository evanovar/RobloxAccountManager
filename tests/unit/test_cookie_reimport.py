"""Cookie re-import preserves notes without carrying forward old passwords."""

import tempfile
import unittest
from unittest import mock

from classes import account_manager as am
from classes.operation_result import OperationResult

COOKIE = (
    "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-"
    "and-to-steal-your-ROBUX-and-items.|_"
)


class ReimportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patches = [
            mock.patch.object(am, "get_data_dir", return_value=self.folder.name),
            mock.patch.object(am.RobloxAPI, "get_user_info_from_api", return_value=("alice", 42)),
            mock.patch.object(am.RobloxAPI, "validate_cookie", return_value=OperationResult.success()),
            mock.patch.object(am.requests, "get", side_effect=RuntimeError("offline")),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.manager = am.RobloxAccountManager()

    def test_reimport_keeps_note(self):
        self.manager.accounts["alice"] = {
            "username": "alice",
            "cookie": COOKIE + "old",
            "password": "hunter2",
            "note": "main account",
        }
        result = self.manager.import_cookie_account_result(COOKIE + "new")
        self.assertTrue(result)

        account = self.manager.accounts["alice"]
        self.assertEqual(account["cookie"], COOKIE + "new")
        self.assertEqual(account["note"], "main account")
        self.assertNotIn("password", account)
        self.assertTrue(account["cookie_valid"])

    def test_new_account_has_empty_note(self):
        self.manager.import_cookie_account_result(COOKIE + "fresh")
        self.assertEqual(self.manager.accounts["alice"]["note"], "")
        self.assertNotIn("password", self.manager.accounts["alice"])

    def test_new_password_replaces_the_old_one(self):
        self.manager.accounts["alice"] = {"username": "alice", "password": "old"}
        record = self.manager._merge_existing_account("alice", {"password": "new", "note": ""})
        self.assertEqual(record["password"], "new")


if __name__ == "__main__":
    unittest.main()
