"""
features/groups.py
Stores all the group data.
"""

from __future__ import annotations

import json
import os
from typing import Optional

_ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GROUPS_FILE = os.path.join(_ROOT_DIR, "AccountManagerData", "groups.json")

def _load() -> dict:
    if os.path.exists(_GROUPS_FILE):
        try:
            with open(_GROUPS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"groups": [], "assignments": {}}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_GROUPS_FILE), exist_ok=True)
    try:
        with open(_GROUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def get_group_names() -> list[str]:
    return list(_load().get("groups", []))


def get_account_group(username: str) -> Optional[str]:
    return _load().get("assignments", {}).get(username)


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
