"""
features/account_actions.py
Logic for all account related actions
"""

from __future__ import annotations

import json
import os
import threading
import time
import ctypes
import re
import autoit
import platform
import tempfile
import shutil
import zipfile
import subprocess
import win32gui
import msvcrt
import requests
from urllib.request import urlretrieve
from ctypes import wintypes


from typing import Callable
from classes.operation_result import OperationResult, ensure_result, unexpected_result
from classes.roblox_api import RobloxAPI
import features.browsers as browsers_mod
import features.headless_manager as headless_manager_mod
import features.presence as presence_mod
import features.settings_store as settings_store_mod
from utils.app_paths import get_app_dir, get_data_dir

# Paths
_DATA_DIR = get_data_dir()
_RECENT_GAMES_FILE = os.path.join(_DATA_DIR, "recent_games.json")

# Recent games
def load_recent_games() -> list[dict]:
    try:
        if os.path.exists(_RECENT_GAMES_FILE):
            with open(_RECENT_GAMES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def save_recent_game(place_id: str, name: str, private_server: str = "") -> None:
    if not place_id:
        return
    games = load_recent_games()
    games = [
        g for g in games
        if not (str(g.get("place_id")) == str(place_id)
                and str(g.get("private_server", "")) == str(private_server))
    ]
    games.insert(0, {
        "place_id": place_id,
        "name": name,
        "private_server": private_server,
        "private": bool(private_server),
    })
    games = games[:20]
    os.makedirs(_DATA_DIR, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(
        prefix=".recent_games.", suffix=".tmp", dir=_DATA_DIR
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            json.dump(games, f, indent=2)
        os.replace(temp_path, _RECENT_GAMES_FILE)
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

# UI settings persistence

def load_ui_settings() -> dict:
    return settings_store_mod.load()


def get_ui_setting(key: str, default=None):
    return settings_store_mod.get(key, default)


def save_ui_setting(key: str, value) -> None:
    settings_store_mod.save(key, value)


# Game name lookup
def fetch_game_name(place_id: str) -> str:
    try:
        name = RobloxAPI.get_game_name(str(place_id))
        if name:
            return name
    except Exception as e:
        print(f"[ERROR] Failed to fetch game name for place {place_id}: {e}")
    return ""


# Launch / join
def _batch_launch_result(
    action: str,
    total: int,
    success_count: int,
    failures: list[tuple[str, OperationResult]],
) -> OperationResult:
    summary = f"{action} {success_count}/{total} accounts."
    if not failures:
        return OperationResult.success(summary)

    detail = "\n".join(
        f"{username}: {result.code} - {result.message}"
        for username, result in failures
    )
    if success_count:
        return OperationResult.failure(
            "PARTIAL_LAUNCH_FAILURE",
            "Some Accounts Failed to Launch",
            summary,
            detail=detail,
        )

    first_result = failures[0][1]
    return OperationResult.failure(
        first_result.code or "ROBLOX_LAUNCH_FAILED",
        first_result.title or "Roblox Could Not Start",
        first_result.message or "Roblox could not be launched.",
        detail=detail,
        retryable=first_result.retryable,
    )


def join_place(manager, username: str, place_id: str, private_server_key: str = "", on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    print(f"[INFO] join_place: {username} -> place {place_id} (launcher={launcher}, ps={bool(private_server_key)})")
    def _worker():
        try:
            result = ensure_result(manager.launch_roblox(
                username, place_id,
                private_server_id=private_server_key or "",
                launcher_preference=launcher,
                custom_launcher_path=custom_path,
            ))
            print(f"[{'SUCCESS' if result else 'ERROR'}] join_place {username}: {'OK' if result else 'FAIL'}")
            on_done(bool(result), result)
        except Exception as exc:
            print(f"[ERROR] join_place exception for {username}: {exc}")
            result = unexpected_result(f"Joining place for {username}", exc)
            on_done(False, result)

    threading.Thread(target=_worker, daemon=True, name=f"join-{username}").start()


def join_place_all(manager, usernames: list[str], place_id: str, private_server_key: str = "", on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    print(f"[INFO] join_place_all: {len(usernames)} accounts -> place {place_id}")
    def _worker():
        success = 0
        failures: list[tuple[str, OperationResult]] = []
        for u in usernames:
            try:
                result = ensure_result(manager.launch_roblox(
                    u, place_id,
                    private_server_id=private_server_key or "",
                    launcher_preference=launcher,
                    custom_launcher_path=custom_path,
                ))
                if result:
                    success += 1
                else:
                    failures.append((u, result))
                print(f"[{'SUCCESS' if result else 'ERROR'}] join_place_all {u}: {'OK' if result else 'FAIL'}")
                time.sleep(0.5)
            except Exception as exc:
                print(f"[ERROR] join_place_all {u}: {exc}")
                failures.append((u, unexpected_result(f"Joining place for {u}", exc)))
        result = _batch_launch_result(
            "Joined",
            len(usernames),
            success,
            failures,
        )
        print(f"[INFO] join_place_all done: {result.message}")
        on_done(bool(result), result)

    threading.Thread(target=_worker, daemon=True, name="join-all").start()


def join_vip_server(manager, username: str, vip_url: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    print(f"[INFO] join_vip_server: {username} -> {vip_url}")
    def _worker():
        try:
            result = ensure_result(manager.launch_roblox(
                username, "",
                private_server_id=vip_url,
                launcher_preference=launcher,
                custom_launcher_path=custom_path,
            ))
            print(f"[{'SUCCESS' if result else 'ERROR'}] join_vip_server {username}: {'OK' if result else 'FAIL'}")
            on_done(bool(result), result)
        except Exception as exc:
            print(f"[ERROR] join_vip_server {username}: {exc}")
            result = unexpected_result(f"Joining VIP server for {username}", exc)
            on_done(False, result)

    threading.Thread(target=_worker, daemon=True, name=f"vip-{username}").start()


def add_account(manager, cookie: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    def _worker():
        try:
            result = manager.import_cookie_account_result(cookie)
            if result:
                on_done(True, str(result.data or result.message))
            else:
                on_done(False, result)
        except Exception as exc:
            print(f"[ERROR] add_account: {exc}")
            on_done(False, unexpected_result("Importing cookie", exc))

    threading.Thread(target=_worker, daemon=True, name="add-account-cookie").start()


def _split_cookie_bundle(cookie_blob: str) -> list[str]:
    marker = "_|WARNING:-"
    if not cookie_blob:
        return []

    text = cookie_blob.strip().strip('"').strip("'")
    if marker not in text:
        return [text] if text else []

    parts: list[str] = []
    matches = list(re.finditer(re.escape(marker), text))
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        cookie = text[start:end].strip().strip('"').strip("'")
        if cookie.startswith(marker):
            parts.append(cookie)

    if parts:
        return parts

    return [text]


def remove_account(manager, username: str) -> tuple[bool, str]:
    try:
        ok = manager.delete_account(username)
        if ok:
            return True, ""
        return False, f"Account '{username}' not found"
    except Exception as e:
        return False, str(e)


def get_account_note(manager, username: str) -> str:
    try:
        return manager.get_account_note(username) or ""
    except Exception:
        return ""

def get_note(manager, username: str) -> str:
    return get_account_note(manager, username)

def set_account_note(manager, username: str, note: str) -> None:
    try:
        manager.set_account_note(username, note)
    except Exception:
        pass


def set_note(manager, username: str, note: str) -> None:
    set_account_note(manager, username, note)

# Encryption status badge
def get_encryption_status(manager) -> tuple[str, str]:
    try:
        if manager.encryption_config.is_encryption_enabled():
            method = manager.encryption_config.get_encryption_method()
            if method == "hardware":
                return "[HARDWARE ENCRYPTED]", "#90EE90"
            elif method == "password":
                return "[PASSWORD ENCRYPTED]", "#87CEEB"
        return "[NOT ENCRYPTED]", "#FFB6C1"
    except Exception:
        return "", ""


# Additional launch/join actions
def launch_home(manager, username: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    def _worker():
        try:
            result = ensure_result(
                manager.launch_roblox(
                    username,
                    "",
                    "",
                    launcher_preference=launcher,
                    custom_launcher_path=custom_path,
                ),
                failure_code="ROBLOX_LAUNCH_FAILED",
                failure_title="Roblox Could Not Start",
                failure_message="Roblox could not be launched.",
            )
            on_done(bool(result), result)
        except Exception as exc:
            result = unexpected_result(f"Launching Roblox Home for {username}", exc)
            on_done(False, result)
    threading.Thread(target=_worker, daemon=True).start()
# username joining
def join_user(manager, usernames: list[str] | str, target_username: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    if isinstance(usernames, str):
        usernames = [usernames]
    print(f"[INFO] join_user: {len(usernames)} accounts -> join {target_username}")

    def _worker():
        try:
            target_user_id = RobloxAPI.get_user_id_from_username(target_username)
            if not target_user_id:
                msg = f"Could not find user ID for '{target_username}'."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, OperationResult.failure(
                    "TARGET_USER_NOT_FOUND",
                    "Roblox User Not Found",
                    msg,
                ))
                return

            first_acc_data = manager.accounts.get(usernames[0], {})
            cookie = first_acc_data.get("cookie", "")
            if not cookie:
                msg = f"No cookie found for account {usernames[0]} to check presence."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, OperationResult.failure(
                    "COOKIE_MISSING",
                    "Account Cookie Missing",
                    msg,
                ))
                return

            presence = RobloxAPI.get_player_presence(target_user_id, cookie)
            if not presence:
                msg = f"Could not fetch presence data for {target_username}."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, OperationResult.failure(
                    "PRESENCE_REQUEST_FAILED",
                    "Presence Could Not Be Checked",
                    msg,
                    retryable=True,
                ))
                return

            if not presence.get("in_game", False):
                msg = f"{target_username} is not in a game."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, OperationResult.failure(
                    "TARGET_NOT_IN_GAME",
                    "User Is Not In Game",
                    msg,
                ))
                return

            place_id = str(presence.get("place_id", "") or "")
            game_id  = str(presence.get("game_id",  "") or "")

            if not place_id:
                msg = f"{target_username} is in a game, but their Place ID is hidden."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, OperationResult.failure(
                    "TARGET_PLACE_HIDDEN",
                    "Place ID Is Hidden",
                    msg,
                ))
                return

            S = load_ui_settings()
            launcher = S.get("roblox_launcher", "default")
            custom_path = S.get("custom_roblox_launcher_path", "")

            success = 0
            failures: list[tuple[str, OperationResult]] = []
            for u in usernames:
                try:
                    result = ensure_result(manager.launch_roblox(
                        u, place_id,
                        job_id=game_id,
                        launcher_preference=launcher,
                        custom_launcher_path=custom_path,
                    ))
                    if result:
                        success += 1
                    else:
                        failures.append((u, result))
                    print(f"[{'SUCCESS' if result else 'ERROR'}] join_user {u}: {'OK' if result else 'FAIL'}")
                    time.sleep(0.5)
                except Exception as exc:
                    print(f"[ERROR] join_user {u}: {exc}")
                    failures.append((u, unexpected_result(f"Joining user with {u}", exc)))

            result = _batch_launch_result(
                "Joined",
                len(usernames),
                success,
                failures,
            )
            print(f"[INFO] join_user done: {result.message}")
            on_done(bool(result), result)
        except Exception as exc:
            print(f"[ERROR] join_user exception: {exc}")
            result = unexpected_result("Joining Roblox user", exc)
            on_done(False, result)

    threading.Thread(target=_worker, daemon=True, name="joinplayer-all").start()
# jobid joining
def join_job_id(manager, usernames: list[str] | str, place_id: str, job_id: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    if isinstance(usernames, str):
        usernames = [usernames]

    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    print(f"[INFO] join_job_id: {len(usernames)} accounts -> place {place_id} job {job_id}")

    def _worker():
        success = 0
        failures: list[tuple[str, OperationResult]] = []
        for u in usernames:
            try:
                result = ensure_result(manager.launch_roblox(
                    u, place_id,
                    job_id=job_id,
                    launcher_preference=launcher,
                    custom_launcher_path=custom_path,
                ))
                if result:
                    success += 1
                else:
                    failures.append((u, result))
                print(f"[{'SUCCESS' if result else 'ERROR'}] join_job_id {u}: {'OK' if result else 'FAIL'}")
                time.sleep(0.5)
            except Exception as exc:
                print(f"[ERROR] join_job_id {u}: {exc}")
                failures.append((u, unexpected_result(f"Joining Job ID with {u}", exc)))
        result = _batch_launch_result(
            "Joined",
            len(usernames),
            success,
            failures,
        )
        print(f"[INFO] join_job_id done: {result.message}")
        on_done(bool(result), result)

    threading.Thread(target=_worker, daemon=True, name="jobjoin-all").start()
# small server joining
def join_small_server(manager, usernames: list[str] | str, place_id: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    if isinstance(usernames, str):
        usernames = [usernames]

    print(f"[INFO] join_small_server: {len(usernames)} accounts -> place {place_id}")

    def _worker():
        try:
            servers_url = (
                f"https://games.roblox.com/v1/games/{place_id}/servers/Public"
                "?sortOrder=Asc&limit=100"
            )
            resp = requests.get(servers_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            servers = data.get("data", [])
            joinable = [s for s in servers if s.get("playing", 0) < s.get("maxPlayers", 1)]
            if not joinable:
                print(f"[WARNING] join_small_server: No joinable servers found for place {place_id}")
                on_done(False, OperationResult.failure(
                    "NO_JOINABLE_SERVER",
                    "No Available Server",
                    "No joinable public server was found for this game.",
                    retryable=True,
                ))
                return

            smallest = min(joinable, key=lambda s: s.get("playing", 999))
            job_id = smallest.get("id", "")
            print(f"[INFO] join_small_server: Joining server {job_id} ({smallest.get('playing')}/{smallest.get('maxPlayers')} players)")

            S = load_ui_settings()
            launcher = S.get("roblox_launcher", "default")
            custom_path = S.get("custom_roblox_launcher_path", "")

            success = 0
            failures: list[tuple[str, OperationResult]] = []
            for u in usernames:
                try:
                    result = ensure_result(manager.launch_roblox(
                        u, place_id,
                        job_id=job_id,
                        launcher_preference=launcher,
                        custom_launcher_path=custom_path,
                    ))
                    if result:
                        success += 1
                    else:
                        failures.append((u, result))
                    print(f"[{'SUCCESS' if result else 'ERROR'}] join_small_server {u}: {'OK' if result else 'FAIL'}")
                    time.sleep(0.5)
                except Exception as exc:
                    print(f"[ERROR] join_small_server {u}: {exc}")
                    failures.append((u, unexpected_result(f"Joining small server with {u}", exc)))

            result = _batch_launch_result(
                "Joined",
                len(usernames),
                success,
                failures,
            )
            print(f"[INFO] join_small_server done: {result.message}")
            on_done(bool(result), result)
        except requests.Timeout as exc:
            result = OperationResult.failure(
                "SERVER_LIST_TIMEOUT",
                "Server List Timed Out",
                "Roblox did not return the server list in time.",
                detail=str(exc),
                retryable=True,
            )
            on_done(False, result)
        except requests.RequestException as exc:
            result = OperationResult.failure(
                "SERVER_LIST_FAILED",
                "Server List Could Not Be Loaded",
                "Roblox could not return the public server list.",
                detail=f"{type(exc).__name__}: {exc}",
                retryable=True,
            )
            on_done(False, result)
        except Exception as exc:
            print(f"[ERROR] join_small_server: {exc}")
            result = unexpected_result("Finding a small server", exc)
            on_done(False, result)

    threading.Thread(target=_worker, daemon=True, name="smalljoin-all").start()

def fetch_game_name_async(place_id: str, on_done: Callable[[str], None] = lambda _: None) -> None:
    def _worker():
        name = fetch_game_name(place_id)
        on_done(name)
    threading.Thread(target=_worker, daemon=True).start()


def import_cookie(manager, cookie: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    cookies = _split_cookie_bundle(cookie)
    if not cookies:
        on_done(False, "No cookie data provided.")
        return

    if len(cookies) == 1:
        add_account(manager, cookies[0], on_done=on_done)
        return

    def _worker():
        success_count = 0
        imported_users: list[str] = []
        failure_results: list[OperationResult] = []

        for cookie_value in cookies:
            result = manager.import_cookie_account_result(cookie_value, save=False)
            if result:
                success_count += 1
                imported_users.append(str(result.data))
            else:
                failure_results.append(result)

        if success_count:
            manager.save_accounts()

        if success_count:
            summary = f"Imported {success_count}/{len(cookies)} account(s)."
            if imported_users:
                summary += " " + ", ".join(imported_users)
            on_done(True, summary)
        else:
            result = failure_results[0] if failure_results else OperationResult.failure(
                "COOKIE_IMPORT_FAILED",
                "Cookie Import Failed",
                f"Failed to import {len(cookies)} cookie(s).",
            )
            on_done(False, result)

    threading.Thread(target=_worker, daemon=True, name="add-account-cookie-batch").start()


def parse_user_pass_file(path: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                username, password = line.split(":", 1)
                username = username.strip()
                password = password.strip()
                if username and password:
                    pairs.append((username, password))
    except Exception as e:
        print(f"[ERROR] Failed to read User:Pass file: {e}")
    return pairs


def _build_login_script(username: str, password: str) -> str:
    return f"""
    (function() {{
        function setNativeValue(el, value) {{
            var proto = Object.getPrototypeOf(el);
            var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(el, value);
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        function tryFill(attemptsLeft) {{
            var userEl = document.getElementById('login-username');
            var passEl = document.getElementById('login-password');
            var btn = document.getElementById('login-button');
            if (userEl && passEl && btn) {{
                setNativeValue(userEl, {json.dumps(username)});
                setNativeValue(passEl, {json.dumps(password)});
                setTimeout(function() {{ btn.click(); }}, 300);
                return;
            }}
            if (attemptsLeft > 0) {{
                setTimeout(function() {{ tryFill(attemptsLeft - 1); }}, 250);
            }}
        }}
        tryFill(20);
    }})();
    """

IMPORT_BATCH_SIZE = 5

def import_user_pass(manager, pairs: list[tuple[str, str]], on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    if not pairs:
        on_done(False, "No username:password pairs provided.")
        return

    browser_result = get_browser_result()
    if not browser_result:
        on_done(False, browser_result)
        return
    browser = browser_result.data.get("browser")

    def _worker():
        success_count = 0
        imported_users: list[str] = []
        failures: list[OperationResult] = []

        for start in range(0, len(pairs), IMPORT_BATCH_SIZE):
            batch = pairs[start:start + IMPORT_BATCH_SIZE]
            existing_before = set(manager.accounts.keys())
            try:
                scripts = [_build_login_script(username, password) for username, password in batch]
                add_result = ensure_result(manager.add_account(
                    amount=len(batch),
                    javascript_list=scripts,
                    browser=browser,
                ))
                new_names = set(manager.accounts.keys()) - existing_before
                if new_names:
                    success_count += len(new_names)
                    imported_users.extend(str(name) for name in new_names)
                else:
                    print(f"[ERROR] import_user_pass: batch at {start} failed for all {len(batch)} account(s)")
                    failures.append(add_result)
            except Exception as exc:
                print(f"[ERROR] import_user_pass: batch at {start}: {exc}")
                failures.append(unexpected_result("Importing User:Pass batch", exc))

        if success_count:
            summary = f"Imported {success_count}/{len(pairs)} account(s)."
            if imported_users:
                summary += " " + ", ".join(imported_users)
            on_done(True, summary)
        else:
            result = failures[0] if failures else OperationResult.failure(
                "USER_PASS_IMPORT_FAILED",
                "User:Pass Import Failed",
                f"Failed to import {len(pairs)} account(s).",
            )
            on_done(False, result)

    threading.Thread(target=_worker, daemon=True, name="import-user-pass").start()


def get_browser_result() -> OperationResult:
    S = load_ui_settings()
    browser_type = S.get("browser_type", "chrome")
    return browsers_mod.resolve_browser(browser_type)


def add_account_browser(manager, on_done: Callable[[bool, str], None] = lambda *_: None, javascript: str = "") -> None:
    browser_result = get_browser_result()
    if not browser_result:
        on_done(False, browser_result)
        return
    browser = browser_result.data.get("browser")

    def _worker():
        existing_before = set(manager.accounts.keys())
        try:
            result = ensure_result(manager.add_account(
                javascript=javascript or "",
                browser=browser,
            ))
            if result:
                new_names = set(manager.accounts.keys()) - existing_before
                username = next(iter(new_names)) if new_names else "(unknown)"
                on_done(True, str(username))
            else:
                on_done(False, result)
        except Exception as exc:
            print(f"[ERROR] add_account_browser: {exc}")
            on_done(False, unexpected_result("Adding account through browser", exc))
    threading.Thread(target=_worker, daemon=True, name="add-account-browser").start()

# Anti-AFK
_afk_thread: threading.Thread | None = None
_afk_stop_event = threading.Event()
_afk_key: str = "w"
_afk_press_count: int = 1
_afk_interval: int = 10          # minutes
_afk_tooltip_enabled: bool = True

_afk_tooltip_callback: Callable[[str | None, int, int], None] | None = None

def set_afk_tooltip_callback(cb: Callable[[str | None, int, int], None]) -> None:
    global _afk_tooltip_callback
    _afk_tooltip_callback = cb

def _update_afk_tooltip(message: str | None) -> None:
    if not _afk_tooltip_enabled:
        return
    if _afk_tooltip_callback:
        try:
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            _afk_tooltip_callback(message, pt.x, pt.y)
        except Exception:
            pass

def start_anti_afk(key: str = "w", press_count: int = 1, interval: int = 10,
                   tooltip_enabled: bool = True) -> None:
    global _afk_thread, _afk_key, _afk_press_count, _afk_interval, _afk_tooltip_enabled
    _afk_key = key
    _afk_press_count = press_count
    _afk_interval = interval
    _afk_tooltip_enabled = tooltip_enabled
    stop_anti_afk()
    _afk_stop_event.clear()
    _afk_thread = threading.Thread(target=_afk_worker, daemon=True)
    _afk_thread.start()
    print("[Anti-AFK] Started")


def stop_anti_afk() -> None:
    global _afk_thread
    if _afk_thread and _afk_thread.is_alive():
        _afk_stop_event.set()
        _afk_thread.join(timeout=2)
        print("[Anti-AFK] Stopped")
    _afk_thread = None


def _afk_worker():
    user32 = ctypes.windll.user32

    def _get_roblox_pids():
        return set(presence_mod.get_roblox_processes())

    def _get_roblox_hwnds(pids):
        hm = headless_manager_mod.get_active_manager()
        headless_pids = hm.get_hidden_pids() if hm else set()

        hwnds = []
        windows_by_pid = presence_mod.get_windows_by_pid(set(pids))
        for pid, windows in windows_by_pid.items():
            for hwnd in windows:
                if user32.IsWindowVisible(hwnd):
                    hwnds.append(hwnd)
                    continue
                if pid not in headless_pids:
                    continue
                expected_titles = {"Roblox"}
                username = hm.get_pid_username(pid) if hm else None
                if username:
                    expected_titles.add(username)
                if win32gui.GetWindowText(hwnd) in expected_titles:
                    hwnds.append(hwnd)
        return hwnds

    def _get_placement(hwnd):
        if win32gui and win32gui.IsWindow(hwnd):
            try:
                return win32gui.GetWindowPlacement(hwnd)
            except Exception:
                pass
        return None

    def _restore_placement(hwnd, placement):
        if placement and win32gui and win32gui.IsWindow(hwnd):
            try:
                win32gui.SetWindowPlacement(hwnd, placement)
            except Exception:
                pass

    def _activate(hwnd):
        window_spec = f"[HANDLE:0x{hwnd:08X}]"
        try:
            autoit.win_activate(window_spec)
        except Exception:
            try:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

    def _perform_action(action_key, press_count):
        mouse_actions = {"lmb": "left", "rmb": "right", "mmb": "middle"}
        for _ in range(max(1, press_count)):
            if _afk_stop_event.is_set():
                break
            if action_key in mouse_actions:
                autoit.mouse_down(mouse_actions[action_key])
                time.sleep(0.1)
                autoit.mouse_up(mouse_actions[action_key])
            elif action_key == "scroll_up":
                autoit.mouse_wheel("up", 1)
            elif action_key == "scroll_down":
                autoit.mouse_wheel("down", 1)
            else:
                autoit.send(f"{{{action_key.upper()} down}}")
                time.sleep(0.1)
                autoit.send(f"{{{action_key.upper()} up}}")
            time.sleep(0.1)

    while not _afk_stop_event.is_set(): # main loop
        try:
            total_seconds = _afk_interval * 60
            countdown_seconds = min(30, total_seconds)
            wait_seconds = max(0, total_seconds - countdown_seconds)

            # Idle wait
            if wait_seconds > 0 and _afk_stop_event.wait(wait_seconds):
                break

            # Countdown + tooltip
            for remaining in range(countdown_seconds, 0, -1):
                if _afk_stop_event.is_set():
                    _update_afk_tooltip(None)
                    return
                msg = f"Anti-AFK Maintenance in {remaining}s"
                _update_afk_tooltip(msg)
                if _afk_stop_event.wait(1):
                    _update_afk_tooltip(None)
                    return

            _update_afk_tooltip(None)

            roblox_pids = _get_roblox_pids()
            if not roblox_pids:
                print("[Anti-AFK] No Roblox processes found")
                continue

            hwnds = _get_roblox_hwnds(roblox_pids)
            if not hwnds:
                print("[Anti-AFK] No Roblox windows found")
                continue

            # Save foreground window + its placement
            try:
                original_hwnd = user32.GetForegroundWindow()
            except Exception:
                original_hwnd = None
            original_placement = _get_placement(original_hwnd) if original_hwnd else None

            # Visit each Roblox window
            hm = headless_manager_mod.get_active_manager()
            for hwnd in hwnds:
                if _afk_stop_event.is_set():
                    break

                window_spec = f"[HANDLE:0x{hwnd:08X}]"

                hwnd_pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(hwnd_pid))
                was_headless_hidden = hm.pause_hidden(hwnd_pid.value) if hm else False

                window_placement = _get_placement(hwnd)

                _activate(hwnd)
                time.sleep(0.12)

                try:
                    autoit.win_maximize(window_spec)
                except Exception:
                    try:
                        if win32gui:
                            win32gui.ShowWindow(hwnd, 3)
                        else:
                            user32.ShowWindow(hwnd, 3)
                    except Exception:
                        pass

                try:
                    autoit.win_activate(window_spec)
                except Exception:
                    pass

                time.sleep(0.12)

                _perform_action(_afk_key, _afk_press_count)
                time.sleep(0.08)

                _restore_placement(hwnd, window_placement)

                try:
                    autoit.win_activate(window_spec)
                except Exception:
                    try:
                        if window_placement and len(window_placement) > 1 and window_placement[1] == 3:
                            if win32gui:
                                win32gui.ShowWindow(hwnd, 3)
                            else:
                                user32.ShowWindow(hwnd, 3)
                        else:
                            user32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass

                if was_headless_hidden and hm:
                    hm.resume_hidden(hwnd_pid.value)

                print(f"[Anti-AFK] Sent key to window 0x{hwnd:08X}")

            # Restore original foreground window + its placement
            if original_hwnd and (win32gui.IsWindow(original_hwnd) if win32gui else True):
                window_spec = f"[HANDLE:0x{original_hwnd:08X}]"
                _restore_placement(original_hwnd, original_placement)
                try:
                    autoit.win_activate(window_spec)
                except Exception:
                    try:
                        user32.SetForegroundWindow(original_hwnd)
                    except Exception:
                        pass

        except Exception as exc:
            print(f"[Anti-AFK] Error: {exc}")
            time.sleep(5)


# Multi Roblox
_mr_handle: dict | None = None # {'mutex': handle|None, 'file': file|None}
_mr_h64_monitoring = False
_mr_h64_thread: threading.Thread | None = None
_mr_h64_path: str | None = None


def find_handle64() -> str | None:
    data_dir = _DATA_DIR
    app_dir = get_app_dir()
    candidates = [
        os.path.join(data_dir, "handle64.exe"),
        os.path.join(app_dir, "handle64.exe"),
        os.path.join(app_dir, "handle", "handle64.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def download_handle64() -> bool:
    
    try:
        
        url = "https://download.sysinternals.com/files/Handle.zip"
        exe_name = "handle64.exe" if platform.architecture()[0] == "64bit" else "handle.exe"
        data_dir = _DATA_DIR
        os.makedirs(data_dir, exist_ok=True)
        dest = os.path.join(data_dir, "handle64.exe")
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "Handle.zip")
            urlretrieve(url, zip_path)  # nosec B310
            with zipfile.ZipFile(zip_path) as z:
                z.extract(exe_name, tmp)
                shutil.move(os.path.join(tmp, exe_name), dest)
        print(f"[Multi Roblox] handle64.exe downloaded to {dest}")
        return True
    except Exception as e:
        print(f"[Multi Roblox] Download failed: {e}")
        return False


def _mr_h64_monitor_worker():
    completed: set[tuple[int, float]] = set()
    in_flight: set[tuple[int, float]] = set()
    state_lock = threading.Lock()

    def close_pending_handles(processes: list[tuple[int, float]]):
        closed_pids = _mr_h64_close_handles([pid for pid, _ in processes])
        with state_lock:
            for identity in processes:
                in_flight.discard(identity)
                if identity[0] in closed_pids:
                    completed.add(identity)

    while _mr_h64_monitoring and _mr_h64_path:
        try:
            process_snapshot = presence_mod.get_roblox_processes(force=True)
            current = {
                (pid, process_data[0])
                for pid, process_data in process_snapshot.items()
            }
            with state_lock:
                completed.intersection_update(current)
                pending = current - completed - in_flight
                in_flight.update(pending)
            if pending:
                threading.Thread(
                    target=close_pending_handles,
                    args=(list(pending),),
                    daemon=True
                ).start()
            if not _mr_h64_monitoring:
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"[Multi Roblox] Handle64 monitor error: {e}")
            time.sleep(1.0)


def _mr_h64_close_handles(pids: list[int]) -> set[int]:
    HANDLE = _mr_h64_path
    if not HANDLE:
        return set()
    closed_pids: set[int] = set()
    for pid in pids:
        handle_value = None
        try:
            for _ in range(5):
                cmd = f'"{HANDLE}" -accepteula -p {pid} -a'
                proc = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, text=True, shell=True  # nosec B602
                )
                for line in proc.stdout.splitlines():
                    if "ROBLOX_singletonEvent" in line:
                        m = re.search(r"([0-9A-F]+):.*ROBLOX_singletonEvent", line, re.IGNORECASE)
                        if m:
                            handle_value = m.group(1)
                            break
                if handle_value:
                    break
                time.sleep(0.2)
            if handle_value:
                close_result = subprocess.run(
                    f'"{HANDLE}" -accepteula -p {pid} -c {handle_value} -y',
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, shell=True  # nosec B602
                )
                if close_result.returncode == 0:
                    closed_pids.add(pid)
                    print(f"[Multi Roblox] Closed singleton handle for PID:{pid}")
                else:
                    print(f"[Multi Roblox] Failed to close singleton handle for PID:{pid}")
            else:
                print(f"[Multi Roblox] Handle not found for PID:{pid}")
        except Exception as e:
            print(f"[Multi Roblox] Error closing handle for PID:{pid}: {e}")
    return closed_pids

def enable_multi_roblox(method: str = "default") -> tuple[bool, str]:
    # I know what you're here for.
    global _mr_handle, _mr_h64_monitoring, _mr_h64_thread, _mr_h64_path
    disable_multi_roblox() # clean up any existing state

    use_h64 = (method == "handle64")

    if use_h64:
        # Admin check
        try:
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            is_admin = False

        if not is_admin:
            print("[Multi Roblox] handle64 mode requires admin. Not running as admin.")
            return False, "NEEDS_ADMIN"

        h64 = find_handle64()
        if not h64:
            print("[Multi Roblox] handle64.exe not found. Download it first.")
            return False, "handle64.exe not found. Click 'Download Handle64' first."

        _mr_h64_path = h64
        _mr_h64_monitoring = True
        _mr_h64_thread = threading.Thread(target=_mr_h64_monitor_worker, daemon=True)
        _mr_h64_thread.start()
        _mr_handle = {"mutex": None, "file": None}
        print("[Multi Roblox] Started (handle64 mode)")
        return True, ""

    if is_roblox_running():
        print("[Multi Roblox] Roblox is already running, close it before enabling default mode.")
        return False, "ROBLOX_RUNNING"

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        mutex = kernel32.CreateMutexW(None, True, "ROBLOX_singletonEvent")
        if not mutex:
            print(f"[Multi Roblox] Failed to create mutex: {ctypes.get_last_error()}")
        elif ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            print("[Multi Roblox] Mutex already exists. Took ownership.")
        else:
            print("[Multi Roblox] Mutex created.")

    except Exception as e:
        return False, f"Failed to create mutex: {e}"

    cookie_file = None
    cookies_path = os.path.join(
        os.getenv("LOCALAPPDATA", ""),
        r"Roblox\LocalStorage\RobloxCookies.dat"
    )
    if os.path.exists(cookies_path):
        try:
            cookie_file = open(cookies_path, "r+b")
            msvcrt.locking(cookie_file.fileno(), msvcrt.LK_NBLCK, os.path.getsize(cookies_path))
            print("[Multi Roblox] Error 773 fix applied (cookie lock).")
        except OSError:
            print("[Multi Roblox] Could not lock RobloxCookies.dat (may already be locked).")
    else:
        print("[Multi Roblox] RobloxCookies.dat not found, 773 fix skipped.")

    _mr_handle = {"mutex": mutex, "file": cookie_file}
    print("[Multi Roblox] Started (default mode)")
    return True, ""

def is_roblox_running() -> bool:
    try:
        output = subprocess.check_output(["tasklist"], text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if "robloxplayerbeta.exe" in output.lower():
            return True
    except Exception as e:
        print(f"[Multi Roblox] Error checking if Roblox is running: {e}")
    return False

def kill_roblox():
    subprocess.run(
        ["taskkill", "/F", "/IM", "RobloxPlayerBeta.exe"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def disable_multi_roblox():
    global _mr_handle, _mr_h64_monitoring, _mr_h64_thread, _mr_h64_path

    if _mr_h64_monitoring:
        _mr_h64_monitoring = False
        if _mr_h64_thread:
            _mr_h64_thread.join(timeout=2.0)
        _mr_h64_thread = None
        _mr_h64_path = None
        print("[Multi Roblox] Handle64 monitor stopped.")

    if _mr_handle:
        f = _mr_handle.get("file")
        if f:
            try:
                cookies_path = os.path.join(
                    os.getenv("LOCALAPPDATA", ""),
                    r"Roblox\LocalStorage\RobloxCookies.dat"
                )
                if os.path.exists(cookies_path):
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, os.path.getsize(cookies_path))
            except Exception as e:
                print(f"[Multi Roblox] Failed to unlock cookie file: {e}")
            try:
                f.close()
            except Exception:
                pass

        m = _mr_handle.get("mutex")
        if m:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.ReleaseMutex.restype = wintypes.BOOL
            kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            try:
                if not kernel32.ReleaseMutex(m):
                    print(f"ReleaseMutex failed. Error: {ctypes.get_last_error()}")

                if not kernel32.CloseHandle(m):
                    print(f"CloseHandle failed. Error: {ctypes.get_last_error()}")

                print("[Multi Roblox] Mutex released.")

            except Exception as e:
                print(f"[Multi Roblox] Failed to release mutex: {e}")

        _mr_handle = None
        print("[Multi Roblox] Stopped.")
