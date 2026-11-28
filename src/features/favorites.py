from __future__ import annotations

import json
import os
import re
import threading

from utils.app_paths import get_data_dir
from utils.atomic_io import quarantine_corrupt, write_json_atomic

_DATA_DIR = get_data_dir()
_FAVORITES_FILE = os.path.join(_DATA_DIR, "favorites.json")
_LOCK = threading.RLock()


def is_valid_place_id(value) -> bool:
    text = str(value or "").strip()
    return bool(re.fullmatch(r"[0-9]{1,20}", text)) and int(text) > 0


def _same(entry: dict, place_id: str, private_server: str) -> bool:
    return (str(entry.get("place_id")) == str(place_id)
            and str(entry.get("private_server", "") or "") == str(private_server or ""))


def load_favorites() -> list[dict]:
    try:
        if os.path.exists(_FAVORITES_FILE):
            with open(_FAVORITES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [entry for entry in data if isinstance(entry, dict) and entry.get("place_id")]
            quarantine_corrupt(_FAVORITES_FILE)
    except ValueError:
        quarantine_corrupt(_FAVORITES_FILE)
    except Exception:
        pass
    return []


def save_favorites(favorites: list[dict]) -> None:
    write_json_atomic(_FAVORITES_FILE, favorites, prefix=".favorites.")


def add_favorite(place_id: str, name: str = "", private_server: str = "", universe_id: str = "") -> bool:
    # newest first, the same place and server is moved to the top instead of duplicated
    if not is_valid_place_id(place_id):
        return False
    place_id = str(place_id).strip()
    private_server = str(private_server or "").strip()
    with _LOCK:
        favorites = load_favorites()
        old = next((f for f in favorites if _same(f, place_id, private_server)), {})
        favorites = [f for f in favorites if not _same(f, place_id, private_server)]
        favorites.insert(0, {
            "place_id": place_id,
            "name": name or old.get("name") or place_id,
            "private_server": private_server,
            "universe_id": str(universe_id or old.get("universe_id") or ""),
        })
        save_favorites(favorites)
    return True


def update_favorite_details(place_id: str, private_server: str, name: str, universe_id: str) -> bool:
    # fills in the game name and universe looked up from roblox, keeps the order
    with _LOCK:
        favorites = load_favorites()
        changed = False
        for entry in favorites:
            if not _same(entry, place_id, private_server):
                continue
            if name and entry.get("name") != name:
                entry["name"] = name
                changed = True
            if universe_id and str(entry.get("universe_id", "")) != str(universe_id):
                entry["universe_id"] = str(universe_id)
                changed = True
        if changed:
            save_favorites(favorites)
    return changed


def remove_favorite(place_id: str, private_server: str = "") -> None:
    with _LOCK:
        favorites = [f for f in load_favorites() if not _same(f, place_id, private_server)]
        save_favorites(favorites)
