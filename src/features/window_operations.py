"""Nonblocking and bounded operations on external client windows."""

import ctypes
from ctypes import wintypes


_USER32 = ctypes.WinDLL('user32', use_last_error=True)
_USER32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
_USER32.ShowWindowAsync.restype = wintypes.BOOL
_USER32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]
_USER32.SendMessageTimeoutW.restype = ctypes.c_ssize_t


def show_window_async(hwnd: int, command: int) -> bool:
    return bool(_USER32.ShowWindowAsync(hwnd, command))


def set_window_title(hwnd: int, title: str) -> bool:
    # ctypes releases the GIL while Windows waits for the other process.
    text = ctypes.create_unicode_buffer(title)
    result = ctypes.c_size_t()
    delivered = _USER32.SendMessageTimeoutW(
        hwnd, 0x000C, 0, ctypes.addressof(text),
        0x0001 | 0x0002 | 0x0020, 250, ctypes.byref(result),
    )
    return bool(delivered and result.value)
