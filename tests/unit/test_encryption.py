import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import classes.account_manager as account_manager_mod
import classes.encryption as encryption_mod
from classes.account_manager import AccountPasswordError, RobloxAccountManager
from classes.encryption import (
    EncryptedDataError, HardwareEncryption, PasswordDecryptionError, PasswordEncryption,
)

def _hardware_encryptor(machine_id):
    encryptor = HardwareEncryption.__new__(HardwareEncryption)
    encryptor.machine_id = machine_id
    encryptor.key = encryptor._derive_key_from_machine_id(machine_id)
    encryptor.decryption_key_source = "stable"
    return encryptor


def _hardware_reader(stable_id, v264_id, legacy_id):
    encryptor = _hardware_encryptor(stable_id)
    encryptor._get_v264_machine_id = lambda: v264_id
    encryptor._get_legacy_machine_id = lambda: legacy_id
    return encryptor


class HardwareEncryptionCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(encryption_mod._MACHINE_ID_CACHE, {}, clear=True))
        self.stable_id = hashlib.sha256(b"stable").hexdigest()
        self.v264_id = hashlib.sha256(b"v264").hexdigest()
        self.legacy_id = hashlib.sha256(b"legacy").hexdigest()
        self.payload = {"accounts": {"test": {"cookie": "secret"}}}

    def test_reads_stable_hardware_payload(self):
        package = _hardware_encryptor(self.stable_id).encrypt_data(self.payload)
        reader = _hardware_reader(self.stable_id, self.v264_id, self.legacy_id)
        self.assertEqual(reader.decrypt_data(package), self.payload)
        self.assertEqual(reader.decryption_key_source, "stable")

    def test_reads_v264_hardware_payload(self):
        package = _hardware_encryptor(self.v264_id).encrypt_data(self.payload)
        reader = _hardware_reader(self.stable_id, self.v264_id, self.legacy_id)
        self.assertEqual(reader.decrypt_data(package), self.payload)
        self.assertEqual(reader.decryption_key_source, "v264")

    def test_reads_legacy_hardware_payload(self):
        package = _hardware_encryptor(self.legacy_id).encrypt_data(self.payload)
        reader = _hardware_reader(self.stable_id, self.v264_id, self.legacy_id)
        self.assertEqual(reader.decrypt_data(package), self.payload)
        self.assertEqual(reader.decryption_key_source, "legacy")

    def test_stable_multi_processor_format_is_unchanged(self):
        outputs = {
            "(Get-CimInstance Win32_ComputerSystemProduct).UUID": b"UUID\r\n",
            "(Get-CimInstance Win32_Processor).ProcessorId": b"CPU1\r\nCPU2\r\n",
            "(Get-CimInstance Win32_BaseBoard).SerialNumber": b"BOARD\r\n",
        }
        with patch("classes.encryption.platform.system", return_value="Windows"), patch(
            "classes.encryption._read_wmi_identifiers", return_value=None,
        ):
            with patch(
                "classes.encryption.subprocess.check_output",
                side_effect=lambda args, **kwargs: outputs[args[-1]],
            ):
                machine_id = HardwareEncryption.__new__(
                    HardwareEncryption
                )._get_machine_id()
        expected = hashlib.sha256(
            "UUID-CPU1\r\nCPU2-BOARD".encode()
        ).hexdigest()
        self.assertEqual(machine_id, expected)


class PasswordEncryptionFailureTests(unittest.TestCase):
    def test_unicode_password_round_trip_after_restart(self):
        for password in ('password-\u013e', 'password-\u4e2d\u6587', 'password-\u00e9'):
            with self.subTest(password=password):
                writer = PasswordEncryption(password)
                package = writer.encrypt_data({'accounts': {'demo': {'cookie': 'test'}}})
                self.assertEqual(package['password_encoding'], 'utf-8')
                reader = PasswordEncryption(password, writer.get_salt_b64())
                self.assertEqual(reader.decrypt_data(package)['accounts']['demo']['cookie'], 'test')

    def test_legacy_latin1_password_remains_readable(self):
        password = 'legacy-\u00e9-password'
        writer = PasswordEncryption(password)
        writer.key = encryption_mod.PBKDF2(password, writer.salt, dkLen=32, count=100000)
        package = writer.encrypt_data({'accounts': {}})
        package.pop('password_encoding')
        reader = PasswordEncryption(password, writer.get_salt_b64())
        self.assertEqual(reader.decrypt_data(package), {'accounts': {}})
        rewritten = reader.encrypt_data({'accounts': {}})
        self.assertEqual(rewritten['password_encoding'], 'utf-8')
        self.assertEqual(PasswordEncryption(password, reader.salt).decrypt_data(rewritten), {'accounts': {}})

    def test_utf8_password_does_not_use_legacy_ambiguous_bytes(self):
        writer = PasswordEncryption('password-\u013e')
        package = writer.encrypt_data({'accounts': {}})
        different_password = 'password-\u013e'.encode('utf-8').decode('latin-1')
        reader = PasswordEncryption(different_password, writer.salt)
        with self.assertRaises(PasswordDecryptionError):
            reader.decrypt_data(package)

    def test_wrong_password_has_specific_error(self):
        writer = PasswordEncryption("correct password")
        package = writer.encrypt_data({"accounts": {}})
        reader = PasswordEncryption("wrong password", writer.get_salt_b64())
        with self.assertRaises(PasswordDecryptionError):
            reader.decrypt_data(package)

    def test_malformed_payload_has_specific_error(self):
        reader = PasswordEncryption("password")
        with self.assertRaises(EncryptedDataError):
            reader.decrypt_data({"nonce": "invalid"})

    def test_failed_account_unlock_preserves_file(self):
        with tempfile.TemporaryDirectory() as work_dir:
            writer = PasswordEncryption("correct password")
            encrypted = {
                "encrypted": True,
                "data": writer.encrypt_data({"accounts": {}}),
            }
            config = {
                "encryption_enabled": True,
                "encryption_method": "password",
                "setup_completed": True,
                "salt": writer.get_salt_b64(),
            }
            accounts_path = os.path.join(work_dir, "saved_accounts.json")
            config_path = os.path.join(work_dir, "encryption_config.json")
            with open(accounts_path, "w", encoding="utf-8") as handle:
                json.dump(encrypted, handle)
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(config, handle)
            with open(accounts_path, "rb") as handle:
                before = handle.read()

            with patch.object(account_manager_mod, "get_data_dir", return_value=work_dir):
                with self.assertRaises(AccountPasswordError):
                    RobloxAccountManager(password="wrong password")

            with open(accounts_path, "rb") as handle:
                self.assertEqual(handle.read(), before)
