from __future__ import annotations

import threading
import time
from contextlib import nullcontext
from typing import Callable

import requests

# same endpoint roblox.com uses for the plus badge
_PROFILES_URL = "https://apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles"
_BATCH_SIZE = 100
FIELD = "roblox_plus"

_RETRY_AFTER = 60.0

_LOCK = threading.Lock()
_RUNNING = False
_SYNCED_THIS_SESSION = False
_LAST_FAILED: float | None = None


def has_plus(data) -> bool:
    return isinstance(data, dict) and data.get(FIELD) is True


def _valid_user_id(user_id) -> str | None:
    text = str(user_id or "").strip()
    if not text.isdigit() or int(text) <= 0:
        return None
    return text


def fetch_plus_status(user_ids: list[str], session=None) -> dict[str, bool]:
    unique_ids = list(dict.fromkeys(uid for uid in map(_valid_user_id, user_ids) if uid))
    results: dict[str, bool] = {}
    http = session or requests
    for start in range(0, len(unique_ids), _BATCH_SIZE):
        batch = unique_ids[start:start + _BATCH_SIZE]
        try:
            response = http.post(
                _PROFILES_URL,
                json={"userIds": [int(uid) for uid in batch], "fields": ["hasRobloxSubscription"]},
                timeout=8,
            )
            if response.status_code != 200:
                print(f"[WARNING] Roblox Plus check failed: HTTP {response.status_code}")
                continue
            for item in response.json().get("profileDetails", []):
                value = item.get("hasRobloxSubscription")
                user_id = _valid_user_id(item.get("userId"))
                if user_id and isinstance(value, bool):
                    results[user_id] = value
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            print(f"[WARNING] Roblox Plus check failed: {type(exc).__name__}")
    return results


def _targets(manager, only_missing: bool) -> dict[str, str]:
    account_lock = getattr(manager, "_accounts_lock", None)
    targets: dict[str, str] = {}
    with account_lock if account_lock is not None else nullcontext():
        for username, data in manager.accounts.items():
            if not isinstance(data, dict):
                continue
            if only_missing and FIELD in data:
                continue
            user_id = _valid_user_id(data.get("user_id"))
            if user_id:
                targets[username] = user_id
    return targets


def _apply(manager, targets: dict[str, str], statuses: dict[str, bool]) -> list[str]:
    account_lock = getattr(manager, "_accounts_lock", None)
    changed = []
    with account_lock if account_lock is not None else nullcontext():
        for username, user_id in targets.items():
            data = manager.accounts.get(username)
            # account may be gone or swapped while the request ran
            if not isinstance(data, dict) or _valid_user_id(data.get("user_id")) != user_id:
                continue
            if user_id not in statuses or data.get(FIELD) is statuses[user_id]:
                continue
            data[FIELD] = statuses[user_id]
            changed.append(username)
    return changed


def sync_plus_status(manager, on_done: Callable[[list[str]], None] | None = None) -> bool:
    # first run checks everyone, later runs only accounts never checked
    global _RUNNING
    with _LOCK:
        if _RUNNING:
            return False
        # dont hammer roblox while offline
        if _LAST_FAILED is not None and time.monotonic() - _LAST_FAILED < _RETRY_AFTER:
            return False
        only_missing = _SYNCED_THIS_SESSION
        targets = _targets(manager, only_missing)
        if not targets:
            return False
        _RUNNING = True

    def worker():
        global _RUNNING, _SYNCED_THIS_SESSION, _LAST_FAILED
        changed: list[str] = []
        try:
            statuses = fetch_plus_status(list(targets.values()))
            if statuses:
                _SYNCED_THIS_SESSION = True
            else:
                _LAST_FAILED = time.monotonic()
            changed = _apply(manager, targets, statuses)
            if changed:
                manager.save_accounts()
        except Exception as exc:
            print(f"[WARNING] Roblox Plus status could not be saved: {exc}")
        finally:
            with _LOCK:
                _RUNNING = False
        if on_done is not None:
            try:
                on_done(changed)
            except Exception as exc:
                print(f"[WARNING] Roblox Plus callback error: {exc}")

    threading.Thread(target=worker, daemon=True, name="RobloxPlus").start()
    return True
