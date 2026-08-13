"""
Diagnostics and crash reporting.
"""

from __future__ import annotations

import collections
import ctypes
from datetime import datetime
import os
import platform
import re
import sys
import tempfile
import threading
import time
import traceback

from utils.app_paths import get_data_dir

_LOCK = threading.RLock()
_RECENT_LINES: collections.deque[str] = collections.deque(maxlen=500)
_SESSION_LOG_PATH = ""
_STARTUP_STAGE = "process import"
_APP_VERSION = "unknown"
_INSTALLED = False
_UI_READY = False
_ORIGINAL_STDOUT = None
_ORIGINAL_STDERR = None
_ORIGINAL_SYS_EXCEPTHOOK = None
_ORIGINAL_THREAD_EXCEPTHOOK = None
_LAST_UI_HEARTBEAT = 0.0
_HEALTH_STOP = threading.Event()
_HEALTH_THREAD = None
_SESSION_LOG_HANDLE = None

_REDACTION_PATTERNS = (
    (
        re.compile(r"(?i)(\.ROBLOSECURITY\s*=\s*)[^;\s\"']+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)([\"']?(?:cookie|password|auth_ticket)[\"']?\s*[:=]\s*[\"'])[^\"']+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)(privateServerLinkCode=)[^&\s\"']+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)(link code:\s*)[A-Za-z0-9_-]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"https://(?:canary\.)?discord(?:app)?\.com/api/webhooks/[^\s\"']+"),
        "[REDACTED DISCORD WEBHOOK]",
    ),
    (
        re.compile(r"_\|WARNING:-DO-NOT-SHARE-THIS\.[^\s\"']+"),
        "[REDACTED ROBLOX COOKIE]",
    ),
)


def redact(value) -> str:
    text = str(value)
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _safe_write(path: str, text: str) -> None:
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
    except Exception:
        pass


def _record_line(line: str, stream_name: str = "stdout") -> None:
    if not line.strip():
        return
    cleaned = redact(line.rstrip("\r\n"))
    entry = f"[{_timestamp()}] [{stream_name}] {cleaned}"
    with _LOCK:
        _RECENT_LINES.append(entry)
        if _SESSION_LOG_HANDLE is not None:
            try:
                _SESSION_LOG_HANDLE.write(entry + "\n")
            except Exception:
                pass
        else:
            _safe_write(_SESSION_LOG_PATH, entry + "\n")


def flush_session_log() -> None:
    with _LOCK:
        if _SESSION_LOG_HANDLE is not None:
            try:
                _SESSION_LOG_HANDLE.flush()
            except Exception:
                pass


class DiagnosticStream:
    def __init__(self, original, stream_name: str):
        self._original = original
        self._stream_name = stream_name
        self._buffer = ""
        self._write_lock = threading.RLock()

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        with self._write_lock:
            if self._original is not None:
                try:
                    self._original.write(text)
                except Exception:
                    pass

            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                _record_line(line, self._stream_name)
        return len(text)

    def flush(self) -> None:
        with self._write_lock:
            if self._buffer:
                _record_line(self._buffer, self._stream_name)
                self._buffer = ""
            if self._original is not None:
                try:
                    self._original.flush()
                except Exception:
                    pass

    def fileno(self) -> int:
        try:
            return self._original.fileno()
        except Exception:
            return -1

    def isatty(self) -> bool:
        try:
            return bool(self._original.isatty())
        except Exception:
            return False

    @property
    def encoding(self):
        return getattr(self._original, "encoding", "utf-8")


def set_startup_stage(stage: str) -> None:
    global _STARTUP_STAGE
    _STARTUP_STAGE = str(stage)
    record_message(f"Startup stage: {_STARTUP_STAGE}")


def mark_ui_ready() -> None:
    global _UI_READY
    global _LAST_UI_HEARTBEAT
    _UI_READY = True
    _LAST_UI_HEARTBEAT = time.monotonic()
    set_startup_stage("UI ready")


def pulse_ui() -> None:
    global _LAST_UI_HEARTBEAT
    _LAST_UI_HEARTBEAT = time.monotonic()


def _health_monitor() -> None:
    warned = False
    while not _HEALTH_STOP.wait(5):
        if not _UI_READY or not _LAST_UI_HEARTBEAT:
            continue
        stalled_for = time.monotonic() - _LAST_UI_HEARTBEAT
        if stalled_for >= 30 and not warned:
            record_message(
                f"The UI event loop has not responded for {stalled_for:.1f} seconds.",
                "WARNING",
            )
            warned = True
        elif stalled_for < 15:
            warned = False


def record_message(message: str, level: str = "INFO") -> None:
    _record_line(f"[{level}] {message}", "diagnostics")


def get_session_log_path() -> str:
    return _SESSION_LOG_PATH


def get_recent_lines(limit: int = 200) -> list[str]:
    with _LOCK:
        return list(_RECENT_LINES)[-max(1, int(limit)):]


def _build_crash_path() -> str:
    data_dir = _get_diagnostics_root()
    crash_dir = os.path.join(data_dir, "crash_logs")
    os.makedirs(crash_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    return os.path.join(crash_dir, f"crash-{stamp}.log")


def _get_diagnostics_root() -> str:
    preferred = get_data_dir()
    try:
        os.makedirs(preferred, exist_ok=True)
        return preferred
    except Exception:
        fallback = os.path.join(tempfile.gettempdir(), "EvanovarRAM")
        os.makedirs(fallback, exist_ok=True)
        return fallback


def report_exception(
    context: str,
    exception,
    traceback_object=None,
    fatal: bool = False,
) -> str:
    try:
        crash_path = _build_crash_path()
    except Exception:
        crash_path = ""

    exception_type = type(exception)
    if traceback_object is None:
        traceback_object = getattr(exception, "__traceback__", None)
    formatted_traceback = "".join(
        traceback.format_exception(exception_type, exception, traceback_object)
    )

    details = [
        "Evanovar RAM crash report",
        f"Timestamp: {_timestamp()}",
        f"Application version: {_APP_VERSION}",
        f"Mode: {'compiled' if getattr(sys, 'frozen', False) else 'source'}",
        f"Python: {platform.python_version()}",
        f"Windows: {platform.platform()}",
        f"Executable: {redact(sys.executable)}",
        f"Thread: {threading.current_thread().name}",
        f"Startup stage: {_STARTUP_STAGE}",
        f"Fatal: {fatal}",
        f"Context: {redact(context)}",
        "",
        "Exception:",
        redact(formatted_traceback.rstrip()),
        "",
        "Recent console:",
        *get_recent_lines(),
        "",
    ]
    report = "\n".join(details)
    if crash_path:
        _safe_write(crash_path, report)
    _record_line(
        f"[ERROR] {context}: {exception_type.__name__}: {redact(exception)}",
        "diagnostics",
    )
    return crash_path


def show_native_error(title: str, message: str) -> None:
    safe_title = redact(title)
    safe_message = redact(message)
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            safe_message,
            safe_title,
            0x1010,
        )
    except Exception:
        target = _ORIGINAL_STDERR or getattr(sys, "__stderr__", None)
        if target is not None:
            try:
                target.write(f"{safe_title}: {safe_message}\n")
                target.flush()
            except Exception:
                pass


def _handle_unhandled_exception(exception_type, exception, traceback_object) -> None:
    if issubclass(exception_type, KeyboardInterrupt):
        if _ORIGINAL_SYS_EXCEPTHOOK:
            _ORIGINAL_SYS_EXCEPTHOOK(exception_type, exception, traceback_object)
        return

    crash_path = report_exception(
        "Unhandled main-thread exception",
        exception,
        traceback_object,
        fatal=True,
    )
    location = crash_path or _SESSION_LOG_PATH or "AccountManagerData"
    show_native_error(
        "Evanovar RAM Crashed",
        "The application encountered an unexpected error.\n\n"
        f"Crash report:\n{location}",
    )


def _handle_thread_exception(args) -> None:
    crash_path = report_exception(
        f"Unhandled background exception in {args.thread.name}",
        args.exc_value,
        args.exc_traceback,
        fatal=False,
    )
    _record_line(
        f"[ERROR] Background task crashed. Report: {crash_path}",
        "diagnostics",
    )


def install(app_version: str) -> str:
    global _APP_VERSION
    global _INSTALLED
    global _ORIGINAL_STDOUT
    global _ORIGINAL_STDERR
    global _ORIGINAL_SYS_EXCEPTHOOK
    global _ORIGINAL_THREAD_EXCEPTHOOK
    global _SESSION_LOG_PATH
    global _HEALTH_THREAD
    global _SESSION_LOG_HANDLE

    if _INSTALLED:
        return _SESSION_LOG_PATH

    _APP_VERSION = str(app_version)
    data_dir = _get_diagnostics_root()
    log_dir = os.path.join(data_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _SESSION_LOG_PATH = os.path.join(log_dir, f"session-{stamp}.log")
    try:
        _SESSION_LOG_HANDLE = open(
            _SESSION_LOG_PATH,
            "a",
            encoding="utf-8",
            buffering=8192,
        )
    except OSError:
        _SESSION_LOG_HANDLE = None

    _ORIGINAL_STDOUT = sys.stdout or getattr(sys, "__stdout__", None)
    _ORIGINAL_STDERR = sys.stderr or getattr(sys, "__stderr__", None)
    _ORIGINAL_SYS_EXCEPTHOOK = sys.excepthook
    _ORIGINAL_THREAD_EXCEPTHOOK = getattr(threading, "excepthook", None)

    sys.stdout = DiagnosticStream(_ORIGINAL_STDOUT, "stdout")
    sys.stderr = DiagnosticStream(_ORIGINAL_STDERR, "stderr")
    sys.excepthook = _handle_unhandled_exception
    threading.excepthook = _handle_thread_exception
    _INSTALLED = True

    _HEALTH_STOP.clear()
    _HEALTH_THREAD = threading.Thread(
        target=_health_monitor,
        daemon=True,
        name="diagnostics-health",
    )
    _HEALTH_THREAD.start()

    record_message(
        f"Diagnostics started. Session log: {_SESSION_LOG_PATH}"
    )
    set_startup_stage("diagnostics initialized")
    return _SESSION_LOG_PATH


def shutdown(exit_code: int = 0) -> None:
    global _SESSION_LOG_HANDLE
    _HEALTH_STOP.set()
    record_message(f"Application exit code: {exit_code}")
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stderr.flush()
    except Exception:
        pass
    with _LOCK:
        if _SESSION_LOG_HANDLE is not None:
            try:
                _SESSION_LOG_HANDLE.flush()
                _SESSION_LOG_HANDLE.close()
            except Exception:
                pass
            _SESSION_LOG_HANDLE = None
