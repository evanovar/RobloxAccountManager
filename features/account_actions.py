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
import psutil
import platform
import tempfile
import shutil
import zipfile
import subprocess
import re
import win32gui
import msvcrt
import requests
from urllib.request import urlretrieve
from ctypes import wintypes


from typing import Callable, Optional
from classes.roblox_api import RobloxAPI
import features.headless_manager as headless_manager_mod
from utils.app_paths import get_app_dir, get_data_dir

# Paths
_DATA_DIR = get_data_dir()
_RECENT_GAMES_FILE = os.path.join(_DATA_DIR, "recent_games.json")
_SETTINGS_FILE = os.path.join(_DATA_DIR, "ui_settings.json")
_CHROMIUM_DIR = os.path.join(_DATA_DIR, "Chromium", "chrome-win64")

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
    with open(_RECENT_GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(games, f, indent=2)

# UI settings persistence

def load_ui_settings() -> dict:
    try:
        if os.path.exists(_SETTINGS_FILE):
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_ui_setting(key: str, value) -> None:
    settings = load_ui_settings()
    settings[key] = value
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


# Game name lookup
def fetch_game_name(place_id: str) -> str:
    try:
        name = RobloxAPI.get_game_name(str(place_id))
        if name:
            # print(f"[SUCCESS] Game name for place {place_id}: {name}")
            return name
    except Exception as e:
        print(f"[ERROR] Failed to fetch game name for place {place_id}: {e}")
    return ""


# Account list helpers
def get_accounts(manager) -> list[dict]:
    try:
        result = []
        for username, data in manager.accounts.items():
            entry = dict(data) if isinstance(data, dict) else {}
            entry["username"] = username
            result.append(entry)
        return result
    except Exception:
        return []


def get_groups(manager) -> list[str]:
    try:
        groups: set[str] = set()
        for data in manager.accounts.values():
            g = data.get("group", "") if isinstance(data, dict) else ""
            if g:
                groups.add(g)
        return sorted(groups)
    except Exception:
        return []

# Avatar fetching
def fetch_avatar_image(username: str, on_done: Callable[[str, bytes | None], None]) -> None:
    def _worker():
        try:
            api = RobloxAPI()
            user_id = api.get_user_id(username)
            if user_id:
                img_bytes = api.get_avatar_thumbnail(user_id, size=48)
                on_done(username, img_bytes)
                return
        except Exception:
            pass
        on_done(username, None)

    threading.Thread(target=_worker, daemon=True).start()


# Launch / join
def launch_roblox_home(manager, username: str, on_done: Callable[[bool, str], None]) -> None:
    def _worker():
        try:
            ok = manager.launch_roblox(username, "", "")
            on_done(ok, "" if ok else "Failed to launch Roblox.")
        except Exception as e:
            on_done(False, str(e))

    threading.Thread(target=_worker, daemon=True).start()


def join_place(manager, username: str, place_id: str, private_server_key: str = "", on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    print(f"[INFO] join_place: {username} -> place {place_id} (launcher={launcher}, ps={bool(private_server_key)})")
    def _worker():
        try:
            ok = manager.launch_roblox(
                username, place_id,
                private_server_id=private_server_key or "",
                launcher_preference=launcher,
                custom_launcher_path=custom_path,
            )
            if not ok:
                if getattr(RobloxAPI, "_last_error", None) == "expired_cookie":
                    msg = "EXPIRED_COOKIE"
                    RobloxAPI._last_error = None
                else:
                    msg = "Failed to join. Check the console for details."
            else:
                msg = ""
            print(f"[{'SUCCESS' if ok else 'ERROR'}] join_place {username}: {'OK' if ok else 'FAIL'}")
            on_done(ok, msg)
        except Exception as e:
            print(f"[ERROR] join_place exception for {username}: {e}")
            on_done(False, str(e))

    threading.Thread(target=_worker, daemon=True, name=f"join-{username}").start()


def join_place_all(manager, usernames: list[str], place_id: str, private_server_key: str = "", on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    print(f"[INFO] join_place_all: {len(usernames)} accounts -> place {place_id}")
    def _worker():
        success = 0
        for u in usernames:
            try:
                ok = manager.launch_roblox(
                    u, place_id,
                    private_server_id=private_server_key or "",
                    launcher_preference=launcher,
                    custom_launcher_path=custom_path,
                )
                if ok:
                    success += 1
                print(f"[{'SUCCESS' if ok else 'ERROR'}] join_place_all {u}: {'OK' if ok else 'FAIL'}")
                time.sleep(0.5)
            except Exception as e:
                print(f"[ERROR] join_place_all {u}: {e}")
        msg = f"Joined {success}/{len(usernames)} accounts."
        print(f"[INFO] join_place_all done: {msg}")
        on_done(success > 0, msg)

    threading.Thread(target=_worker, daemon=True, name="join-all").start()


def join_vip_server(manager, username: str, vip_url: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    print(f"[INFO] join_vip_server: {username} -> {vip_url}")
    def _worker():
        try:
            ok = manager.launch_roblox(
                username, "",
                private_server_id=vip_url,
                launcher_preference=launcher,
                custom_launcher_path=custom_path,
            )
            msg = "" if ok else "Failed to join VIP server."
            print(f"[{'SUCCESS' if ok else 'ERROR'}] join_vip_server {username}: {'OK' if ok else 'FAIL'}")
            on_done(ok, msg)
        except Exception as e:
            print(f"[ERROR] join_vip_server {username}: {e}")
            on_done(False, str(e))

    threading.Thread(target=_worker, daemon=True, name=f"vip-{username}").start()


def join_player(manager, username: str, target_username: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    join_user(manager, username, target_username, on_done=on_done)


def add_account(manager, cookie: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    def _worker():
        try:
            ok, username = manager.import_cookie_account(cookie)
            if ok and username:
                on_done(True, str(username))
            else:
                on_done(False, "Failed to add account — invalid or expired cookie?")
        except Exception as e:
            print(f"[ERROR] add_account: {e}")
            on_done(False, str(e))

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
            ok = manager.launch_roblox(username, "",  "", launcher_preference=launcher, custom_launcher_path=custom_path)
            on_done(ok, "" if ok else "Failed to launch Roblox.")
        except Exception as e:
            on_done(False, str(e))
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
                on_done(False, msg)
                return

            first_acc_data = manager.accounts.get(usernames[0], {})
            cookie = first_acc_data.get("cookie", "")
            if not cookie:
                msg = f"No cookie found for account {usernames[0]} to check presence."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, msg)
                return

            presence = RobloxAPI.get_player_presence(target_user_id, cookie)
            if not presence:
                msg = f"Could not fetch presence data for {target_username}."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, msg)
                return

            if not presence.get("in_game", False):
                msg = f"{target_username} is not in a game."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, msg)
                return

            place_id = str(presence.get("place_id", "") or "")
            game_id  = str(presence.get("game_id",  "") or "")

            if not place_id:
                msg = f"{target_username} is in a game, but their Place ID is hidden."
                print(f"[WARNING] join_user: {msg}")
                on_done(False, msg)
                return

            S = load_ui_settings()
            launcher = S.get("roblox_launcher", "default")
            custom_path = S.get("custom_roblox_launcher_path", "")

            success = 0
            for u in usernames:
                try:
                    ok = manager.launch_roblox(
                        u, place_id,
                        job_id=game_id,
                        launcher_preference=launcher,
                        custom_launcher_path=custom_path,
                    )
                    if ok:
                        success += 1
                    print(f"[{'SUCCESS' if ok else 'ERROR'}] join_user {u}: {'OK' if ok else 'FAIL'}")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"[ERROR] join_user {u}: {e}")

            msg = f"Joined {success}/{len(usernames)} accounts."
            print(f"[INFO] join_user done: {msg}")
            on_done(success > 0, msg)
        except Exception as e:
            print(f"[ERROR] join_user exception: {e}")
            on_done(False, str(e))

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
        for u in usernames:
            try:
                ok = manager.launch_roblox(
                    u, place_id,
                    job_id=job_id,
                    launcher_preference=launcher,
                    custom_launcher_path=custom_path,
                )
                if ok:
                    success += 1
                print(f"[{'SUCCESS' if ok else 'ERROR'}] join_job_id {u}: {'OK' if ok else 'FAIL'}")
                time.sleep(0.5)
            except Exception as e:
                print(f"[ERROR] join_job_id {u}: {e}")
        msg = f"Joined {success}/{len(usernames)} accounts."
        print(f"[INFO] join_job_id done: {msg}")
        on_done(success > 0, msg)

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
                on_done(False, "No available servers found.")
                return

            smallest = min(joinable, key=lambda s: s.get("playing", 999))
            job_id = smallest.get("id", "")
            print(f"[INFO] join_small_server: Joining server {job_id} ({smallest.get('playing')}/{smallest.get('maxPlayers')} players)")

            S = load_ui_settings()
            launcher = S.get("roblox_launcher", "default")
            custom_path = S.get("custom_roblox_launcher_path", "")

            success = 0
            for u in usernames:
                try:
                    ok = manager.launch_roblox(
                        u, place_id,
                        job_id=job_id,
                        launcher_preference=launcher,
                        custom_launcher_path=custom_path,
                    )
                    if ok:
                        success += 1
                    print(f"[{'SUCCESS' if ok else 'ERROR'}] join_small_server {u}: {'OK' if ok else 'FAIL'}")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"[ERROR] join_small_server {u}: {e}")

            msg = f"Joined {success}/{len(usernames)} accounts."
            print(f"[INFO] join_small_server done: {msg}")
            on_done(success > 0, msg)
        except Exception as e:
            print(f"[ERROR] join_small_server: {e}")
            on_done(False, str(e))

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
        failures = 0

        for cookie_value in cookies:
            ok, username = manager.import_cookie_account(cookie_value)
            if ok and username:
                success_count += 1
                imported_users.append(str(username))
            else:
                failures += 1

        if success_count:
            summary = f"Imported {success_count}/{len(cookies)} account(s)."
            if imported_users:
                summary += " " + ", ".join(imported_users)
            on_done(True, summary)
        else:
            on_done(False, f"Failed to import {len(cookies)} cookie(s).")

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


def import_user_pass(manager, pairs: list[tuple[str, str]], on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    if not pairs:
        on_done(False, "No username:password pairs provided.")
        return

    browser_path = get_browser_path()

    def _worker():
        success_count = 0
        imported_users: list[str] = []

        for username, password in pairs:
            existing_before = set(manager.accounts.keys())
            try:
                script = _build_login_script(username, password)
                ok = manager.add_account(javascript=script, browser_path=browser_path)
                if ok:
                    new_names = set(manager.accounts.keys()) - existing_before
                    added = next(iter(new_names)) if new_names else username
                    success_count += 1
                    imported_users.append(str(added))
                else:
                    print(f"[ERROR] import_user_pass: login failed for {username}")
            except Exception as e:
                print(f"[ERROR] import_user_pass: {username}: {e}")

        if success_count:
            summary = f"Imported {success_count}/{len(pairs)} account(s)."
            if imported_users:
                summary += " " + ", ".join(imported_users)
            on_done(True, summary)
        else:
            on_done(False, f"Failed to import {len(pairs)} account(s).")

    threading.Thread(target=_worker, daemon=True, name="import-user-pass").start()


def get_browser_path() -> str | None:
    S = load_ui_settings()
    browser_type = S.get("browser_type", "chrome")
    
    if browser_type == "chromium":
        chromium_path = os.path.join(_CHROMIUM_DIR, "chrome.exe")
        if os.path.exists(chromium_path):
            return chromium_path
        browser_type = "chrome"
    
    if browser_type == "chrome":
        candidates = []
        pf = os.environ.get('ProgramFiles')
        pfx86 = os.environ.get('ProgramFiles(x86)')
        localapp = os.environ.get('LOCALAPPDATA')
        if pf:
            candidates.append(os.path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'))
        if pfx86:
            candidates.append(os.path.join(pfx86, 'Google', 'Chrome', 'Application', 'chrome.exe'))
        if localapp:
            candidates.append(os.path.join(localapp, 'Google', 'Chrome', 'Application', 'chrome.exe'))
        for path in candidates:
            if path and os.path.exists(path):
                return path
    
    return None

def add_account_browser(manager, on_done: Callable[[bool, str], None] = lambda *_: None, javascript: str = "") -> None:
    browser_path = get_browser_path()
    def _worker():
        existing_before = set(manager.accounts.keys())
        try:
            ok = manager.add_account(javascript=javascript or "", browser_path=browser_path)
            if ok:
                new_names = set(manager.accounts.keys()) - existing_before
                username = next(iter(new_names)) if new_names else "(unknown)"
                on_done(True, str(username))
            else:
                on_done(False, "Failed to add account via browser.")
        except Exception as e:
            print(f"[ERROR] add_account_browser: {e}")
            on_done(False, str(e))
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
        pids = set()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                    pids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return pids

    def _get_roblox_hwnds(pids):
        hm = headless_manager_mod.get_active_manager()
        headless_pids = hm.get_hidden_pids() if hm else set()

        hwnds = []
        def _cb(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in pids:
                return True
            if user32.IsWindowVisible(hwnd):
                hwnds.append(hwnd)
                return True
            if pid.value in headless_pids:
                expected_titles = {"Roblox"}
                username = hm.get_pid_username(pid.value) if hm else None
                if username:
                    expected_titles.add(username)
                if win32gui.GetWindowText(hwnd) in expected_titles:
                    hwnds.append(hwnd)
            return True
        EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumProc(_cb), 0)
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
                print(f"[Anti-AFK] {msg}")
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
    global _mr_h64_monitoring, _mr_h64_path
    
    target = "robloxplayerbeta.exe"
    known: set[int] = set()

    while _mr_h64_monitoring and _mr_h64_path:
        try:
            current: set[int] = set()
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if p.info["name"] and p.info["name"].lower() == target:
                        current.add(p.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            new = current - known
            if new:
                known |= new
                threading.Thread(
                    target=_mr_h64_close_handles,
                    args=(list(new),),
                    daemon=True
                ).start()
            known -= known - current
            time.sleep(0.4)
        except Exception as e:
            print(f"[Multi Roblox] Handle64 monitor error: {e}")
            time.sleep(1.0)


def _mr_h64_close_handles(pids: list[int]):
    global _mr_h64_path
    HANDLE = _mr_h64_path
    if not HANDLE:
        return
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
                time.sleep(1)
            if handle_value:
                subprocess.run(
                    f'"{HANDLE}" -accepteula -p {pid} -c {handle_value} -y',
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, shell=True  # nosec B602
                )
                print(f"[Multi Roblox] Closed singleton handle for PID:{pid}")
            else:
                print(f"[Multi Roblox] Handle not found for PID:{pid}")
        except Exception as e:
            print(f"[Multi Roblox] Error closing handle for PID:{pid}: {e}")

def enable_multi_roblox(method: str = "default") -> tuple[bool, str]:
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
        print("[Multi Roblox] RobloxCookies.dat not found — 773 fix skipped.")

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