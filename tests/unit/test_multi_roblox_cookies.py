import os
import threading
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from classes.account_manager import RobloxAccountManager
from classes.operation_result import OperationResult
from features import account_actions as actions, launch_monitor


class SharedCookieProtectionTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"LOCALAPPDATA": folder}))
        self.path = os.path.join(folder, "Roblox", "LocalStorage", "RobloxCookies.dat")
        self.app_storage_path = os.path.join(folder, "Roblox", "LocalStorage", "appStorage.json")
        self.enterContext(patch.object(actions, "_mr_handle", None))
        self.addCleanup(actions.disable_multi_roblox)

    def test_existing_data_is_preserved_and_other_clients_cannot_read_or_write(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "wb") as handle:
            handle.write(b"existing session")
        lock = actions._lock_roblox_storage_file("RobloxCookies.dat")
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
        lock = actions._lock_roblox_storage_file("RobloxCookies.dat")
        actions._mr_handle = {"file": lock["file"], "cookie_lock": lock}
        self.assertTrue(lock["acquired"])
        self.assertEqual(os.path.getsize(self.path), 0)
        # Even growth beyond the original zero length must be blocked.
        with self.assertRaises(OSError), open(self.path, "r+b", buffering=0) as handle:
            handle.seek(4096)
            handle.write(b"x")

    def test_app_storage_is_preserved_and_read_write_truncate_and_replace_are_blocked(self):
        os.makedirs(os.path.dirname(self.app_storage_path))
        original = b'{"Username":"Account B","UserId":"42","preference":"example"}'
        with open(self.app_storage_path, "wb") as handle:
            handle.write(original)
        replacement = self.app_storage_path + ".replacement"
        with open(replacement, "wb") as handle:
            handle.write(b"replacement")
        lock = actions._lock_roblox_storage_file("appStorage.json")
        actions._mr_handle = {"app_storage_lock": lock}
        for mode, operation in (
            ("rb", "f.read()"), ("r+b", "f.write(b'other account')"),
            ("wb", "f.write(b'other account')"), ("w+b", "f.write(b'other account')"),
        ):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [sys.executable, "-c", f"import sys\nwith open(sys.argv[1], {mode!r}, buffering=0) as f:\n {operation}", self.app_storage_path],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self.assertNotEqual(result.returncode, 0)
        result = subprocess.run(
            [sys.executable, "-c", "import os, sys\nos.replace(sys.argv[1], sys.argv[2])", replacement, self.app_storage_path],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertNotEqual(result.returncode, 0)
        actions.disable_multi_roblox()
        with open(self.app_storage_path, "rb") as handle:
            self.assertEqual(handle.read(), original)
        os.replace(replacement, self.app_storage_path)
        with open(self.app_storage_path, "rb") as handle:
            self.assertEqual(handle.read(), b"replacement")

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
                actions._lock_roblox_storage_file("RobloxCookies.dat")
        self.assertTrue(opened[0].closed)

    def test_competing_open_failure_does_not_truncate_existing_data(self):
        lock = actions._lock_roblox_storage_file("RobloxCookies.dat")
        actions._mr_handle = {"file": lock["file"], "cookie_lock": lock}
        with self.assertRaises(OSError):
            actions._lock_roblox_storage_file("RobloxCookies.dat")
        self.assertFalse(lock["file"].closed)

    def test_handle_conversion_failure_releases_exclusive_access(self):
        with patch.object(actions.msvcrt, "open_osfhandle", side_effect=OSError("conversion failed")):
            with self.assertRaises(OSError):
                actions._lock_roblox_storage_file("RobloxCookies.dat")
        with open(self.path, "wb") as handle:
            handle.write(b"available again")

    def start_handle64(self, *, running=False):
        self.enterContext(patch.object(actions.ctypes.windll.shell32, "IsUserAnAdmin", return_value=True))
        self.enterContext(patch.object(actions, "find_handle64", return_value="test.exe"))
        self.enterContext(patch.object(actions, "verify_handle64", return_value=True))
        self.release_trusted = self.enterContext(patch.object(actions.handle64_trust, "release_trusted_copies"))
        self.enterContext(patch.object(actions, "is_roblox_running", return_value=running))
        self.thread = self.enterContext(patch.object(actions.threading, "Thread"))
        return actions.enable_multi_roblox("handle64")

    def test_handle64_protects_both_stores_before_monitor_starts_and_releases_them(self):
        self.assertEqual(self.start_handle64(), (True, ""))
        self.assertTrue(actions._mr_handle["cookie_lock"]["acquired"])
        self.assertFalse(actions._mr_handle["file"].closed)
        app_storage_lock = actions._mr_handle["app_storage_lock"]
        self.assertTrue(app_storage_lock["acquired"])
        with self.assertRaises(OSError), open(self.app_storage_path, "rb"):
            pass
        self.thread.return_value.start.assert_called_once()
        actions.disable_multi_roblox()
        self.assertTrue(app_storage_lock["file"].closed)
        for path in (self.path, self.app_storage_path):
            with open(path, "wb") as handle:
                handle.write(b"available again")

    def test_handle64_does_not_start_when_protection_fails(self):
        with patch.object(actions, "_lock_roblox_storage_file", side_effect=OSError("busy")):
            self.assertEqual(self.start_handle64(), (False, "ROBLOX_COOKIES_LOCK_FAILED"))
        self.assertIsNone(actions._mr_handle)
        self.thread.assert_not_called()

    def test_handle64_rejects_running_clients_before_protection_or_monitoring(self):
        with patch.object(actions, "_lock_roblox_storage_file") as protect:
            self.assertEqual(self.start_handle64(running=True), (False, "ROBLOX_RUNNING"))
        protect.assert_not_called()
        self.assertIsNone(actions._mr_handle)
        self.thread.assert_not_called()
        self.release_trusted.assert_called()

    def test_handle64_releases_first_guard_when_app_storage_cannot_be_protected(self):
        busy = actions._lock_roblox_storage_file("appStorage.json")
        self.addCleanup(busy["file"].close)
        self.assertEqual(self.start_handle64(), (False, "ROBLOX_COOKIES_LOCK_FAILED"))
        self.assertIsNone(actions._mr_handle)
        self.thread.assert_not_called()
        self.release_trusted.assert_called()
        with open(self.path, "wb") as handle:
            handle.write(b"first guard released")
        self.assertFalse(busy["file"].closed)

    def test_default_mode_protects_both_stores_and_releases_them(self):
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 101
        with patch.object(actions, "is_roblox_running", return_value=False), \
                patch.object(actions.ctypes, "WinDLL", return_value=kernel):
            self.assertEqual(actions.enable_multi_roblox(), (True, ""))
            self.assertTrue(actions._mr_handle["cookie_lock"]["acquired"])
            app_storage_lock = actions._mr_handle["app_storage_lock"]
            self.assertTrue(app_storage_lock["acquired"])
            with self.assertRaises(OSError), open(self.app_storage_path, "rb"):
                pass
            actions.disable_multi_roblox()
        self.assertTrue(app_storage_lock["file"].closed)
        for path in (self.path, self.app_storage_path):
            with open(path, "wb") as handle:
                handle.write(b"available again")

    def test_default_mode_is_not_published_before_both_guards_are_acquired(self):
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 101
        protect = actions._lock_roblox_storage_file

        def acquire(filename):
            self.assertIsNone(actions._mr_handle)
            self.assertFalse(actions.is_multi_roblox_running())
            return protect(filename)

        with patch.object(actions, "is_roblox_running", return_value=False), \
                patch.object(actions.ctypes, "WinDLL", return_value=kernel), \
                patch.object(actions, "_lock_roblox_storage_file", side_effect=acquire):
            self.assertEqual(actions.enable_multi_roblox(), (True, ""))
            self.assertTrue(actions.is_multi_roblox_running())
            actions.disable_multi_roblox()

    def test_startup_does_not_interrupt_an_in_progress_launch(self):
        with launch_monitor.LAUNCH_LOCK:
            with patch.object(actions, "disable_multi_roblox") as disable:
                self.assertEqual(actions.enable_multi_roblox(), (False, "ROBLOX_LAUNCH_IN_PROGRESS"))
        disable.assert_not_called()

    def test_concurrent_ticket_dispatch_waits_until_both_guards_are_ready(self):
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 101
        manager = RobloxAccountManager.__new__(RobloxAccountManager)
        entered = threading.Event()
        completed = threading.Event()
        observations = []

        def dispatch(*_args):
            state = actions._mr_handle
            observations.append(bool(state and state.get("cookie_lock") and state.get("app_storage_lock")))
            return OperationResult.success()

        manager._launch_roblox = MagicMock(side_effect=dispatch)

        def launch():
            entered.set()
            try:
                manager.launch_roblox("synthetic-account", "123")
            finally:
                completed.set()

        thread = threading.Thread(target=launch, daemon=True)
        protect = actions._lock_roblox_storage_file

        def acquire(filename):
            if filename == "RobloxCookies.dat":
                thread.start()
                self.assertTrue(entered.wait(2))
                self.assertFalse(completed.wait(0.1), "ticket dispatched before native protection")
            return protect(filename)

        with patch.object(actions, "is_roblox_running", return_value=False), \
                patch.object(actions.ctypes, "WinDLL", return_value=kernel), \
                patch.object(actions, "_lock_roblox_storage_file", side_effect=acquire), \
                patch.object(launch_monitor, "wait_for_launch_slot", return_value=OperationResult.success()), \
                patch.object(launch_monitor, "_snapshot", return_value={}), \
                patch.object(launch_monitor, "confirm_launch", return_value=OperationResult.success()):
            try:
                self.assertEqual(actions.enable_multi_roblox(), (True, ""))
            finally:
                if thread.ident is not None:
                    thread.join(2)
                actions.disable_multi_roblox()
        self.assertFalse(thread.is_alive())
        self.assertEqual(observations, [True])

    def test_default_mode_releases_mutexes_when_cookie_protection_fails(self):
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 101
        with patch.object(actions, "is_roblox_running", return_value=False), \
                patch.object(actions.ctypes, "WinDLL", return_value=kernel), \
                patch.object(actions, "_lock_roblox_storage_file", side_effect=OSError("busy")):
            self.assertEqual(actions.enable_multi_roblox(), (False, "ROBLOX_COOKIES_LOCK_FAILED"))
        self.assertIsNone(actions._mr_handle)
        self.assertEqual(kernel.CloseHandle.call_count, len(actions._MR_SINGLETON_NAMES))

    def test_default_mode_releases_first_guard_and_mutexes_when_app_storage_is_busy(self):
        busy = actions._lock_roblox_storage_file("appStorage.json")
        self.addCleanup(busy["file"].close)
        kernel = MagicMock()
        kernel.CreateMutexW.return_value = 101
        with patch.object(actions, "is_roblox_running", return_value=False), \
                patch.object(actions.ctypes, "WinDLL", return_value=kernel):
            self.assertEqual(actions.enable_multi_roblox(), (False, "ROBLOX_COOKIES_LOCK_FAILED"))
        self.assertIsNone(actions._mr_handle)
        self.assertEqual(kernel.CloseHandle.call_count, len(actions._MR_SINGLETON_NAMES))
        with open(self.path, "wb") as handle:
            handle.write(b"first guard released")
        self.assertFalse(busy["file"].closed)


if __name__ == "__main__":
    unittest.main()
