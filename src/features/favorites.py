"""
features/favorites.py
Saved Place ID + Private Server Link favorites for quick re-joining.
"""

from __future__ import annotations

import json
import os
import threading

from utils.app_paths import get_data_dir
from utils.atomic_io import quarantine_corrupt, write_json_atomic

_DATA_DIR = get_data_dir()
_FAVORITES_FILE = os.path.join(_DATA_DIR, "favorites.json")
_LOCK = threading.RLock()


def load_favorites() -> list[dict]:
    try:
        if os.path.exists(_FAVORITES_FILE):
            with open(_FAVORITES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            quarantine_corrupt(_FAVORITES_FILE)
    except ValueError:
        quarantine_corrupt(_FAVORITES_FILE)
    except Exception:
        pass
    return []


def save_favorites(favorites: list[dict]) -> None:
    write_json_atomic(_FAVORITES_FILE, favorites, prefix=".favorites.")


def add_favorite(place_id: str, name: str, private_server: str = "") -> None:
    if not place_id:
        return
    with _LOCK:
        favorites = [
            f for f in load_favorites()
            if not (str(f.get("place_id")) == str(place_id)
                    and str(f.get("private_server", "")) == str(private_server))
        ]
        favorites.insert(0, {
            "place_id": str(place_id),
            "name": name or str(place_id),
            "private_server": private_server or "",
        })
        save_favorites(favorites)


def remove_favorite(place_id: str, private_server: str = "") -> None:
    with _LOCK:
        favorites = [
            f for f in load_favorites()
            if not (str(f.get("place_id")) == str(place_id)
                    and str(f.get("private_server", "")) == str(private_server))
        ]
        save_favorites(favorites)
