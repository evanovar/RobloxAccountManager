"""Game search for the Games Selector."""

from __future__ import annotations

from dataclasses import dataclass, replace
from queue import Empty, Queue
import re
import threading
from urllib.parse import urlparse

import requests

from classes.operation_result import OperationResult

SEARCH_URL = "https://apis.roblox.com/search-api/omni-search"
DISCOVERY_URL = "https://apis.roblox.com/explore-api/v1/get-sorts"
THUMBNAILS_URL = "https://thumbnails.roblox.com/v1/games/icons"
PAGE_SIZE = 40
MAX_IMAGE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class Game:
    universe_id: str
    place_id: str
    title: str
    thumbnail_url: str = ""


def _id(value) -> str:
    text = str(value)
    return text if re.fullmatch(r"[0-9]{1,20}", text) and int(text) > 0 else ""


def _get_json(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=(5, 10))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload


def _with_icons(games):
    if not games:
        return games
    try:
        thumbnails = _get_json(THUMBNAILS_URL, {
            "universeIds": ",".join(game.universe_id for game in games),
            "size": "150x150", "format": "Png", "isCircular": "false",
        })
        urls = {str(entry.get("targetId")): entry.get("imageUrl") or ""
                for entry in thumbnails.get("data", []) if entry.get("state") == "Completed"}
        return [replace(game, thumbnail_url=urls.get(game.universe_id, "")) for game in games]
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return games


def search_games(query: str, session_id: str, page_token: str = "") -> OperationResult:
    query = query.strip()[:100]
    try:
        if query:
            params = {"searchQuery": query, "sessionId": session_id, "pageType": "all"}
            if page_token:
                params["pageToken"] = page_token
            payload = _get_json(SEARCH_URL, params)
            groups = payload["searchResults"]
            records = [record for group in groups if group.get("contentGroupType") == "Game"
                       for record in group.get("contents", [])]
            next_page = payload.get("nextPageToken") or ""
            if not isinstance(next_page, str):
                raise ValueError("Invalid search page token.")
        else:
            payload = _get_json(DISCOVERY_URL, {"sessionId": session_id})
            sorts = [sort for sort in payload["sorts"] if sort.get("contentType") == "Games"]
            popular = next((sort for sort in sorts if sort.get("sortId") == "top-playing-now"),
                           sorts[0] if sorts else {})
            records = popular.get("games", [])
            next_page = ""

        games, seen = [], set()
        for record in records:
            universe_id = _id(record.get("universeId"))
            place_id = _id(record.get("rootPlaceId"))
            title = record.get("name")
            if not universe_id or not place_id or not isinstance(title, str) or not title.strip():
                continue
            if universe_id not in seen:
                games.append(Game(universe_id, place_id, title.strip()))
                seen.add(universe_id)
            if query and len(games) == PAGE_SIZE:
                break

        remaining = [games[offset:offset + PAGE_SIZE] for offset in range(PAGE_SIZE, len(games), PAGE_SIZE)]
        return OperationResult.success(data={
            "games": _with_icons(games[:PAGE_SIZE]), "next_page_token": next_page,
            "remaining_pages": remaining,
        })
    except requests.HTTPError as exc:
        message = ("Roblox is limiting game searches. Wait a moment and try again."
                   if exc.response is not None and exc.response.status_code == 429
                   else "Could not load games from Roblox. Try searching again.")
    except requests.RequestException:
        message = "Could not connect to Roblox. Check your connection and try again."
    except (ValueError, KeyError, TypeError, AttributeError):
        message = "Roblox returned an unexpected game list. Try searching again."
    return OperationResult.failure("GAME_SEARCH_FAILED", "Games Selector", message, retryable=True)


def download_thumbnail(url: str, cancel: threading.Event) -> bytes | None:
    if cancel.is_set() or not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
    except ValueError:
        return None
    if parsed.scheme != "https" or not (host == "rbxcdn.com" or host.endswith(".rbxcdn.com")):
        return None
    try:
        with requests.get(url, timeout=(5, 10), stream=True, allow_redirects=False) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(64 * 1024):
                if cancel.is_set() or len(content) + len(chunk) > MAX_IMAGE_BYTES:
                    return None
                content.extend(chunk)
            return bytes(content) or None
    except requests.RequestException:
        return None


def _start_thumbnails(games, on_thumbnail, cancel):
    pending = Queue()
    for game in games:
        if game.thumbnail_url:
            pending.put(game)

    def load_images():
        while not cancel.is_set():
            try:
                game = pending.get_nowait()
            except Empty:
                return
            image = download_thumbnail(game.thumbnail_url, cancel)
            if image and not cancel.is_set():
                on_thumbnail(game.universe_id, image)

    for _ in range(min(4, pending.qsize())):
        threading.Thread(target=load_images, name="game-thumbnail", daemon=True).start()


def start_thumbnails(games, on_thumbnail) -> threading.Event:
    cancel = threading.Event()

    def work():
        missing = [game for game in games if not game.thumbnail_url]
        resolved = _with_icons(missing)
        if not cancel.is_set():
            _start_thumbnails([game for game in games if game.thumbnail_url] + resolved, on_thumbnail, cancel)

    threading.Thread(target=work, name="game-icons", daemon=True).start()
    return cancel


def start_load(query, session_id, page_token, on_done, on_thumbnail) -> threading.Event:
    cancel = threading.Event()

    def work():
        result = search_games(query, session_id, page_token)
        if cancel.is_set():
            return
        on_done(result)
        if not result:
            return

        _start_thumbnails(result.data["games"], on_thumbnail, cancel)

    threading.Thread(target=work, name="game-search", daemon=True).start()
    return cancel
