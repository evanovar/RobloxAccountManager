import threading
import time

from classes.operation_result import OperationResult
from features import account_actions as actions, presence

# one launch at a time across batch, auto-rejoin and websocket
LAUNCH_LOCK = threading.Lock()
_TIMEOUT = 120.0
_POLL_SECONDS = 0.2
# nothing was launched for these, so the rest of a batch would fail the same way
SESSION_FAILURE_CODES = frozenset({'MULTI_ROBLOX_NOT_READY', 'MULTI_ROBLOX_STOPPED'})


def _failure(code, message):
    return OperationResult.failure(
        code, "Roblox Launch Was Not Sent", message,
        retryable=True,
    )


def _session_active(session):
    return actions._mr_handle is session and actions.is_multi_roblox_running()


def _snapshot():
    return {
        (pid, created): process
        for pid, (created, process) in presence.get_roblox_processes(force=True).items()
    }


def wait_for_launch_slot(session):
    # handle64 needs the last client's singleton handles closed before the next launch
    deadline = time.monotonic() + _TIMEOUT
    while _session_active(session):
        if session.get("mode") != "handle64" or actions.singleton_handles_ready(set(_snapshot())):
            return OperationResult.success()
        if time.monotonic() >= deadline:
            return _failure(
                "MULTI_ROBLOX_NOT_READY",
                "Handle64 has not cleared the running clients. No new launch was sent. "
                "Check the Console and restart Multi Roblox before trying again.",
            )
        time.sleep(_POLL_SECONDS)
    return _failure("MULTI_ROBLOX_STOPPED", "Multi Roblox stopped before the launch was sent.")
