"""Roblox window title management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import re
import threading
import time

import psutil
import win32con
import win32gui
import win32process

from classes.roblox_api import RobloxAPI
import features.presence as presence_mod


_LOG_EARLY_TOLERANCE_SEC = 2.0
_LOG_STARTUP_WINDOW_SEC = 60.0
_TRACKER_PATTERN = re.compile(
    r"browsertrackerid[^0-9]{0,32}(\d+)",
    re.IGNORECASE,
)
_EVIDENCE_TIMESTAMP = 1
_EVIDENCE_OPEN_FILE = 2
_EVIDENCE_TRACKER = 3
_EVIDENCE_NAMES = {
    _EVIDENCE_TIMESTAMP: "single timestamp match",
    _EVIDENCE_OPEN_FILE: "exact open log file",
    _EVIDENCE_TRACKER: "browser tracker ID",
}


@dataclass(frozen=True)
class _ProcessIdentity:
    user_id: str
    username: str
    log_path: str
    browser_tracker_id: str
    evidence: int


class RobloxWindowRenamer:
    def __init__(
        self,
        manager,
        interval_sec: float = 5.0,
        title_mode: str = "username",
    ):
        self._manager = manager
        self._interval = max(5.0, float(interval_sec))
        self._mode_lock = threading.Lock()
        self._title_mode = self._normalize_title_mode(title_mode)
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._identities: dict[tuple[int, float], _ProcessIdentity] = {}
        self._claimed_logs: dict[str, tuple[int, float]] = {}
        self._username_cache: dict[str, str] = {}
        self._username_retry_at: dict[str, float] = {}
        self._waiting_for_window: set[tuple[int, float]] = set()
        self._ambiguities: dict[tuple[int, float], str] = {}
        self._main_windows: dict[tuple[int, float], int] = {}
        self._managed_titles: set[str] = set()

    @staticmethod
    def _normalize_title_mode(mode: str) -> str:
        return mode if mode in ("username", "note") else "username"

    def set_title_mode(self, mode: str) -> None:
        normalized = self._normalize_title_mode(mode)
        with self._mode_lock:
            self._title_mode = normalized

    def _get_title_mode(self) -> str:
        with self._mode_lock:
            return self._title_mode

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="RobloxWindowRenamer",
        )
        self._thread.start()

    def stop(self, join_timeout: float = 2.0) -> None:
        self._stop_evt.set()
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=max(0.0, join_timeout))
        self._identities.clear()
        self._claimed_logs.clear()
        self._username_cache.clear()
        self._username_retry_at.clear()
        self._waiting_for_window.clear()
        self._ambiguities.clear()
        self._main_windows.clear()
        self._managed_titles.clear()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        print("[INFO] Rename Roblox Windows started")
        while not self._stop_evt.is_set():
            self._do_scan()
            if self._stop_evt.wait(self._interval):
                break
        print("[INFO] Rename Roblox Windows stopped")

    def _get_saved_accounts(self) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        accounts_lock = getattr(self._manager, "_accounts_lock", None)
        if accounts_lock is not None:
            with accounts_lock:
                accounts = list(self._manager.accounts.items())
        else:
            accounts = list(self._manager.accounts.items())

        for username, data in accounts:
            if not isinstance(data, dict):
                continue
            user_id = str(data.get("user_id", "") or "")
            if user_id and user_id != "0":
                result[user_id] = {
                    "username": str(username),
                    "note": str(data.get("note", "") or "").strip(),
                }
        return result

    @staticmethod
    def _get_saved_usernames(
        saved_accounts: dict[str, dict[str, str]],
    ) -> dict[str, str]:
        return {
            user_id: account["username"]
            for user_id, account in saved_accounts.items()
            if account.get("username")
        }

    def _get_title_target(
        self,
        identity: _ProcessIdentity,
        saved_accounts: dict[str, dict[str, str]],
    ) -> str:
        if self._get_title_mode() == "note":
            account = saved_accounts.get(identity.user_id)
            if not account:
                return ""
            return str(account.get("note", "") or "").strip()
        return identity.username

    def _get_username(self, user_id: str, saved_usernames: dict[str, str]) -> str:
        username = saved_usernames.get(user_id)
        if username:
            self._username_cache[user_id] = username
            self._username_retry_at.pop(user_id, None)
            return username

        cached = self._username_cache.get(user_id)
        if cached:
            return cached

        now = time.monotonic()
        if now < self._username_retry_at.get(user_id, 0.0):
            return ""
        try:
            username = RobloxAPI.get_username_from_user_id(user_id) or ""
        except Exception:
            username = ""
        if username:
            self._username_cache[user_id] = username
            self._username_retry_at.pop(user_id, None)
        else:
            self._username_retry_at[user_id] = now + 30.0
        return username

    @staticmethod
    def _create_time_utc(create_time: float) -> datetime:
        return datetime.fromtimestamp(
            create_time,
            tz=timezone.utc,
        ).replace(tzinfo=None)

    @staticmethod
    def _normalized_path(path: str) -> str:
        return os.path.normcase(os.path.abspath(str(path or "")))

    @staticmethod
    def _extract_process_tracker(process: psutil.Process) -> str:
        try:
            command_line = " ".join(str(value) for value in process.cmdline())
            matches = set(_TRACKER_PATTERN.findall(command_line))
            if len(matches) == 1:
                return next(iter(matches))
        except (
            OSError,
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
        ):
            pass
        return ""

    @classmethod
    def _get_open_log_paths(cls, process: psutil.Process) -> set[str]:
        paths: set[str] = set()
        try:
            for opened_file in process.open_files():
                path = str(getattr(opened_file, "path", "") or "")
                if path.lower().endswith("_last.log"):
                    paths.add(cls._normalized_path(path))
        except (
            OSError,
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
        ):
            pass
        return paths

    @staticmethod
    def _process_is_current(key: tuple[int, float]) -> bool:
        pid, expected_create_time = key
        current = presence_mod.get_roblox_processes()
        process_data = current.get(pid)
        return bool(
            process_data
            and abs(process_data[0] - expected_create_time) < 0.01
        )

    def _remove_exited_state(self, live_keys: set[tuple[int, float]]) -> None:
        self._identities = {
            key: value
            for key, value in self._identities.items()
            if key in live_keys
        }
        self._claimed_logs = {
            path: key
            for path, key in self._claimed_logs.items()
            if key in live_keys
        }
        self._waiting_for_window &= live_keys
        self._ambiguities = {
            key: value
            for key, value in self._ambiguities.items()
            if key in live_keys
        }
        self._main_windows = {
            key: hwnd
            for key, hwnd in self._main_windows.items()
            if key in live_keys
        }

    def _set_ambiguity(self, key: tuple[int, float], reason: str) -> None:
        if self._ambiguities.get(key) == reason:
            return
        self._ambiguities[key] = reason
        print(
            f"[WARNING] Roblox PID {key[0]} identity is ambiguous, "
            f"waiting for direct evidence: {reason}"
        )

    def _clear_ambiguity(self, key: tuple[int, float]) -> None:
        self._ambiguities.pop(key, None)

    def _set_identity(
        self,
        key: tuple[int, float],
        entry: presence_mod.RobloxLogEntry,
        evidence: int,
        saved_usernames: dict[str, str],
        process_tracker: str = "",
    ) -> bool:
        owner = self._claimed_logs.get(entry.path)
        if owner is not None and owner != key:
            owner_identity = self._identities.get(owner)
            if owner_identity is not None and evidence > owner_identity.evidence:
                self._identities.pop(owner, None)
                self._claimed_logs.pop(entry.path, None)
                self._set_ambiguity(owner, "its previous log belongs to another PID")
            else:
                self._set_ambiguity(key, "the matching log is already claimed")
                return False

        old_identity = self._identities.get(key)
        if old_identity is not None:
            if evidence < old_identity.evidence:
                return False
            if (
                evidence == old_identity.evidence
                and old_identity.user_id != entry.user_id
            ):
                self._set_ambiguity(
                    key,
                    "equal-confidence evidence identifies different accounts",
                )
                return False

        username = self._get_username(entry.user_id, saved_usernames)
        new_identity = _ProcessIdentity(
            user_id=entry.user_id,
            username=username,
            log_path=entry.path,
            browser_tracker_id=(
                process_tracker
                or entry.browser_tracker_id
            ),
            evidence=evidence,
        )

        if old_identity is not None and old_identity.log_path != entry.path:
            self._claimed_logs.pop(old_identity.log_path, None)
        self._identities[key] = new_identity
        self._claimed_logs[entry.path] = key
        self._clear_ambiguity(key)
        if username:
            self._managed_titles.add(username)

        evidence_name = _EVIDENCE_NAMES[evidence]
        if (
            old_identity is not None
            and old_identity.username
            and username
            and old_identity.username != username
        ):
            print(
                f"[WARNING] Corrected Roblox PID {key[0]} mapping: "
                f"'{old_identity.username}' -> '{username}' using {evidence_name}"
            )
        elif old_identity is None and username:
            print(
                f"[INFO] Mapped Roblox PID {key[0]} -> "
                f"'{username}' using {evidence_name}"
            )
        return True

    def _collect_direct_evidence(
        self,
        live_processes: dict[tuple[int, float], psutil.Process],
        entries: list[presence_mod.RobloxLogEntry],
        saved_usernames: dict[str, str],
    ) -> tuple[dict[tuple[int, float], str], dict[tuple[int, float], set[str]]]:
        process_trackers: dict[tuple[int, float], str] = {}
        process_log_paths: dict[tuple[int, float], set[str]] = {}
        tracker_processes: dict[str, list[tuple[int, float]]] = {}
        tracker_entries: dict[str, list[presence_mod.RobloxLogEntry]] = {}
        path_entries = {
            self._normalized_path(entry.path): entry
            for entry in entries
        }

        for entry in entries:
            if entry.browser_tracker_id:
                tracker_entries.setdefault(
                    entry.browser_tracker_id,
                    [],
                ).append(entry)

        for key, process in live_processes.items():
            identity = self._identities.get(key)
            if identity and identity.evidence >= _EVIDENCE_OPEN_FILE:
                continue
            tracker = self._extract_process_tracker(process)
            process_trackers[key] = tracker
            if tracker:
                tracker_processes.setdefault(tracker, []).append(key)
            process_log_paths[key] = self._get_open_log_paths(process)

        for key, tracker in process_trackers.items():
            if not tracker:
                continue
            matching_processes = tracker_processes.get(tracker, [])
            matching_entries = tracker_entries.get(tracker, [])
            if len(matching_processes) != 1 or len(matching_entries) != 1:
                if len(matching_processes) > 1 or len(matching_entries) > 1:
                    self._set_ambiguity(
                        key,
                        "browser tracker ID is not unique",
                    )
                continue
            self._set_identity(
                key,
                matching_entries[0],
                _EVIDENCE_TRACKER,
                saved_usernames,
                process_tracker=tracker,
            )

        for key, open_paths in process_log_paths.items():
            matches = [
                path_entries[path]
                for path in open_paths
                if path in path_entries
            ]
            if len(matches) == 1:
                self._set_identity(
                    key,
                    matches[0],
                    _EVIDENCE_OPEN_FILE,
                    saved_usernames,
                    process_tracker=process_trackers.get(key, ""),
                )
            elif len(matches) > 1 and key not in self._identities:
                self._set_ambiguity(key, "multiple open Roblox logs were found")

        return process_trackers, process_log_paths

    def _apply_safe_timestamp_fallback(
        self,
        live_processes: dict[tuple[int, float], psutil.Process],
        entries: list[presence_mod.RobloxLogEntry],
        saved_usernames: dict[str, str],
        process_trackers: dict[tuple[int, float], str],
        process_log_paths: dict[tuple[int, float], set[str]],
    ) -> None:
        unresolved = [
            key
            for key in live_processes
            if key not in self._identities
            and not process_trackers.get(key)
            and not process_log_paths.get(key)
        ]
        if len(unresolved) != 1:
            if len(unresolved) > 1:
                for key in unresolved:
                    self._set_ambiguity(
                        key,
                        "multiple processes require timestamp matching",
                    )
            return

        key = unresolved[0]
        create_time = self._create_time_utc(key[1])
        candidates = [
            entry
            for entry in entries
            if entry.path not in self._claimed_logs
            and entry.user_id in saved_usernames
            and -_LOG_EARLY_TOLERANCE_SEC
            <= (entry.timestamp - create_time).total_seconds()
            <= _LOG_STARTUP_WINDOW_SEC
        ]
        if len(candidates) == 1:
            self._set_identity(
                key,
                candidates[0],
                _EVIDENCE_TIMESTAMP,
                saved_usernames,
            )
        elif len(candidates) > 1:
            self._set_ambiguity(key, "multiple timestamp log matches were found")

    def _refresh_unresolved_usernames(
        self,
        saved_usernames: dict[str, str],
    ) -> None:
        for key, identity in list(self._identities.items()):
            if identity.username:
                continue
            username = self._get_username(identity.user_id, saved_usernames)
            if not username:
                continue
            self._identities[key] = _ProcessIdentity(
                user_id=identity.user_id,
                username=username,
                log_path=identity.log_path,
                browser_tracker_id=identity.browser_tracker_id,
                evidence=identity.evidence,
            )
            self._managed_titles.add(username)
            print(
                f"[INFO] Mapped Roblox PID {key[0]} -> "
                f"'{username}' using {_EVIDENCE_NAMES[identity.evidence]}"
            )

    def _find_main_window(
        self,
        key: tuple[int, float],
        windows: list[int],
    ) -> int:
        if not self._process_is_current(key):
            return 0
        candidates: list[tuple[int, int]] = []
        for hwnd in windows:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    continue
                if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                    continue
                title = (win32gui.GetWindowText(hwnd) or "").strip()
                if not title:
                    continue
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                area = max(0, right - left) * max(0, bottom - top)
                if area > 0:
                    candidates.append((area, hwnd))
            except Exception:
                pass
        if not candidates:
            return 0
        return max(candidates, key=lambda item: (item[0], item[1]))[1]

    def _enforce_window_title(
        self,
        key: tuple[int, float],
        identity: _ProcessIdentity,
        target_title: str,
        saved_titles: set[str],
        windows: list[int],
    ) -> None:
        pid = key[0]
        hwnd = self._find_main_window(key, windows)
        if not hwnd:
            if key not in self._waiting_for_window:
                self._waiting_for_window.add(key)
                print(
                    f"[INFO] Roblox main window for PID {pid} "
                    f"({target_title}) is not visible yet"
                )
            return

        self._waiting_for_window.discard(key)
        self._main_windows[key] = hwnd
        try:
            current_title = (win32gui.GetWindowText(hwnd) or "").strip()
        except Exception:
            return
        if current_title == target_title:
            return

        lower_title = current_title.lower()
        can_correct = (
            identity.evidence >= _EVIDENCE_OPEN_FILE
            or "roblox" in lower_title
            or current_title in saved_titles
            or current_title in self._managed_titles
        )
        if not can_correct or not self._process_is_current(key):
            return

        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                return
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if window_pid != pid:
                return
            win32gui.SetWindowText(hwnd, target_title)
            if win32gui.GetWindowText(hwnd) != target_title:
                return
            self._managed_titles.add(target_title)
            print(
                f"[INFO] Renamed Roblox main window HWND 0x{hwnd:08X} "
                f"PID {pid} -> '{target_title}'"
            )
        except Exception as exc:
            print(
                f"[ERROR] Failed to rename Roblox main window PID {pid}: "
                f"{type(exc).__name__}: {exc}"
            )

    def _do_scan(self) -> None:
        try:
            discovered = presence_mod.get_roblox_processes()
            live_processes = {
                (pid, create_time): process
                for pid, (create_time, process) in discovered.items()
            }
            self._remove_exited_state(set(live_processes))
            if not live_processes:
                return

            saved_accounts = self._get_saved_accounts()
            saved_usernames = self._get_saved_usernames(saved_accounts)
            earliest_time = min(
                self._create_time_utc(key[1])
                for key in live_processes
            ) - timedelta(seconds=_LOG_EARLY_TOLERANCE_SEC)
            latest_time = max(
                self._create_time_utc(key[1])
                for key in live_processes
            ) + timedelta(seconds=_LOG_STARTUP_WINDOW_SEC)
            entries = presence_mod.get_roblox_log_entries(
                earliest_time=earliest_time,
                latest_time=latest_time,
            )
            process_trackers, process_log_paths = self._collect_direct_evidence(
                live_processes,
                entries,
                saved_usernames,
            )
            self._apply_safe_timestamp_fallback(
                live_processes,
                entries,
                saved_usernames,
                process_trackers,
                process_log_paths,
            )
            self._refresh_unresolved_usernames(saved_usernames)

            saved_titles = set(saved_usernames.values())
            saved_titles.update(
                account["note"]
                for account in saved_accounts.values()
                if account.get("note")
            )
            windows_by_pid = presence_mod.get_windows_by_pid(set(discovered))
            for key in sorted(live_processes, key=lambda item: (item[1], item[0])):
                identity = self._identities.get(key)
                if identity and identity.username:
                    target_title = self._get_title_target(
                        identity,
                        saved_accounts,
                    )
                    if not target_title:
                        continue
                    self._enforce_window_title(
                        key,
                        identity,
                        target_title,
                        saved_titles,
                        windows_by_pid.get(key[0], []),
                    )
        except Exception as exc:
            print(
                f"[ERROR] Rename Roblox Windows scan failed: "
                f"{type(exc).__name__}: {exc}"
            )
