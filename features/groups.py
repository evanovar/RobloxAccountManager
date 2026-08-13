"""
features/groups.py
Stores all the group data.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Optional
from utils.app_paths import get_data_dir

_GROUPS_FILE = os.path.join(get_data_dir(), "groups.json")
_LOCK = threading.RLock()
_CACHE: dict | None = None


def _default_data() -> dict:
    return {"groups": [], "assignments": {}}

def _load() -> dict:
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return {
                "groups": list(_CACHE.get("groups", [])),
                "assignments": dict(_CACHE.get("assignments", {})),
            }
        data = _default_data()
        if os.path.exists(_GROUPS_FILE):
            try:
                with open(_GROUPS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, ValueError, TypeError):
                pass
        _CACHE = {
            "groups": list(data.get("groups", [])),
            "assignments": dict(data.get("assignments", {})),
        }
        return {
            "groups": list(_CACHE["groups"]),
            "assignments": dict(_CACHE["assignments"]),
        }


def _save(data: dict) -> None:
    global _CACHE
    with _LOCK:
        normalized = {
            "groups": list(data.get("groups", [])),
            "assignments": dict(data.get("assignments", {})),
        }
        if _CACHE == normalized:
            return
        os.makedirs(get_data_dir(), exist_ok=True)
        descriptor, temp_path = tempfile.mkstemp(
            prefix=".groups.", suffix=".tmp", dir=get_data_dir()
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2)
            os.replace(temp_path, _GROUPS_FILE)
            _CACHE = normalized
        except OSError:
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                os.remove(temp_path)
            except OSError:
                pass

def get_group_names() -> list[str]:
    return list(_load().get("groups", []))


def get_account_group(username: str) -> Optional[str]:
    return _load().get("assignments", {}).get(username)


def get_assignments() -> dict[str, str]:
    return dict(_load().get("assignments", {}))


def set_account_group(username: str, group_name: Optional[str]) -> None:
    data = _load()
    assignments = data.setdefault("assignments", {})
    if group_name is None:
        assignments.pop(username, None)
    else:
        assignments[username] = group_name
    _save(data)


def create_group(name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    data = _load()
    groups = data.setdefault("groups", [])
    if name in groups:
        return False
    groups.append(name)
    _save(data)
    return True


def delete_group(name: str) -> None:
    data = _load()
    groups = data.get("groups", [])
    if name in groups:
        groups.remove(name)
    assignments = data.get("assignments", {})
    for user in [u for u, g in assignments.items() if g == name]:
        del assignments[user]
    _save(data)


def rename_group(old_name: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name or new_name == old_name:
        return False
    data = _load()
    groups = data.get("groups", [])
    if new_name in groups or old_name not in groups:
        return False
    groups[groups.index(old_name)] = new_name
    for user, grp in data.get("assignments", {}).items():
        if grp == old_name:
            data["assignments"][user] = new_name
    _save(data)
    return True
