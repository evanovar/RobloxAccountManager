"""
Avatar headshot fetching logic.
"""

from __future__ import annotations

import collections
import concurrent.futures
import os
import threading
from typing import Callable, Optional

import requests

from classes.roblox_api import RobloxAPI
from utils.app_paths import get_data_dir


_CACHE_DIR = os.path.join(get_data_dir(), "avatar_cache")
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="avatar",
)
_LOCK = threading.RLock()
_THREAD_LOCAL = threading.local()
_INFLIGHT: dict[str, list[tuple[str, Callable[[str, bytes], None]]]] = {}
_MEMORY_CACHE: collections.OrderedDict[str, bytes] = collections.OrderedDict()
_MEMORY_CACHE_LIMIT = 128
_SYNC_RUNNING = False

AVATAR_SIZE = 22


def _get_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        _THREAD_LOCAL.session = session
    return session


def _cache_path(user_id: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{user_id}.png")


def _remember(user_id: str, data: bytes) -> None:
    with _LOCK:
        _MEMORY_CACHE[user_id] = data
        _MEMORY_CACHE.move_to_end(user_id)
        while len(_MEMORY_CACHE) > _MEMORY_CACHE_LIMIT:
            _MEMORY_CACHE.popitem(last=False)


def load_cached_bytes(user_id: str) -> Optional[bytes]:
    uid = str(user_id)
    with _LOCK:
        cached = _MEMORY_CACHE.get(uid)
        if cached is not None:
            _MEMORY_CACHE.move_to_end(uid)
            return cached

    path = _cache_path(uid)
    try:
        with open(path, "rb") as f:
            data = f.read()
        if data:
            _remember(uid, data)
            return data
    except FileNotFoundError:
        pass
    except OSError:
        pass
    return None


def _save_to_cache(user_id: str, data: bytes) -> None:
    _remember(user_id, data)
    try:
        with open(_cache_path(user_id), "wb") as f:
            f.write(data)
    except OSError:
        pass


def fetch_avatar_urls(user_ids: list[str]) -> dict[str, str]:
    unique_ids = list(dict.fromkeys(
        str(user_id) for user_id in user_ids
        if str(user_id) and str(user_id) != "0"
    ))
    results: dict[str, str] = {}
    for start in range(0, len(unique_ids), 100):
        batch = unique_ids[start:start + 100]
        try:
            response = _get_session().get(
                "https://thumbnails.roblox.com/v1/users/avatar-headshot",
                params={
                    "userIds": ",".join(batch),
                    "size": "100x100",
                    "format": "Png",
                    "isCircular": "true",
                },
                timeout=6,
            )
            if response.status_code != 200:
                continue
            for item in response.json().get("data", []):
                user_id = str(item.get("targetId", ""))
                image_url = str(item.get("imageUrl", "") or "")
                if user_id and image_url:
                    results[user_id] = image_url
        except (requests.RequestException, ValueError, TypeError):
            continue
    return results


def fetch_avatar_url(user_id: str) -> Optional[str]:
    return fetch_avatar_urls([str(user_id)]).get(str(user_id))


def _complete_fetch(user_id: str, data: bytes | None) -> None:
    with _LOCK:
        callbacks = _INFLIGHT.pop(user_id, [])
    if not data:
        return
    for username, callback in callbacks:
        try:
            callback(username, data)
        except Exception:
            pass


def _fetch_worker(user_id: str, image_url: str = "") -> None:
    cached = load_cached_bytes(user_id)
    if cached:
        _complete_fetch(user_id, cached)
        return

    url = image_url or fetch_avatar_url(user_id) or ""
    if not url:
        _complete_fetch(user_id, None)
        return
    try:
        response = _get_session().get(url, timeout=8)
        if response.status_code == 200 and response.content:
            _save_to_cache(user_id, response.content)
            _complete_fetch(user_id, response.content)
            return
    except requests.RequestException:
        pass
    _complete_fetch(user_id, None)


def fetch_avatar_async(
    user_id: str,
    username: str,
    on_done: Callable[[str, bytes], None],
    image_url: str = "",
) -> None:
    uid = str(user_id).strip()
    if not uid or uid == "0":
        return

    with _LOCK:
        callbacks = _INFLIGHT.get(uid)
        if callbacks is not None:
            callbacks.append((username, on_done))
            return
        _INFLIGHT[uid] = [(username, on_done)]
    _EXECUTOR.submit(_fetch_worker, uid, image_url)


def sync_missing_avatar_cache(
    accounts: dict[str, dict],
    on_avatar_ready: Callable[[str, bytes], None] | None = None,
    on_complete: Callable[[], None] | None = None,
) -> None:
    global _SYNC_RUNNING
    with _LOCK:
        if _SYNC_RUNNING:
            return
        _SYNC_RUNNING = True

    account_snapshot = [
        (username, data)
        for username, data in list(accounts.items())
        if isinstance(data, dict)
    ]

    def _coordinator() -> None:
        global _SYNC_RUNNING
        changed = False
        resolved: list[tuple[str, dict, str]] = []
        try:
            for username, data in account_snapshot:
                user_id = str(data.get("user_id") or "").strip()
                if not user_id or user_id == "0":
                    try:
                        resolved_id = RobloxAPI.get_user_id_from_username(username)
                    except Exception:
                        resolved_id = None
                    if resolved_id:
                        user_id = str(resolved_id)
                        data["user_id"] = resolved_id
                        changed = True
                if user_id and user_id != "0":
                    resolved.append((username, data, user_id))

            missing_ids = [
                user_id for _, _, user_id in resolved
                if load_cached_bytes(user_id) is None
            ]
            urls = fetch_avatar_urls(missing_ids)
            for username, data, user_id in resolved:
                image_url = urls.get(user_id, "")
                if image_url and data.get("avatar_url") != image_url:
                    data["avatar_url"] = image_url
                    changed = True
                if on_avatar_ready:
                    fetch_avatar_async(
                        user_id,
                        username,
                        on_avatar_ready,
                        image_url=image_url,
                    )
            if changed and on_complete:
                try:
                    on_complete()
                except Exception:
                    pass
        finally:
            with _LOCK:
                _SYNC_RUNNING = False

    _EXECUTOR.submit(_coordinator)
