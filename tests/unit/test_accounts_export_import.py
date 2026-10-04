import json
import os
import tempfile
import unittest
from unittest.mock import patch

from classes import account_manager as am
from features import account_backup as backup

PASSWORD = "correct horse battery"
ACCOUNTS = {
    "alice": {"username": "alice", "cookie": "COOKIE-ALICE", "note": "main", "password": "pw-a"},
    "bob": {"username": "bob", "cookie": "COOKIE-BOB", "note": ""},
}


class BackupFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, "accounts.rambak")

    def export(self, accounts=ACCOUNTS, password=PASSWORD):
        return backup.export_accounts(accounts, self.path, password)

    def rewrite(self, change):
        with open(self.path, encoding="utf-8") as handle:
            document = json.load(handle)
        change(document)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(document, handle)

    def test_round_trip_keeps_every_field(self):
        result = self.export()
        self.assertTrue(result)
        self.assertEqual(result.data["count"], 2)
        read = backup.read_backup(self.path, PASSWORD)
        self.assertTrue(read)
        self.assertEqual(read.data["accounts"], ACCOUNTS)
        self.assertEqual(read.data["skipped"], 0)

    def test_file_does_not_contain_readable_secrets(self):
        self.export()
        with open(self.path, encoding="utf-8") as handle:
            text = handle.read()
        for secret in ("COOKIE-ALICE", "pw-a", "alice", PASSWORD):
            self.assertNotIn(secret, text)

    def test_every_export_uses_a_new_salt(self):
        self.export()
        first = json.load(open(self.path, encoding="utf-8"))["salt"]
        self.export()
        second = json.load(open(self.path, encoding="utf-8"))["salt"]
        self.assertNotEqual(first, second)

    def test_short_password_is_refused_and_nothing_is_written(self):
        result = self.export(password="short")
        self.assertEqual(result.code, "BACKUP_PASSWORD_TOO_SHORT")
        self.assertFalse(os.path.exists(self.path))

    def test_nothing_to_export(self):
        self.assertEqual(self.export(accounts={}).code, "BACKUP_NO_ACCOUNTS")

    def test_unwritable_location_is_reported(self):
        result = backup.export_accounts(ACCOUNTS, self.folder.name, PASSWORD)
        self.assertEqual(result.code, "BACKUP_WRITE_FAILED")

    def test_wrong_password_is_reported(self):
        self.export()
        self.assertEqual(backup.read_backup(self.path, "not the password").code, "BACKUP_PASSWORD_INVALID")

    def test_tampered_data_is_not_accepted(self):
        self.export()

        def tamper(document):
            data = document["data"]["ciphertext"]
            document["data"]["ciphertext"] = ("A" if data[0] != "A" else "B") + data[1:]

        self.rewrite(tamper)
        self.assertEqual(backup.read_backup(self.path, PASSWORD).code, "BACKUP_PASSWORD_INVALID")

    def test_files_that_are_not_backups(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("not json at all")
        self.assertEqual(backup.read_backup(self.path, PASSWORD).code, "BACKUP_UNREADABLE")
        self.assertEqual(backup.read_backup(os.path.join(self.folder.name, "missing"), PASSWORD).code, "BACKUP_UNREADABLE")

        for document in ([], {"accounts": {}}, {"format": "other", "salt": "AA==", "data": {}}):
            with self.subTest(document=document):
                with open(self.path, "w", encoding="utf-8") as handle:
                    json.dump(document, handle)
                self.assertEqual(backup.read_backup(self.path, PASSWORD).code, "BACKUP_FORMAT_INVALID")

    def test_unknown_version_is_refused(self):
        self.export()
        self.rewrite(lambda document: document.update(version=99))
        self.assertEqual(backup.read_backup(self.path, PASSWORD).code, "BACKUP_VERSION_UNSUPPORTED")

    def test_damaged_encoding_is_reported(self):
        self.export()
        self.rewrite(lambda document: document["data"].pop("tag"))
        self.assertEqual(backup.read_backup(self.path, PASSWORD).code, "BACKUP_MALFORMED")
        self.export()
        self.rewrite(lambda document: document.update(salt="!!not base64!!"))
        self.assertEqual(backup.read_backup(self.path, PASSWORD).code, "BACKUP_MALFORMED")

    def test_unusable_records_are_dropped_and_counted(self):
        accounts = {**ACCOUNTS, "nocookie": {"username": "x", "cookie": "  "}, "wrongtype": "text"}
        self.export(accounts=accounts)
        read = backup.read_backup(self.path, PASSWORD)
        self.assertEqual(sorted(read.data["accounts"]), ["alice", "bob"])
        self.assertEqual(read.data["skipped"], 2)


class MergeTests(unittest.TestCase):
    def test_new_accounts_are_added_and_existing_ones_kept_by_default(self):
        existing = {"alice": {"cookie": "old"}}
        imported = {"alice": {"cookie": "new"}, "bob": {"cookie": "b"}}
        merged, added, updated, skipped = backup.merge_accounts(existing, imported, overwrite=False)
        self.assertEqual(merged, {"alice": {"cookie": "old"}, "bob": {"cookie": "b"}})
        self.assertEqual((added, updated, skipped), (1, 0, 1))

    def test_overwrite_replaces_existing_accounts(self):
        merged, added, updated, skipped = backup.merge_accounts(
            {"alice": {"cookie": "old"}}, {"alice": {"cookie": "new"}}, overwrite=True
        )
        self.assertEqual(merged["alice"]["cookie"], "new")
        self.assertEqual((added, updated, skipped), (0, 1, 0))

    def test_existing_order_is_kept_and_input_is_not_modified(self):
        existing = {"b": {"cookie": "1"}, "a": {"cookie": "2"}}
        merged, *_ = backup.merge_accounts(existing, {"c": {"cookie": "3"}}, overwrite=False)
        self.assertEqual(list(merged), ["b", "a", "c"])
        self.assertEqual(list(existing), ["b", "a"])


class ImportAccountsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.enterContext(patch.object(am, "get_data_dir", return_value=os.path.join(self.folder.name, "data")))
        self.path = os.path.join(self.folder.name, "accounts.rambak")
        backup.export_accounts(ACCOUNTS, self.path, PASSWORD)
        self.manager = am.RobloxAccountManager()

    def reopened(self):
        return am.RobloxAccountManager().accounts

    def test_import_into_an_empty_manager_saves_to_disk(self):
        result = backup.import_accounts(self.manager, self.path, PASSWORD)
        self.assertTrue(result)
        self.assertEqual((result.data["added"], result.data["updated"], result.data["skipped"]), (2, 0, 0))
        self.assertEqual(sorted(self.reopened()), ["alice", "bob"])
        self.assertEqual(self.reopened()["alice"]["cookie"], "COOKIE-ALICE")
        self.assertIn("cookie_valid", self.reopened()["bob"])

    def test_existing_accounts_are_skipped_unless_overwriting(self):
        self.manager.accounts = {"alice": {"username": "alice", "cookie": "LOCAL", "note": "keep"}}
        result = backup.import_accounts(self.manager, self.path, PASSWORD)
        self.assertEqual((result.data["added"], result.data["skipped"]), (1, 1))
        self.assertEqual(self.manager.accounts["alice"]["cookie"], "LOCAL")

        result = backup.import_accounts(self.manager, self.path, PASSWORD, overwrite=True)
        self.assertEqual((result.data["added"], result.data["updated"]), (0, 2))
        self.assertEqual(self.manager.accounts["alice"]["cookie"], "COOKIE-ALICE")

    def test_wrong_password_changes_nothing(self):
        result = backup.import_accounts(self.manager, self.path, "wrong password")
        self.assertEqual(result.code, "BACKUP_PASSWORD_INVALID")
        self.assertEqual(self.manager.accounts, {})

    def test_failed_save_restores_the_previous_accounts(self):
        self.manager.accounts = {"carol": {"username": "carol", "cookie": "C"}}
        with patch.object(self.manager, "save_accounts", side_effect=OSError("disk full")):
            result = backup.import_accounts(self.manager, self.path, PASSWORD)
        self.assertFalse(result)
        self.assertEqual(list(self.manager.accounts), ["carol"])

    def test_a_backup_without_usable_accounts_is_refused(self):
        backup.export_accounts({"x": {"username": "x", "cookie": "ok"}}, self.path, PASSWORD)
        with patch.object(backup, "read_backup", return_value=backup.OperationResult.success(data={"accounts": {}, "skipped": 3})):
            self.assertEqual(backup.import_accounts(self.manager, self.path, PASSWORD).code, "BACKUP_NO_ACCOUNTS")


if __name__ == "__main__":
    unittest.main()
