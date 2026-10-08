"""Serialize Multi Roblox launches until each matching client is ready."""

import re
import threading
import time
from dataclasses import replace

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
    if not tracker:
        return _failure("LAUNCH_EVIDENCE_MISSING", "The launcher did not supply a launch tracker.")
    deadline = time.monotonic() + _TIMEOUT
    identity = None
    process = None
    ready_since = None
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
            handles_ready = (
                session.get("mode") != "handle64"
                or actions.singleton_handles_ready(set(current))
            )
            if _has_main_window(key[0]) and handles_ready:
                if ready_since is None:
                    ready_since = time.monotonic()
                if time.monotonic() - ready_since >= _STABLE_SECONDS:
                    print(f"[SUCCESS] Confirmed Roblox client for {username}: PID {key[0]}")
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
                f"The Roblox client for {username} did not become ready within {_TIMEOUT:g} seconds. "
                "Check open clients and the Console before retrying.",
            )
        time.sleep(_POLL_SECONDS)
    return _failure("MULTI_ROBLOX_STOPPED", "Multi Roblox stopped while the client was starting.")
