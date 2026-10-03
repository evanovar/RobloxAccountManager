"""Password configs omit fast verifiers and retain encrypted-file compatibility."""

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from classes import account_manager as am
from classes import encryption
from classes.encryption import EncryptionConfig, PasswordEncryption


class EncryptionConfigPasswordTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.directory / "encryption_config.json"
        self.salt = base64.b64encode(b"s" * 32).decode()

    def read_config(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_new_password_config_contains_salt_without_password_hash(self):
        config = EncryptionConfig(str(self.path))
        config.enable_password_encryption(self.salt)
        persisted = self.read_config()
        self.assertNotIn("password_hash", persisted)
        self.assertEqual(persisted["salt"], self.salt)
        self.assertEqual(persisted["encryption_method"], "password")
        self.assertTrue(persisted["encryption_enabled"])
        self.assertTrue(EncryptionConfig(str(self.path)).is_setup_complete())

    def test_old_hash_is_ignored_then_removed_on_the_next_save(self):
        legacy = {
            "encryption_enabled": True,
            "encryption_method": "password",
            "salt": self.salt,
            "password_hash": "obsolete-verifier",
            "custom_setting": {"keep": True},
        }
        self.path.write_text(json.dumps(legacy), encoding="utf-8")
        before = self.path.read_bytes()
        config = EncryptionConfig(str(self.path))
        self.assertNotIn("password_hash", config.config)
        self.assertEqual(self.path.read_bytes(), before)
        config.save_config()
        self.assertEqual(self.read_config(), {key: value for key, value in legacy.items() if key != "password_hash"})

    def test_save_also_discards_hashes_reintroduced_into_memory(self):
        config = EncryptionConfig(str(self.path))
        config.config = {"salt": self.salt, "password_hash": "stale-restored-value"}
        config.save_config()
        self.assertEqual(self.read_config(), {"salt": self.salt})
        self.assertNotIn("password_hash", config.config)

    def test_direct_write_fallback_does_not_persist_a_legacy_hash(self):
        config = EncryptionConfig(str(self.path))
        config.config = {"salt": self.salt, "password_hash": "legacy-verifier"}
        with patch.object(encryption.os, "replace", side_effect=PermissionError("locked")):
            config.save_config()
        self.assertEqual(self.read_config(), {"salt": self.salt})
        self.assertFalse(Path(str(self.path) + ".tmp").exists())


class ExistingPasswordAccountsTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(am, "get_data_dir", return_value=str(self.directory)))
        self.config_path = self.directory / "encryption_config.json"
        self.accounts_path = self.directory / "saved_accounts.json"
        self.payload = {
            "accounts": {"demo": {"cookie": "synthetic-cookie", "note": "keep", "cookie_valid": None}},
            "secure_settings": {"example": "synthetic-setting"},
        }

    def write_existing_accounts(self, password, legacy_latin1=False):
        writer = PasswordEncryption(password)
        if legacy_latin1:
            writer.key = encryption.PBKDF2(password.encode("latin-1"), writer.salt, dkLen=32, count=100000)
        package = writer.encrypt_data(self.payload)
        if legacy_latin1:
            package.pop("password_encoding")
        self.accounts_path.write_text(json.dumps({"encrypted": True, "data": package}), encoding="utf-8")
        self.config_path.write_text(json.dumps({
            "encryption_enabled": True,
            "encryption_method": "password",
            "setup_completed": True,
            "salt": writer.get_salt_b64(),
            # Deliberately incorrect: the authenticated payload must decide validity.
            "password_hash": "incorrect-old-verifier",
        }), encoding="utf-8")

    def test_old_configs_unlock_and_save_without_reencrypting_account_data(self):
        for password, legacy in (("correct-password", False), ("password-中文", False), ("café-password", True)):
            with self.subTest(password_encoding="latin-1" if legacy else "utf-8"):
                self.write_existing_accounts(password, legacy)
                accounts_before = self.accounts_path.read_bytes()
                config_before = self.config_path.read_bytes()
                original_salt = json.loads(config_before)["salt"]
                manager = am.RobloxAccountManager(password)
                self.assertEqual(manager.accounts, self.payload["accounts"])
                self.assertEqual(manager.secure_settings, self.payload["secure_settings"])
                self.assertNotIn("password_hash", manager.encryption_config.config)
                self.assertEqual(self.config_path.read_bytes(), config_before)
                manager.encryption_config.save_config()
                migrated = json.loads(self.config_path.read_text(encoding="utf-8"))
                self.assertNotIn("password_hash", migrated)
                self.assertEqual(migrated["salt"], original_salt)
                self.assertEqual(self.accounts_path.read_bytes(), accounts_before)
                self.assertEqual(am.RobloxAccountManager(password).accounts, self.payload["accounts"])

    def test_wrong_password_still_fails_without_rewriting_either_file(self):
        self.write_existing_accounts("correct-password")
        before = (self.accounts_path.read_bytes(), self.config_path.read_bytes())
        with self.assertRaises(am.AccountPasswordError):
            am.RobloxAccountManager("wrong-password")
        self.assertEqual((self.accounts_path.read_bytes(), self.config_path.read_bytes()), before)

    def test_switch_to_password_does_not_create_a_fast_verifier(self):
        manager = am.RobloxAccountManager()
        manager.accounts = self.payload["accounts"]
        manager.secure_settings = self.payload["secure_settings"]
        manager.switch_encryption_method("password", password="new-password")
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertNotIn("password_hash", persisted)
        self.assertEqual(am.RobloxAccountManager("new-password").accounts, self.payload["accounts"])

    def test_switch_rollback_preserves_salt_without_restoring_the_old_hash(self):
        self.write_existing_accounts("correct-password")
        manager = am.RobloxAccountManager("correct-password")
        salt_before = manager.encryption_config.get_salt()
        accounts_before = self.accounts_path.read_bytes()
        with patch.object(manager, "save_accounts", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                manager.switch_encryption_method("none")
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertNotIn("password_hash", persisted)
        self.assertEqual(persisted["salt"], salt_before)
        self.assertEqual(persisted["encryption_method"], "password")
        self.assertEqual(self.accounts_path.read_bytes(), accounts_before)
        self.assertEqual(am.RobloxAccountManager("correct-password").accounts, self.payload["accounts"])
