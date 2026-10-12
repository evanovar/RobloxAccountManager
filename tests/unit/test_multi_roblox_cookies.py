import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from features import account_actions as actions


class SharedCookieProtectionTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"LOCALAPPDATA": folder}))
        self.path = os.path.join(folder, "Roblox", "LocalStorage", "RobloxCookies.dat")
        self.enterContext(patch.object(actions, "_mr_handle", None))
        self.addCleanup(actions.disable_multi_roblox)

    def test_existing_data_is_preserved_and_other_clients_cannot_read_or_write(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "wb") as handle:
            handle.write(b"existing session")
        lock = actions._lock_roblox_cookies()
        actions._mr_handle = {"file": lock["file"], "cookie_lock": lock}
        for mode, operation in (
            ("rb", "f.read()"), ("r+b", "f.write(b'other account')"),
            ("wb", "f.write(b'other account')"), ("w+b", "f.write(b'other account')"),
        ):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [sys.executable, "-c", f"import sys\nwith open(sys.argv[1], {mode!r}, buffering=0) as f:\n {operation}", self.path],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self.assertNotEqual(result.returncode, 0)
        actions.disable_multi_roblox()
        with open(self.path, "rb") as handle:
            self.assertEqual(handle.read(), b"existing session")

    def test_missing_store_is_created_and_locked_before_first_launch(self):
        lock = actions._lock_roblox_cookies()
        actions._mr_handle = {"file": lock["file"], "cookie_lock": lock}
        self.assertTrue(lock["acquired"])
        self.assertEqual(os.path.getsize(self.path), 0)
        # Even growth beyond the original zero length must be blocked.
        with self.assertRaises(OSError), open(self.path, "r+b", buffering=0) as handle:
            handle.seek(4096)
            handle.write(b"x")

    def test_lock_failure_closes_the_file(self):
        opened = []
        real_fdopen = os.fdopen

        def fdopen(*args, **kwargs):
            handle = real_fdopen(*args, **kwargs)
            opened.append(handle)
            return handle

        with patch.object(actions.os, "fdopen", side_effect=fdopen), \
                patch.object(actions.msvcrt, "locking", side_effect=OSError("busy")):
            with self.assertRaises(OSError):
                actions._lock_roblox_cookies()
        self.assertTrue(opened[0].closed)

    def test_competing_open_failure_does_not_truncate_existing_data(self):
        lock = actions._lock_roblox_cookies()
        actions._mr_handle = {"file": lock["file"], "cookie_lock": lock}
        with self.assertRaises(OSError):
            actions._lock_roblox_cookies()
        self.assertFalse(lock["file"].closed)

    def test_handle_conversion_failure_releases_exclusive_access(self):
        with patch.object(actions.msvcrt, "open_osfhandle", side_effect=OSError("conversion failed")):
            with self.assertRaises(OSError):
                actions._lock_roblox_cookies()
        with open(self.path, "wb") as handle:
            handle.write(b"available again")

    def start_handle64(self):
        self.enterContext(patch.object(actions.ctypes.windll.shell32, "IsUserAnAdmin", return_value=True))
        self.enterContext(patch.object(actions, "find_handle64", return_value="test.exe"))
        self.enterContext(patch.object(actions, "verify_handle64", return_value=True))
        self.enterContext(patch.object(actions.handle64_trust, "release_trusted_copies"))
        self.thread = self.enterContext(patch.object(actions.threading, "Thread"))
        return actions.enable_multi_roblox("handle64")

    def test_handle64_acquires_cookie_protection_before_monitor_starts(self):
        self.assertEqual(self.start_handle64(), (True, ""))
        self.assertTrue(actions._mr_handle["cookie_lock"]["acquired"])
        self.assertFalse(actions._mr_handle["file"].closed)
        self.thread.return_value.start.assert_called_once()

    def test_handle64_does_not_start_when_protection_fails(self):
        with patch.object(actions, "_lock_roblox_cookies", side_effect=OSError("busy")):
            self.assertEqual(self.start_handle64(), (False, "ROBLOX_COOKIES_LOCK_FAILED"))
        self.assertIsNone(actions._mr_handle)
        self.thread.assert_not_called()

    def test_default_mode_uses_the_same_cookie_protection(self):
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 101
        with patch.object(actions, "is_roblox_running", return_value=False), \
                patch.object(actions.ctypes, "WinDLL", return_value=kernel):
            self.assertEqual(actions.enable_multi_roblox(), (True, ""))
            self.assertTrue(actions._mr_handle["cookie_lock"]["acquired"])
            actions.disable_multi_roblox()

    def test_default_mode_releases_mutexes_when_cookie_protection_fails(self):
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 101
        with patch.object(actions, "is_roblox_running", return_value=False), \
                patch.object(actions.ctypes, "WinDLL", return_value=kernel), \
                patch.object(actions, "_lock_roblox_cookies", side_effect=OSError("busy")):
            self.assertEqual(actions.enable_multi_roblox(), (False, "ROBLOX_COOKIES_LOCK_FAILED"))
        self.assertIsNone(actions._mr_handle)
        self.assertEqual(kernel.CloseHandle.call_count, len(actions._MR_SINGLETON_NAMES))


if __name__ == "__main__":
    unittest.main()
