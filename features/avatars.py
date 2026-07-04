"""
features/avatars.py
Avatar headshot fetching logic.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional

import requests
from utils.app_paths import get_data_dir

_CACHE_DIR = os.path.join(get_data_dir(), "avatar_cache")

AVATAR_SIZE = 22

def _cache_path(user_id: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{user_id}.png")


def load_cached_bytes(user_id: str) -> Optional[bytes]:
    path = _cache_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception:
            pass
    return None


def _save_to_cache(user_id: str, data: bytes) -> None:
    try:
        with open(_cache_path(user_id), "wb") as f:
            f.write(data)
    except Exception:
        pass

def fetch_avatar_url(user_id: str) -> Optional[str]:
    try:
        api = (
            "https://thumbnails.roblox.com/v1/users/avatar-headshot"
            f"?userIds={user_id}&size=100x100&format=Png&isCircular=true"
        )
        resp = requests.get(api, timeout=6)
        data = resp.json()
        items = data.get("data", [])
        if items and items[0].get("imageUrl"):
            return items[0]["imageUrl"]
    except Exception:
        pass
    return None

AVATAR_JS = """
return fetch(
    'https://thumbnails.roblox.com/v1/users/avatar-headshot'
    + '?userIds=' + (window.Roblox && Roblox.CurrentUser ? Roblox.CurrentUser.userId : 0)
    + '&size=100x100&format=Png&isCircular=true'
)
.then(r => r.json())
.then(d => (d.data && d.data[0] && d.data[0].imageUrl) ? d.data[0].imageUrl : null)
.catch(() => null);
"""


def fetch_avatar_async(user_id: str, username: str, on_done: Callable[[str, bytes], None],) -> None:
    if not user_id or str(user_id) == "0":
        return

    def _worker():
        uid = str(user_id)

        cached = load_cached_bytes(uid)
        if cached:
            on_done(username, cached)
            return

        img_url = fetch_avatar_url(uid)
        if not img_url:
            return

        try:
            resp = requests.get(img_url, timeout=8)
            if resp.status_code == 200 and resp.content:
                _save_to_cache(uid, resp.content)
                on_done(username, resp.content)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()