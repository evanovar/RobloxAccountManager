"""Inspect external file handles in a disposable process, never in the UI app.

The Windows psutil scan may retain the GIL or hang in a native API. A thread
timeout cannot contain that failure. This module is also the frozen app's early
helper entry point; it must not initialize diagnostics, settings, or Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


HELPER_OPTION = "--window-log-probe"
PROBE_TIMEOUT_SECONDS = 3.0
_MAX_RESULT_BYTES = 64 * 1024
_MAX_LOG_PATHS = 256


@dataclass(frozen=True)
class ProbeResult:
    status: str
    paths: frozenset[str] = frozenset()


def _scan(pid: int, expected_create_time: float) -> dict:
    # Keep all psutil calls, including identity checks, inside the helper.
    import psutil

    try:
        process = psutil.Process(pid)
        if (
            abs(process.create_time() - expected_create_time) >= 0.01
            or process.name().casefold() != "robloxplayerbeta.exe"
        ):
            return {"status": "process_changed"}
        paths = sorted({
            os.path.normcase(os.path.abspath(opened.path))
            for opened in process.open_files()
            if opened.path.lower().endswith("_last.log")
        })
        # A PID may exit and be reused while the native scan is running.
        current = psutil.Process(pid)
        if abs(current.create_time() - expected_create_time) >= 0.01:
            return {"status": "process_changed"}
        if len(paths) > _MAX_LOG_PATHS:
            return {"status": "error"}
        return {"status": "ok", "pid": pid,
                "create_time": expected_create_time, "paths": paths}
    except psutil.NoSuchProcess:
        return {"status": "process_changed"}
    except (OSError, psutil.AccessDenied, psutil.ZombieProcess):
        return {"status": "error"}


def helper_main(arguments: list[str]) -> int:
    """Write a small result file even in a windowed build with no stdout."""
    if len(arguments) != 3:
        return 2
    try:
        pid = int(arguments[0])
        create_time = float(arguments[1])
        if pid <= 0 or not math.isfinite(create_time):
            return 2
        payload = _scan(pid, create_time)
        encoded = json.dumps(payload).encode("utf-8")
        if len(encoded) > _MAX_RESULT_BYTES:
            return 1
        Path(arguments[2]).write_bytes(encoded)
        return 0
    except Exception:
        # The parent treats nonzero exits/missing results as unknown evidence.
        return 1


def _helper_command(key: tuple[int, float], result_path: str) -> list[str]:
    arguments = [str(key[0]), repr(key[1]), result_path]
    if getattr(sys, "frozen", False):
        return [sys.executable, HELPER_OPTION, *arguments]
    source_root = Path(__file__).resolve().parents[1]
    return [sys.executable, str(source_root / "main.py"), HELPER_OPTION,
            *arguments]


def _read_result(path: str, key: tuple[int, float]) -> ProbeResult:
    with open(path, "rb") as handle:
        raw = handle.read(_MAX_RESULT_BYTES + 1)
    if len(raw) > _MAX_RESULT_BYTES:
        return ProbeResult("error")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return ProbeResult("error")
    if payload.get("status") == "process_changed":
        return ProbeResult("process_changed")
    if (
        payload.get("status") != "ok"
        or payload.get("pid") != key[0]
        or payload.get("create_time") != key[1]
    ):
        return ProbeResult("error")
    paths = payload.get("paths")
    if not isinstance(paths, list) or len(paths) > _MAX_LOG_PATHS:
        return ProbeResult("error")
    if any(not isinstance(path, str) or not os.path.isabs(path)
           or not path.lower().endswith("_last.log") for path in paths):
        return ProbeResult("error")
    return ProbeResult("ok", frozenset(os.path.normcase(path) for path in paths))


def probe_open_log_paths(
    key: tuple[int, float],
    stop_event: threading.Event,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> ProbeResult:
    """Bound helper lifetime and reap it on timeout, cancellation, or error."""
    if stop_event.is_set():
        return ProbeResult("cancelled")
    try:
        with tempfile.TemporaryDirectory(prefix="ram-window-probe-") as folder:
            result_path = os.path.join(folder, "result.json")
            process = subprocess.Popen(
                _helper_command(key, result_path),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                deadline = time.monotonic() + max(0.0, timeout)
                while process.poll() is None:
                    if stop_event.is_set():
                        return ProbeResult("cancelled")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return ProbeResult("timeout")
                    stop_event.wait(min(0.05, remaining))
                if stop_event.is_set():
                    return ProbeResult("cancelled")
                if process.returncode != 0:
                    return ProbeResult("error")
                return _read_result(result_path, key)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=1)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return ProbeResult("error")
