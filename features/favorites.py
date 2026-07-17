"""
features/favorites.py
Saved Place ID + Private Server Link favorites for quick re-joining.
"""

from __future__ import annotations

import json
import os

from utils.app_paths import get_data_dir

_DATA_DIR = get_data_dir()
_FAVORITES_FILE = os.path.join(_DATA_DIR, "favorites.json")


def load_favorites() -> list[dict]:
    try:
        if os.path.exists(_FAVORITES_FILE):
            with open(_FAVORITES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def save_favorites(favorites: list[dict]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favorites, f, indent=2)


def add_favorite(place_id: str, name: str, private_server: str = "") -> None:
    if not place_id:
        return
    favorites = load_favorites()
    favorites = [
        f for f in favorites
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
    favorites = load_favorites()
    favorites = [
        f for f in favorites
        if not (str(f.get("place_id")) == str(place_id)
                and str(f.get("private_server", "")) == str(private_server))
    ]
    save_favorites(favorites)
