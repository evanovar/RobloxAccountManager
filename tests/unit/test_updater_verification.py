import hashlib
import os
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from features import updater

PAYLOAD = b"MZ" + b"\x00" * 1022


def sha256_digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


class VerifyDownloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def write(self, data):
        path = os.path.join(self.folder.name, "update.exe")
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_matching_size_and_digest_pass(self):
        updater.verify_download(self.write(PAYLOAD), len(PAYLOAD), sha256_digest(PAYLOAD))

    def test_digest_is_case_insensitive(self):
        updater.verify_download(self.write(PAYLOAD), len(PAYLOAD), sha256_digest(PAYLOAD).upper().replace("SHA256", "sha256"))

    def test_wrong_digest_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            updater.verify_download(self.write(PAYLOAD), len(PAYLOAD), sha256_digest(b"other"))

    def test_wrong_size_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "bytes"):
            updater.verify_download(self.write(PAYLOAD), len(PAYLOAD) + 1, None)

    def test_empty_file_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "empty"):
            updater.verify_download(self.write(b""), None, None)

    def test_file_that_is_not_an_executable_is_rejected(self):
        data = b"<html>rate limited</html>"
        with self.assertRaisesRegex(RuntimeError, "executable"):
            updater.verify_download(self.write(data), len(data), sha256_digest(data))

    def test_missing_digest_still_checks_size(self):
        updater.verify_download(self.write(PAYLOAD), len(PAYLOAD), None)
        with self.assertRaises(RuntimeError):
            updater.verify_download(self.write(PAYLOAD), 5, None)


class TrustedUrlTests(unittest.TestCase):
    def test_only_https_github_downloads_are_trusted(self):
        good = "https://github.com/evanovar/RobloxAccountManager/releases/download/v1/x.exe"
        self.assertTrue(updater.is_trusted_download_url(good))
        for bad in (
            "http://github.com/x.exe",
            "https://github.com.evil.example/x.exe",
            "https://example.com/github.com/x.exe",
            "ftp://github.com/x.exe",
            "",
        ):
            with self.subTest(url=bad):
                self.assertFalse(updater.is_trusted_download_url(bad))


class DownloadUpdateTests(unittest.TestCase):
    def run_download(self, asset, body, headers=None):
        response = MagicMock()
        response.headers = headers if headers is not None else {"content-length": str(len(body))}
        response.iter_content.return_value = [body[i:i + 512] for i in range(0, len(body), 512)]
        finished = threading.Event()
        outcome = {}

        def on_done(success, message):
            outcome["result"] = (success, message)
            finished.set()

        with patch.object(updater, "get_update_target", return_value="C:/app/RAM.exe"), \
                patch.object(updater, "get_exe_asset", return_value=asset), \
                patch.object(updater.requests, "get", return_value=response), \
                patch.object(updater, "_launch_installer") as launch:
            updater.download_update(lambda _: None, on_done)
            self.assertTrue(finished.wait(10))
        return outcome["result"], launch

    def asset(self, **overrides):
        base = {
            "url": "https://github.com/evanovar/RobloxAccountManager/releases/download/v1/EvanovarRAM-v1.0.0.exe",
            "name": "EvanovarRAM-v1.0.0.exe",
            "size": len(PAYLOAD),
            "digest": sha256_digest(PAYLOAD),
        }
        base.update(overrides)
        return base

    def test_verified_download_starts_the_installer(self):
        (success, _), launch = self.run_download(self.asset(), PAYLOAD)
        self.assertTrue(success)
        launch.assert_called_once()

    def test_tampered_download_never_reaches_the_installer(self):
        tampered = PAYLOAD[:-1] + b"\x01"
        (success, message), launch = self.run_download(self.asset(), tampered)
        self.assertFalse(success)
        self.assertIn("checksum", message)
        launch.assert_not_called()

    def test_truncated_download_never_reaches_the_installer(self):
        (success, message), launch = self.run_download(
            self.asset(), PAYLOAD[:512], headers={"content-length": str(len(PAYLOAD))}
        )
        self.assertFalse(success)
        self.assertIn("interrupted", message)
        launch.assert_not_called()

    def test_untrusted_address_is_refused_before_downloading(self):
        (success, message), launch = self.run_download(self.asset(url="https://example.com/x.exe"), PAYLOAD)
        self.assertFalse(success)
        self.assertIn("github.com", message)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
