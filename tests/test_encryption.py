import base64
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

from classes.encryption import (
    EncryptedDataError,
    EncryptionConfig,
    HardwareDecryptionError,
    HardwareEncryption,
    PasswordDecryptionError,
    PasswordEncryption,
)

SAMPLE = {"accounts": {"alice": {"cookie": "abc", "note": "main"}}}


def make_hardware(machine_id="machine-a"):
    with mock.patch.object(HardwareEncryption, "_get_machine_id", return_value=machine_id):
        return HardwareEncryption()


class PasswordEncryptionTests(unittest.TestCase):
    def test_round_trip(self):
        enc = PasswordEncryption("hunter2")
        package = enc.encrypt_data(SAMPLE)
        again = PasswordEncryption("hunter2", enc.get_salt_b64())
        self.assertEqual(again.decrypt_data(package), SAMPLE)

    def test_unicode_password_round_trip(self):
        enc = PasswordEncryption("pässwörd-☃")
        package = enc.encrypt_data(SAMPLE)
        again = PasswordEncryption("pässwörd-☃", enc.salt)
        self.assertEqual(again.decrypt_data(package), SAMPLE)

    def test_wrong_password_is_rejected(self):
        enc = PasswordEncryption("right")
        package = enc.encrypt_data(SAMPLE)
        wrong = PasswordEncryption("wrong", enc.salt)
        with self.assertRaises(PasswordDecryptionError):
            wrong.decrypt_data(package)

    def test_tampered_ciphertext_is_rejected(self):
        enc = PasswordEncryption("pw")
        package = enc.encrypt_data(SAMPLE)
        raw = bytearray(base64.b64decode(package["ciphertext"]))
        raw[0] ^= 1
        package["ciphertext"] = base64.b64encode(bytes(raw)).decode()
        with self.assertRaises(PasswordDecryptionError):
            enc.decrypt_data(package)

    def test_legacy_latin1_package_still_decrypts(self):
        password = "café"
        salt = os.urandom(32)
        key = PBKDF2(password.encode("latin-1"), salt, dkLen=32, count=100000)
        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(json.dumps(SAMPLE).encode())
        legacy = {
            "nonce": base64.b64encode(cipher.nonce).decode(),
            "tag": base64.b64encode(tag).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }
        self.assertEqual(PasswordEncryption(password, salt).decrypt_data(legacy), SAMPLE)

    def test_malformed_payloads(self):
        enc = PasswordEncryption("pw")
        for bad in (None, "text", {}, {"nonce": "x", "tag": "y"},
                    {"nonce": "!!", "tag": "!!", "ciphertext": "!!"}):
            with self.subTest(payload=bad):
                with self.assertRaises(EncryptedDataError):
                    enc.decrypt_data(bad)


class HardwareEncryptionTests(unittest.TestCase):
    def test_round_trip(self):
        enc = make_hardware()
        self.assertEqual(enc.decrypt_data(enc.encrypt_data(SAMPLE)), SAMPLE)

    def test_other_machine_is_rejected(self):
        package = make_hardware("machine-a").encrypt_data(SAMPLE)
        other = make_hardware("machine-b")
        with mock.patch.object(other, "_get_v264_machine_id", return_value="machine-b"), \
                mock.patch.object(other, "_get_legacy_machine_id", return_value="machine-b"):
            with self.assertRaises(HardwareDecryptionError):
                other.decrypt_data(package)

    def test_falls_back_to_legacy_machine_id(self):
        package = make_hardware("legacy-id").encrypt_data(SAMPLE)
        current = make_hardware("new-id")
        with mock.patch.object(current, "_get_v264_machine_id", return_value="new-id"), \
                mock.patch.object(current, "_get_legacy_machine_id", return_value="legacy-id"):
            self.assertEqual(current.decrypt_data(package), SAMPLE)
        self.assertEqual(current.decryption_key_source, "legacy")


class EncryptionConfigTests(unittest.TestCase):
    def test_settings_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "nested", "encryption_config.json")
            config = EncryptionConfig(path)
            self.assertFalse(config.is_setup_complete())
            config.enable_password_encryption("salt", "hash")

            reloaded = EncryptionConfig(path)
            self.assertTrue(reloaded.is_encryption_enabled())
            self.assertEqual(reloaded.get_encryption_method(), "password")
            self.assertEqual(reloaded.get_salt(), "salt")

    def test_corrupt_file_loads_as_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "encryption_config.json")
            with open(path, "w") as handle:
                handle.write("{not json")
            self.assertEqual(EncryptionConfig(path).config, {})


if __name__ == "__main__":
    unittest.main()
