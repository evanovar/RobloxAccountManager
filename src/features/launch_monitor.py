"""Serialize Multi Roblox launches until each matching client is ready."""

import re
import os
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import psutil
import win32con
import win32gui

from classes.operation_result import OperationResult
from features import account_actions as actions, presence

LAUNCH_LOCK = threading.Lock()
_TIMEOUT = 120.0
_STABLE_SECONDS = 2.0
_POLL_SECONDS = 0.2
_TRACKER = re.compile(r"browsertrackerid[^0-9]{0,32}(\d+)", re.IGNORECASE)
_WEB_TRACKER = re.compile(r"web launch, websiteBTId is (\d+)", re.IGNORECASE)
_GAME_USER = re.compile(r"\[FLog::GameJoinLoadTime\].*\buserid:(\d+)(?=[,\s])", re.IGNORECASE)


@dataclass
class _StartupLogState:
    identity: tuple[int, int] | None = None
    mtime_ns: int = 0
    offset: int = 0
    partial: bytes = b""
    matched: bool = False
    user_id: str = ""
    challenged: bool = False

    def _evidence(self, line: bytes, tracker: str, complete: bool = True):
        content = line.decode("utf-8", errors="replace")
        matched = any(
            match[1] == tracker and (complete or match.end() < len(content))
            for match in _WEB_TRACKER.finditer(content)
        )
        user = _GAME_USER.search(content)
        return matched, user[1] if user else "", "challengedByGcs" in content

    def read(self, path: str, tracker: str):
        with open(path, "rb") as handle:
            stat = os.fstat(handle.fileno())
            identity = (stat.st_dev, stat.st_ino)
            if (identity != self.identity or stat.st_size < self.offset
                    or (stat.st_size == self.offset and stat.st_mtime_ns != self.mtime_ns)):
                self.identity = identity
                self.offset = 0
                self.partial = b""
                self.matched = False
                self.user_id = ""
                self.challenged = False
            handle.seek(self.offset)
            while chunk := handle.read(64 * 1024):
                self.offset += len(chunk)
                lines = (self.partial + chunk).split(b"\n")
                self.partial = lines.pop()
                for line in lines:
                    matched, user_id, challenged = self._evidence(line, tracker)
                    self.matched |= matched
                    self.user_id = self.user_id or user_id
                    self.challenged |= challenged
            self.mtime_ns = stat.st_mtime_ns
        # A complete marker may be visible before its final newline is written.
        # Keep that line pending so a split marker can be finished on the next poll.
        matched, user_id, challenged = self._evidence(self.partial, tracker, complete=False)
        return self.matched or matched, self.user_id or user_id, self.challenged or challenged


def _read_launch_state(tracker, created, cache=None):
    """Read only the startup log carrying the exact tracker sent to this client."""
    cache = {} if cache is None else cache
    logs_dir = os.path.join(os.getenv("LOCALAPPDATA", ""), "Roblox", "logs")
    matches = []
    try:
        filenames = os.listdir(logs_dir)
    except OSError:
        return "", False
    for filename in filenames:
        if not filename.endswith("_last.log") or "CrashHandler" in filename:
            continue
        timestamp = re.search(r"(\d{8}T\d{6}Z)_Player_", filename)
        if not timestamp:
            continue
        try:
            started = datetime.strptime(timestamp[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
            if not -2 <= started - created <= 60:
                continue
            path = os.path.join(logs_dir, filename)
            state = cache.setdefault((path, tracker), _StartupLogState())
            matched, user_id, challenged = state.read(path, tracker)
        except (OSError, ValueError):
            continue
        if not matched:
            continue
        matches.append((user_id, challenged))
    # Unknown/ambiguous evidence must never establish an authenticated join.
    return matches[0] if len(matches) == 1 else ("", False)


def _failure(code, message):
    return OperationResult.failure(
        code, "Roblox Launch Could Not Be Confirmed", message,
        retryable=True,
    )


def check_launched_client(result, username):
    data = result.data if isinstance(result.data, dict) else {}
    identity = data.get("process_identity")
    if identity is None:
        return result
    pid, created = identity
    try:
        process = psutil.Process(pid)
        if process.is_running() and abs(process.create_time() - created) <= 0.01:
            return result
    except psutil.NoSuchProcess:
        pass
    except psutil.Error:
        return _failure("ROBLOX_CLIENT_UNVERIFIED", f"Could not verify the running client for {username}.")
    return _failure("ROBLOX_CLIENT_EXITED", f"The Roblox client for {username} exited before the batch finished.")


def _session_active(session):
    return actions._mr_handle is session and actions.is_multi_roblox_running()


def _snapshot():
    return {
        (pid, created): process
        for pid, (created, process) in presence.get_roblox_processes(force=True).items()
    }


def wait_for_launch_slot(session):
    """Avoid sending another URL while a live client still owns singleton handles."""
    deadline = time.monotonic() + _TIMEOUT
    while _session_active(session):
        if session.get("mode") != "handle64" or actions.singleton_handles_ready(set(_snapshot())):
            return OperationResult.success()
        if time.monotonic() >= deadline:
            return _failure(
                "MULTI_ROBLOX_NOT_READY",
                "Handle64 has not cleared the running clients. No new launch was sent. "
                "Check Multi Roblox in the Console and try again.",
            )
        time.sleep(_POLL_SECONDS)
    return _failure("MULTI_ROBLOX_STOPPED", "Multi Roblox stopped before the launch was sent.")


def _has_main_window(pid):
    for hwnd in presence.get_windows_by_pid({pid}).get(pid, []):
        try:
            # Hidden/headless windows still establish that the client started.
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                continue
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if right > left and bottom > top and win32gui.GetWindowText(hwnd):
                return True
        except Exception:
            continue
    return False


def confirm_launch(result, session, before, username):
    """A URL handoff is not success: require its exact tracker, window and readiness."""
    data = result.data if isinstance(result.data, dict) else {}
    tracker = str(data.get("browser_tracker_id", ""))
    expected_user = str(data.get("expected_user_id", ""))
    requires_join = data.get("requires_game_join", True)
    if not tracker:
        return _failure("LAUNCH_EVIDENCE_MISSING", "The launcher did not supply a launch tracker.")
    if requires_join and expected_user in ("", "0"):
        return OperationResult.failure(
            "LAUNCH_ACCOUNT_ID_MISSING", "Account Identity Missing",
            f"The saved user ID for {username} is missing. Further launches are paused. "
            "Re-add the account before restarting Multi Roblox.",
        )
    deadline = time.monotonic() + _TIMEOUT
    identity = None
    process = None
    ready_since = None
    log_cache = {}
    while _session_active(session):
        current = _snapshot()
        matches = []
        for key, candidate in current.items():
            if key in before:
                continue
            try:
                trackers = {
                    match.group(1) for arg in candidate.cmdline()
                    for match in _TRACKER.finditer(arg)
                }
                if tracker in trackers:
                    matches.append((key, candidate))
            except (psutil.Error, OSError):
                continue
        if len(matches) > 1:
            return _failure("LAUNCH_IDENTITY_AMBIGUOUS", "Multiple clients have this launch tracker.")
        if matches:
            key, candidate = matches[0]
            if identity is not None and identity != key:
                ready_since = None
            identity, process = key, candidate
            user_id, challenged = _read_launch_state(tracker, key[1], log_cache)
            if challenged:
                return OperationResult.failure(
                    "ROBLOX_SECURITY_CHALLENGE", "Roblox Verification Required",
                    f"Roblox requested verification while launching {username}. "
                    "Further launches are paused. Close the challenged client and verify "
                    "the account on roblox.com before restarting Multi Roblox.",
                )
            if user_id and expected_user and user_id != expected_user:
                return OperationResult.failure(
                    "ROBLOX_ACCOUNT_MISMATCH", "Roblox Account Mismatch",
                    f"The client launched for {username} joined as a different account. "
                    "Further launches are paused. Close all Roblox clients before restarting Multi Roblox.",
                    detail=f"Expected user ID {expected_user}; joined user ID {user_id}; PID {key[0]}.",
                )
            handles_ready = (
                session.get("mode") != "handle64"
                or actions.singleton_handles_ready(set(current))
            )
            if _has_main_window(key[0]) and handles_ready and (not requires_join or user_id == expected_user):
                if ready_since is None:
                    ready_since = time.monotonic()
                if time.monotonic() - ready_since >= _STABLE_SECONDS:
                    print(f"[SUCCESS] Confirmed Roblox {'game join' if requires_join else 'client window'} for {username}: PID {key[0]}")
                    return replace(result, data={**data, "process_identity": key})
            else:
                ready_since = None
        else:
            ready_since = None
            if process is not None and not process.is_running():
                return _failure(
                    "ROBLOX_CLIENT_EXITED",
                    f"The Roblox client for {username} exited during startup. "
                    "Check Multi Roblox and try again.",
                )
        if time.monotonic() >= deadline:
            return _failure(
                "ROBLOX_LAUNCH_UNCONFIRMED",
                f"The Roblox launch for {username} could not be verified within {_TIMEOUT:g} seconds. "
                "Further launches are paused. Check open clients and the Console before restarting Multi Roblox.",
            )
        time.sleep(_POLL_SECONDS)
    return _failure("MULTI_ROBLOX_STOPPED", "Multi Roblox stopped while the client was starting.")
