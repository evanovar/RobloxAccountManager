"""
features/headless_manager.py
Core logic for the Headless Manager: lists running Roblox processes and
lets you hide/show their windows on demand.
"""

from __future__ import annotations

import threading
from typing import Callable

import win32con
import win32gui

import features.presence as presence_mod
from classes.roblox_api import RobloxAPI
from features.window_operations import show_window_async

_ENFORCE_INTERVAL = 1.0
SCAN_INTERVAL_MIN = 3.0
SCAN_INTERVAL_MAX = 60.0
SCAN_INTERVAL_DEFAULT = 10.0
SCAN_INTERVAL_SETTING = "headless_scan_interval_seconds"


def get_scan_interval(settings: dict | None = None) -> float:
    settings = settings if isinstance(settings, dict) else {}
    try:
        value = float(settings.get(SCAN_INTERVAL_SETTING, SCAN_INTERVAL_DEFAULT))
    except (TypeError, ValueError):
        return SCAN_INTERVAL_DEFAULT
    if value != value:
        return SCAN_INTERVAL_DEFAULT
    return max(SCAN_INTERVAL_MIN, min(SCAN_INTERVAL_MAX, value))


def _get_roblox_pids() -> set[int]:
    return set(presence_mod.get_roblox_processes())


def _get_roblox_hwnds_for_pid(pid: int, windows: list[int] | None = None) -> list[int]:
    hwnds = []
    if windows is None:
        windows = presence_mod.get_windows_by_pid({pid}).get(pid, [])
    for hwnd in windows:
        try:
            # Account notes can replace the title. Select the client by PID and
            # top-level window characteristics, not the mutable title text.
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                continue
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if win32gui.GetWindowText(hwnd) and right > left and bottom > top:
                hwnds.append(hwnd)
        except Exception:
            pass
    return hwnds


def hide_roblox_window(pid: int, username: str | None = None) -> bool:
    hwnds = _get_roblox_hwnds_for_pid(pid)
    for hwnd in hwnds:
        try:
            show_window_async(hwnd, win32con.SW_HIDE)
            win32gui.PostMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MINIMIZE, 0)
        except Exception:
            pass
    return bool(hwnds)


def show_roblox_window(pid: int, username: str | None = None) -> bool:
    hwnds = _get_roblox_hwnds_for_pid(pid)
    for hwnd in hwnds:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE, 0)
            show_window_async(hwnd, win32con.SW_SHOW)
        except Exception:
            pass
    return bool(hwnds)


_active_manager: "HeadlessManager | None" = None


def get_active_manager() -> "HeadlessManager | None":
    return _active_manager


class HeadlessManager:
    def __init__(
        self,
        on_update: Callable[[list[dict]], None],
        scan_interval: float = SCAN_INTERVAL_DEFAULT,
    ):
        self._on_update = on_update
        self._scan_interval = max(SCAN_INTERVAL_MIN, scan_interval)
        self._stop_evt = threading.Event()
        self._scan_thread: threading.Thread | None = None
        self._enforce_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._hidden_pids: set[int] = set()
        # Intent survives Anti-AFK's temporary suspension of hide enforcement.
        self._headless_created: dict[int, float] = {}
        self._pid_created: dict[int, float] = {}
        self._uid_cache: dict[int, str] = {}   # pid -> user_id
        self._name_cache: dict[str, str] = {}  # user_id -> username
        self._pid_username: dict[int, str] = {}  # pid -> username, for window title matching
        self._last_results: list[dict] = []

    def start(self) -> None:
        global _active_manager
        if self._scan_thread and self._scan_thread.is_alive():
            return
        self._stop_evt.clear()
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True, name="HeadlessScan")
        self._scan_thread.start()
        self._enforce_thread = threading.Thread(target=self._enforce_loop, daemon=True, name="HeadlessEnforce")
        self._enforce_thread.start()
        _active_manager = self

    def stop(self, restore: bool = True) -> None:
        global _active_manager
        self._stop_evt.set()
        if self._scan_thread:
            self._scan_thread.join(timeout=2.0)
            self._scan_thread = None
        if self._enforce_thread:
            self._enforce_thread.join(timeout=2.0)
            self._enforce_thread = None
        if restore:
            self.restore_all()
        if _active_manager is self:
            _active_manager = None

    def set_scan_interval(self, seconds: float) -> None:
        self._scan_interval = max(SCAN_INTERVAL_MIN, min(SCAN_INTERVAL_MAX, float(seconds)))

    def set_hidden(self, pid: int, hidden: bool) -> None:
        process = presence_mod.get_roblox_processes().get(pid)
        with self._lock:
            if hidden:
                if process is None:
                    return
                self._headless_created[pid] = process[0]
                self._hidden_pids.add(pid)
            else:
                self._headless_created.pop(pid, None)
                self._hidden_pids.discard(pid)
            username = self._pid_username.get(pid)
        if hidden:
            hide_roblox_window(pid, username)
        else:
            show_roblox_window(pid, username)

    def is_hidden(self, pid: int) -> bool:
        with self._lock:
            return pid in self._headless_created

    def get_headless_identities(self) -> set[tuple[int, float]]:
        with self._lock:
            return set(self._headless_created.items())

    def get_hidden_pids(self) -> set[int]:
        with self._lock:
            return set(self._hidden_pids)

    def get_pid_username(self, pid: int) -> str | None:
        with self._lock:
            return self._pid_username.get(pid)

    def pause_hidden(self, pid: int) -> bool:
        with self._lock:
            if pid in self._hidden_pids:
                self._hidden_pids.discard(pid)
                return True
            return False

    def resume_hidden(self, pid: int) -> None:
        process = presence_mod.get_roblox_processes().get(pid)
        with self._lock:
            if process is None or self._headless_created.get(pid) != process[0]:
                return
            self._hidden_pids.add(pid)
            username = self._pid_username.get(pid)
        hide_roblox_window(pid, username)

    def restore_all(self) -> None:
        processes = presence_mod.get_roblox_processes()
        with self._lock:
            pids = [pid for pid, created in self._headless_created.items()
                    if pid in processes and processes[pid][0] == created]
            usernames = dict(self._pid_username)
            self._hidden_pids.clear()
            self._headless_created.clear()
        for pid in pids:
            show_roblox_window(pid, usernames.get(pid))

    def _enforce_loop(self) -> None:
        while not self._stop_evt.is_set():
            processes = presence_mod.get_roblox_processes()
            with self._lock:
                self._headless_created = {
                    pid: created for pid, created in self._headless_created.items()
                    if pid in processes and processes[pid][0] == created
                }
                self._hidden_pids &= set(self._headless_created)
                pids = list(self._hidden_pids)
            windows = presence_mod.get_windows_by_pid(set(pids))
            for pid in pids:
                for hwnd in _get_roblox_hwnds_for_pid(pid, windows.get(pid, [])):
                    try:
                        if win32gui.IsWindowVisible(hwnd):
                            show_window_async(hwnd, win32con.SW_HIDE)
                            win32gui.PostMessage(
                                hwnd,
                                win32con.WM_SYSCOMMAND,
                                win32con.SC_MINIMIZE,
                                0,
                            )
                    except Exception:
                        pass
            if self._stop_evt.wait(_ENFORCE_INTERVAL):
                break

    def _scan_loop(self) -> None:
        while not self._stop_evt.is_set():
            self._do_scan()
            if self._stop_evt.wait(self._scan_interval):
                break

    def _do_scan(self) -> None:
        try:
            processes = presence_mod.get_roblox_processes()
            pids = set(processes)
            with self._lock:
                self._headless_created = {
                    pid: created for pid, created in self._headless_created.items()
                    if pid in processes and processes[pid][0] == created
                }
                self._hidden_pids &= set(self._headless_created)
            self._uid_cache = {p: u for p, u in self._uid_cache.items()
                               if p in pids and self._pid_created.get(p) == processes[p][0]}
            self._pid_created = {pid: data[0] for pid, data in processes.items()}

            used_logs: set[str] = set()
            results: list[dict] = []
            for pid in sorted(pids):
                user_id = self._uid_cache.get(pid)
                if user_id is None:
                    user_id = presence_mod._get_user_id_from_pid(pid, used_logs)
                    if user_id:
                        self._uid_cache[pid] = user_id
                if not user_id:
                    continue

                username = self._name_cache.get(user_id)
                if not username:
                    username = RobloxAPI.get_username_from_user_id(user_id)
                    if username:
                        self._name_cache[user_id] = username
                if not username:
                    continue

                with self._lock:
                    self._pid_username[pid] = username

                results.append({
                    "pid": pid,
                    "user_id": user_id,
                    "username": username,
                    "hidden": self.is_hidden(pid),
                })

            with self._lock:
                self._pid_username = {p: u for p, u in self._pid_username.items() if p in pids}

            if results != self._last_results:
                self._last_results = [dict(row) for row in results]
                self._on_update(results)
        except Exception:
            pass
