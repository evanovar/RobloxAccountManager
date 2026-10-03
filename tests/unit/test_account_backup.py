import base64
import builtins
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from classes import account_manager as am
from classes.encryption import HardwareEncryption


class AccountBackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        for name in ("_get_machine_id", "_get_v264_machine_id", "_get_legacy_machine_id"):
            self.enterContext(patch.object(HardwareEncryption, name, return_value="test-machine"))
        self.password = "synthetic-encryption-password-中文"
        self.accounts = {"alice": {
            "cookie": "synthetic-cookie-never-expose", "password": "synthetic-login-password",
            "note": "previous note", "cookie_valid": None,
        }}

    def make_manager(self, mode="none"):
        folder = self.enterContext(tempfile.TemporaryDirectory(dir=self.directory))
        self.enterContext(patch.object(am, "get_data_dir", return_value=folder))
        manager = am.RobloxAccountManager()
        manager.accounts = copy.deepcopy(self.accounts)
        manager.secure_settings = {"example": "previous secure setting"}
        manager.save_accounts()
        if mode != "none":
            manager.switch_encryption_method(mode, password=self.password)
        return manager

    def reopen(self, mode="none"):
        return am.RobloxAccountManager(self.password if mode == "password" else None)

    def paths(self, manager):
        return Path(manager.accounts_file), Path(manager.accounts_backup_file)

    def next_save(self, manager):
        manager.accounts["alice"]["note"] = "latest note"
        manager.secure_settings["example"] = "latest secure setting"
        manager.save_accounts()

    def test_first_save_creates_a_usable_snapshot_in_every_mode(self):
        for mode in ("none", "hardware", "password"):
            with self.subTest(mode=mode):
                manager = self.make_manager(mode)
                main, backup = self.paths(manager)
                self.assertEqual(main.read_bytes(), backup.read_bytes())
                data, _, encrypted = manager._read_accounts_payload(str(backup), backup=True)
                self.assertEqual(data["accounts"], self.accounts)
                self.assertEqual(encrypted, mode != "none")
                if encrypted:
                    self.assertNotIn(b"synthetic-cookie-never-expose", backup.read_bytes())

    def test_next_save_keeps_the_previous_bytes_and_secure_settings(self):
        for mode in ("none", "hardware", "password"):
            with self.subTest(mode=mode):
                manager = self.make_manager(mode)
                main, backup = self.paths(manager)
                before = main.read_bytes()
                self.next_save(manager)
                self.assertEqual(backup.read_bytes(), before)
                data, _, _ = manager._read_accounts_payload(str(backup), backup=True)
                self.assertEqual(data["accounts"]["alice"]["note"], "previous note")
                self.assertEqual(data["secure_settings"]["example"], "previous secure setting")
                self.assertEqual(self.reopen(mode).accounts["alice"]["note"], "latest note")

    def test_corrupt_main_recovers_previous_accounts_without_rewriting_files(self):
        for mode in ("none", "hardware", "password"):
            with self.subTest(mode=mode):
                manager = self.make_manager(mode)
                self.next_save(manager)
                main, backup = self.paths(manager)
                main.write_bytes(b"broken JSON")
                before = (main.read_bytes(), backup.read_bytes())
                recovered = self.reopen(mode)
                self.assertEqual(recovered.accounts, self.accounts)
                self.assertEqual(recovered.secure_settings, {"example": "previous secure setting"})
                self.assertEqual(recovered.accounts_recovery_source, str(backup))
                self.assertEqual((main.read_bytes(), backup.read_bytes()), before)

    def test_missing_main_uses_the_backup(self):
        manager = self.make_manager()
        main, backup = self.paths(manager)
        main.unlink()
        recovered = self.reopen()
        self.assertEqual(recovered.accounts, self.accounts)
        self.assertEqual(recovered.accounts_recovery_source, str(backup))
        self.assertFalse(main.exists())

    def test_invalid_utf8_and_invalid_account_shapes_use_the_backup(self):
        for contents in (b"\xff", b"[]", b'{"accounts": []}', b'{"accounts": {"alice": "invalid"}}'):
            with self.subTest(contents=contents):
                manager = self.make_manager()
                main, _ = self.paths(manager)
                main.write_bytes(contents)
                self.assertEqual(self.reopen().accounts, self.accounts)

    def test_valid_main_wins_even_when_the_backup_is_corrupt(self):
        manager = self.make_manager()
        self.next_save(manager)
        _, backup = self.paths(manager)
        backup.write_bytes(b"broken backup")
        reopened = self.reopen()
        self.assertEqual(reopened.accounts["alice"]["note"], "latest note")
        self.assertIsNone(reopened.accounts_recovery_source)

    def test_both_files_invalid_still_reports_an_error_and_preserves_them(self):
        manager = self.make_manager()
        main, backup = self.paths(manager)
        main.write_bytes(b"bad main")
        backup.write_bytes(b"bad backup")
        with self.assertRaises(am.AccountDataError):
            self.reopen()
        self.assertEqual(main.read_bytes(), b"bad main")
        self.assertEqual(backup.read_bytes(), b"bad backup")

    def test_wrong_password_does_not_recover_or_modify_encrypted_files(self):
        manager = self.make_manager("password")
        main, backup = self.paths(manager)
        before = (main.read_bytes(), backup.read_bytes())
        with self.assertRaises(am.AccountPasswordError):
            am.RobloxAccountManager("wrong password")
        self.assertEqual((main.read_bytes(), backup.read_bytes()), before)

    def test_tampered_ciphertext_recovers_only_with_the_correct_password(self):
        manager = self.make_manager("password")
        self.next_save(manager)
        main, _ = self.paths(manager)
        document = json.loads(main.read_text(encoding="utf-8"))
        ciphertext = bytearray(base64.b64decode(document["data"]["ciphertext"]))
        ciphertext[0] ^= 1
        document["data"]["ciphertext"] = base64.b64encode(ciphertext).decode()
        main.write_text(json.dumps(document), encoding="utf-8")
        self.assertEqual(self.reopen("password").accounts, self.accounts)
        with self.assertRaises(am.AccountPasswordError):
            am.RobloxAccountManager("wrong password")

    def test_plaintext_backup_cannot_bypass_password_encryption(self):
        manager = self.make_manager("password")
        main, backup = self.paths(manager)
        backup.write_text(json.dumps({"accounts": self.accounts}), encoding="utf-8")
        with self.assertRaises(am.AccountPasswordError):
            am.RobloxAccountManager("wrong password")
        main.write_bytes(b"broken JSON")
        with self.assertRaises(am.AccountDataError):
            self.reopen("password")

    def test_save_after_recovery_keeps_the_good_backup(self):
        manager = self.make_manager("password")
        main, backup = self.paths(manager)
        self.next_save(manager)
        backup_before = backup.read_bytes()
        main.write_bytes(b"broken JSON")
        recovered = self.reopen("password")
        recovered.accounts["alice"]["note"] = "repaired note"
        recovered.save_accounts()
        self.assertEqual(backup.read_bytes(), backup_before)
        self.assertEqual(self.reopen("password").accounts["alice"]["note"], "repaired note")
        self.assertFalse(recovered._using_accounts_backup)

    def test_external_corruption_is_never_rotated_over_a_valid_backup(self):
        manager = self.make_manager()
        self.next_save(manager)
        main, backup = self.paths(manager)
        before = backup.read_bytes()
        main.write_bytes(b"damaged after startup")
        manager.save_accounts()
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(self.reopen().accounts["alice"]["note"], "latest note")

    def test_backup_publication_failure_aborts_without_touching_the_main(self):
        manager = self.make_manager()
        main, backup = self.paths(manager)
        before = (main.read_bytes(), backup.read_bytes())
        manager.accounts["alice"]["note"] = "unsaved note"
        with patch.object(am.os, "replace", side_effect=PermissionError("backup locked")):
            with self.assertRaises(PermissionError):
                manager.save_accounts()
        self.assertEqual((main.read_bytes(), backup.read_bytes()), before)
        self.assertFalse(Path(str(backup) + ".tmp").exists())

    def test_main_publication_failure_preserves_main_and_a_valid_backup(self):
        manager = self.make_manager()
        self.next_save(manager)
        main, backup = self.paths(manager)
        before = main.read_bytes()
        replace = am.os.replace

        def fail_main(source, destination):
            if destination == str(main):
                raise PermissionError("main locked")
            return replace(source, destination)

        manager.accounts["alice"]["note"] = "unsaved note"
        with patch.object(am.os, "replace", side_effect=fail_main):
            with self.assertRaises(PermissionError):
                manager.save_accounts()
        self.assertEqual(main.read_bytes(), before)
        self.assertEqual(backup.read_bytes(), before)
        self.assertFalse(Path(str(main) + ".tmp").exists())

    def test_partial_temporary_write_does_not_truncate_the_original(self):
        manager = self.make_manager()
        main, backup = self.paths(manager)
        before = main.read_bytes()
        real_open = builtins.open

        class PartialWriter:
            def __enter__(self):
                self.handle = real_open(str(main) + ".tmp", "wb")
                return self

            def __exit__(self, *args):
                self.handle.close()

            def write(self, contents):
                self.handle.write(contents[:8])
                raise OSError("disk full during write")

        def partial_open(path, mode="r", **kwargs):
            if path == str(main) + ".tmp" and mode == "wb":
                return PartialWriter()
            return real_open(path, mode, **kwargs)

        manager.accounts["alice"]["note"] = "unsaved note"
        with patch.object(am, "open", side_effect=partial_open, create=True):
            with self.assertRaises(OSError):
                manager.save_accounts()
        self.assertEqual(main.read_bytes(), before)
        self.assertEqual(backup.read_bytes(), before)
        self.assertFalse(Path(str(main) + ".tmp").exists())

    def test_temporary_cleanup_failure_does_not_hide_the_save_error(self):
        manager = self.make_manager()
        main, _ = self.paths(manager)
        before = main.read_bytes()
        replace, remove = am.os.replace, am.os.remove

        def fail_main(source, destination):
            if destination == str(main):
                raise PermissionError("main replacement failed")
            return replace(source, destination)

        def fail_cleanup(path):
            if path == str(main) + ".tmp":
                raise PermissionError("temporary file locked")
            return remove(path)

        with patch.object(am.os, "replace", side_effect=fail_main), patch.object(am.os, "remove", side_effect=fail_cleanup):
            with self.assertRaisesRegex(PermissionError, "main replacement failed"):
                manager.save_accounts()
        self.assertEqual(main.read_bytes(), before)
        Path(str(main) + ".tmp").unlink()

    def test_serialization_failure_does_not_change_the_main_or_backup(self):
        for mode in ("none", "password"):
            with self.subTest(mode=mode):
                manager = self.make_manager(mode)
                main, backup = self.paths(manager)
                before = (main.read_bytes(), backup.read_bytes())
                manager.accounts["invalid"] = object()
                with self.assertRaises(TypeError):
                    manager.save_accounts()
                self.assertEqual((main.read_bytes(), backup.read_bytes()), before)

    def test_encryption_switch_refreshes_backup_under_the_current_method(self):
        manager = self.make_manager()
        for mode in ("hardware", "password", "none"):
            with self.subTest(mode=mode):
                manager.switch_encryption_method(mode, password=self.password)
                main, backup = self.paths(manager)
                self.assertEqual(bool(json.loads(backup.read_text(encoding="utf-8")).get("encrypted")), mode != "none")
                main_before = main.read_bytes()
                main.write_bytes(b"broken JSON")
                recovered = self.reopen(mode)
                self.assertEqual(recovered.accounts, self.accounts)
                self.assertEqual(recovered.secure_settings, manager.secure_settings)
                main.write_bytes(main_before)

    def test_failed_switch_restores_the_previous_backup_and_config(self):
        manager = self.make_manager("password")
        self.next_save(manager)
        main, backup = self.paths(manager)
        config = Path(manager.encryption_config.config_file)
        before = (main.read_bytes(), backup.read_bytes(), config.read_bytes())
        replace = am.os.replace

        def fail_main(source, destination):
            if destination == str(main):
                raise PermissionError("main locked")
            return replace(source, destination)

        with patch.object(am.os, "replace", side_effect=fail_main):
            with self.assertRaises(PermissionError):
                manager.switch_encryption_method("none")
        self.assertEqual((main.read_bytes(), backup.read_bytes(), config.read_bytes()), before)
        main.write_bytes(b"broken JSON")
        self.assertEqual(self.reopen("password").accounts, self.accounts)

    def test_unreadable_main_uses_the_backup(self):
        manager = self.make_manager()
        main, _ = self.paths(manager)
        real_open = builtins.open

        def unreadable(path, mode="r", **kwargs):
            if path == str(main) and mode == "rb":
                raise PermissionError("main locked")
            return real_open(path, mode, **kwargs)

        with patch.object(am, "open", side_effect=unreadable, create=True):
            self.assertEqual(self.reopen().accounts, self.accounts)

    def test_missing_password_salt_still_fails_without_changing_accounts(self):
        manager = self.make_manager("password")
        main, backup = self.paths(manager)
        before = (main.read_bytes(), backup.read_bytes())
        config = Path(manager.encryption_config.config_file)
        data = json.loads(config.read_text(encoding="utf-8"))
        data.pop("salt")
        config.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(am.AccountDataError):
            self.reopen("password")
        self.assertEqual((main.read_bytes(), backup.read_bytes()), before)
