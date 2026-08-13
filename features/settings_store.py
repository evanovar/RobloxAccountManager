"""
Thread-safe cached storage for UI settings.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time

from utils.app_paths import get_data_dir


_SETTINGS_PATH = os.path.join(get_data_dir(), "ui_settings.json")
_LOCK = threading.RLock()
_CACHE: dict = {}
_LOADED = False
_MTIME_NS: int | None = None
_LAST_STAT_CHECK = 0.0
_STAT_INTERVAL = 0.5


def _get_mtime_ns() -> int | None:
    try:
        return os.stat(_SETTINGS_PATH).st_mtime_ns
    except OSError:
        return None


def _load_from_disk_locked() -> None:
    global _CACHE
    global _LOADED
    global _MTIME_NS
    global _LAST_STAT_CHECK

    data = {}
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            data = loaded
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError):
        pass

    _CACHE = data
    _MTIME_NS = _get_mtime_ns()
    _LAST_STAT_CHECK = time.monotonic()
    _LOADED = True


def _refresh_locked() -> None:
    global _LAST_STAT_CHECK
    now = time.monotonic()
    if _LOADED and now - _LAST_STAT_CHECK < _STAT_INTERVAL:
        return
    _LAST_STAT_CHECK = now
    current_mtime = _get_mtime_ns()
    if not _LOADED or current_mtime != _MTIME_NS:
        _load_from_disk_locked()


def _write_locked(settings: dict) -> None:
    global _CACHE
    global _LOADED
    global _MTIME_NS
    global _LAST_STAT_CHECK

    data_dir = os.path.dirname(_SETTINGS_PATH)
    os.makedirs(data_dir, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(
        prefix=".ui_settings.",
        suffix=".tmp",
        dir=data_dir,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, _SETTINGS_PATH)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise

    _CACHE = copy.deepcopy(settings)
    _MTIME_NS = _get_mtime_ns()
    _LAST_STAT_CHECK = time.monotonic()
    _LOADED = True


def load() -> dict:
    with _LOCK:
        _refresh_locked()
        return copy.deepcopy(_CACHE)


def get(key: str, default=None):
    with _LOCK:
        _refresh_locked()
        return copy.deepcopy(_CACHE.get(key, default))


def save(key: str, value) -> bool:
    with _LOCK:
        _refresh_locked()
        if key in _CACHE and _CACHE.get(key) == value:
            return False
        updated = copy.deepcopy(_CACHE)
        updated[key] = copy.deepcopy(value)
        _write_locked(updated)
        return True


def replace(settings: dict) -> bool:
    if not isinstance(settings, dict):
        raise TypeError("UI settings must be a dictionary")
    with _LOCK:
        _refresh_locked()
        if _CACHE == settings:
            return False
        _write_locked(copy.deepcopy(settings))
        return True


def invalidate() -> None:
    global _LOADED
    global _LAST_STAT_CHECK
    with _LOCK:
        _LOADED = False
        _LAST_STAT_CHECK = 0.0
