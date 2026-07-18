"""
features/headless_manager.py
Core logic for the Headless Manager: lists running Roblox processes and
lets you hide/show their windows on demand.
"""

from __future__ import annotations

import threading
from typing import Callable

import psutil
import win32con
import win32gui
import win32process

import features.presence as presence_mod
from classes.roblox_api import RobloxAPI

_ENFORCE_INTERVAL = 0.05

def _get_roblox_pids() -> set[int]:
    try:
        pids = set()
        for p in psutil.process_iter(["pid", "name"]):
            if (p.info.get("name") or "").lower() == "robloxplayerbeta.exe":
                pids.add(p.info["pid"])
        return pids
    except Exception:
        return set()


def _get_roblox_hwnds_for_pid(pid: int, expected_titles: set[str] | None = None) -> list[int]:
    hwnds: list[int] = []
    titles = expected_titles or {"Roblox"}

    def _callback(hwnd, _):
        try:
            if win32gui.GetWindowText(hwnd) in titles:
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    hwnds.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_callback, None)
    except Exception:
        pass
    return hwnds


def hide_roblox_window(pid: int, username: str | None = None) -> bool:
    titles = {"Roblox"}
    if username:
        titles.add(username)
    hwnds = _get_roblox_hwnds_for_pid(pid, titles)
    for hwnd in hwnds:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            win32gui.PostMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MINIMIZE, 0)
        except Exception:
            pass
    return bool(hwnds)


def show_roblox_window(pid: int, username: str | None = None) -> bool:
    titles = {"Roblox"}
    if username:
        titles.add(username)
    hwnds = _get_roblox_hwnds_for_pid(pid, titles)
    for hwnd in hwnds:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE, 0)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        except Exception:
            pass
    return bool(hwnds)


_active_manager: "HeadlessManager | None" = None


def get_active_manager() -> "HeadlessManager | None":
    return _active_manager


class HeadlessManager:
    def __init__(self, on_update: Callable[[list[dict]], None], scan_interval: float = 10.0):
        self._on_update = on_update
        self._scan_interval = max(3.0, scan_interval)
        self._stop_evt = threading.Event()
        self._scan_thread: threading.Thread | None = None
        self._enforce_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._hidden_pids: set[int] = set()
        self._uid_cache: dict[int, str] = {}   # pid -> user_id
        self._name_cache: dict[str, str] = {}  # user_id -> username
        self._pid_username: dict[int, str] = {}  # pid -> username, for window title matching

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

    def set_hidden(self, pid: int, hidden: bool) -> None:
        with self._lock:
            if hidden:
                self._hidden_pids.add(pid)
            else:
                self._hidden_pids.discard(pid)
            username = self._pid_username.get(pid)
        if hidden:
            hide_roblox_window(pid, username)
        else:
            show_roblox_window(pid, username)

    def is_hidden(self, pid: int) -> bool:
        with self._lock:
            return pid in self._hidden_pids

    def get_hidden_pids(self) -> set[int]:
        with self._lock:
            return set(self._hidden_pids)

    def pause_hidden(self, pid: int) -> bool:
        with self._lock:
            if pid in self._hidden_pids:
                self._hidden_pids.discard(pid)
                return True
            return False

    def resume_hidden(self, pid: int) -> None:
        with self._lock:
            self._hidden_pids.add(pid)
            username = self._pid_username.get(pid)
        hide_roblox_window(pid, username)

    def restore_all(self) -> None:
        with self._lock:
            pids = list(self._hidden_pids)
            usernames = dict(self._pid_username)
            self._hidden_pids.clear()
        for pid in pids:
            show_roblox_window(pid, usernames.get(pid))

    def _enforce_loop(self) -> None:
        while not self._stop_evt.is_set():
            with self._lock:
                pids = list(self._hidden_pids)
                usernames = dict(self._pid_username)
            for pid in pids:
                hide_roblox_window(pid, usernames.get(pid))
            if self._stop_evt.wait(_ENFORCE_INTERVAL):
                break

    def _scan_loop(self) -> None:
        while not self._stop_evt.is_set():
            self._do_scan()
            if self._stop_evt.wait(self._scan_interval):
                break

    def _do_scan(self) -> None:
        try:
            pids = _get_roblox_pids()
            with self._lock:
                self._hidden_pids &= pids
            self._uid_cache = {p: u for p, u in self._uid_cache.items() if p in pids}

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

            self._on_update(results)
        except Exception:
            pass
