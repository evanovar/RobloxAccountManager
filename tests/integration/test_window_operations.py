import ctypes
from ctypes import wintypes
import subprocess
import sys
import time
import unittest

if sys.platform == 'win32':
    from features import window_operations


@unittest.skipUnless(sys.platform == 'win32', 'Requires the Windows desktop')
class WindowOperationTests(unittest.TestCase):
    def test_unresponsive_external_window_does_not_block_scans(self):
        script = (
            'import ctypes, time; from ctypes import wintypes; '
            'u = ctypes.WinDLL("user32"); '
            'u.CreateWindowExW.restype = wintypes.HWND; '
            'h = u.CreateWindowExW(0, "STATIC", "Test", 0x80000000, '
            '0, 0, 10, 10, None, None, None, None); '
            'print(h, flush=True); time.sleep(20)'
        )
        child = subprocess.Popen(
            [sys.executable, '-c', script], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            hwnd = int(child.stdout.readline().strip())
            self.assertTrue(hwnd)
            started = time.monotonic()
            for _ in range(6):
                self.assertFalse(window_operations.set_window_title(hwnd, 'Changed'))
            self.assertLess(time.monotonic() - started, 4)
            started = time.monotonic()
            window_operations.show_window_async(hwnd, 0)
            self.assertLess(time.monotonic() - started, 1)
        finally:
            child.kill()
            child.communicate(timeout=5)

    def test_responsive_window_title_changes(self):
        user32 = ctypes.WinDLL('user32')
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        hwnd = user32.CreateWindowExW(
            0, 'STATIC', 'Original', 0x80000000, 0, 0, 10, 10,
            None, None, None, None,
        )
        try:
            self.assertTrue(hwnd)
            self.assertTrue(window_operations.set_window_title(hwnd, 'Account Name'))
            text = ctypes.create_unicode_buffer(100)
            user32.GetWindowTextW(hwnd, text, 100)
            self.assertEqual(text.value, 'Account Name')
        finally:
            user32.DestroyWindow(hwnd)

