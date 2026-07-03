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
import autoit
import psutil
import platform
import tempfile
import shutil
import zipfile
import subprocess
import re
import win32event
import win32api
import msvcrt
import requests
from urllib.request import urlretrieve
from ctypes import wintypes


from typing import Callable, Optional
from classes.roblox_api import RobloxAPI
from classes.encryption import EncryptionConfig
import features.auto_rejoin as ar

# Paths
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RECENT_GAMES_FILE = os.path.join(_ROOT_DIR, "AccountManagerData", "recent_games.json")
_SETTINGS_FILE = os.path.join(_ROOT_DIR, "AccountManagerData", "ui_settings.json")

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


def save_recent_game(place_id: str, name: str) -> None:
    if not place_id:
        return
    games = load_recent_games()
    games = [g for g in games if str(g.get("place_id")) != str(place_id)]
    games.insert(0, {"place_id": place_id, "name": name})
    games = games[:20]
    os.makedirs(os.path.dirname(_RECENT_GAMES_FILE), exist_ok=True)
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
    os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
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
            ok = manager.launch_roblox(username)
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
    print(f"[INFO] join_player: {username} -> join {target_username}")
    def _worker():
        try:
            presence = RobloxAPI.get_player_presence(target_username)
            if not presence:
                msg = f"Could not find {target_username}'s presence."
                print(f"[WARNING] join_player: {msg}")
                on_done(False, msg)
                return
            place_id = str(presence.get("placeId", "") or "")
            game_id  = str(presence.get("gameId",  "") or "")
            if not place_id:
                msg = f"{target_username} is not in a game."
                print(f"[WARNING] join_player: {msg}")
                on_done(False, msg)
                return
            S = load_ui_settings()
            launcher = S.get("roblox_launcher", "default")
            custom_path = S.get("custom_roblox_launcher_path", "")
            ok = manager.launch_roblox(
                username, place_id,
                job_id=game_id,
                launcher_preference=launcher,
                custom_launcher_path=custom_path,
            )
            msg = "" if ok else f"Could not join {target_username}'s server."
            print(f"[{'SUCCESS' if ok else 'ERROR'}] join_player {username}: {'OK' if ok else 'FAIL'}")
            on_done(ok, msg)
        except Exception as e:
            print(f"[ERROR] join_player exception: {e}")
            on_done(False, str(e))

    threading.Thread(target=_worker, daemon=True, name=f"joinplayer-{username}").start()


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
        cfg = EncryptionConfig.load()
        if cfg and cfg.is_encrypted:
            return "Encrypted", "#4CAF50"
        return "Not Encrypted", "#EF5350"
    except Exception:
        return "", ""


# Additional launch/join actions
def launch_home(manager, username: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    def _worker():
        try:
            ok = manager.launch_roblox(username)
            on_done(ok, "" if ok else "Failed to launch Roblox.")
        except Exception as e:
            on_done(False, str(e))
    threading.Thread(target=_worker, daemon=True).start()


def join_user(manager, username: str, target_username: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    join_player(manager, username, target_username, on_done=on_done)


def join_job_id(manager, username: str, place_id: str, job_id: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    S = load_ui_settings()
    launcher = S.get("roblox_launcher", "default")
    custom_path = S.get("custom_roblox_launcher_path", "")
    print(f"[INFO] join_job_id: {username} -> place {place_id} job {job_id}")
    def _worker():
        try:
            ok = manager.launch_roblox(
                username, place_id,
                job_id=job_id,
                launcher_preference=launcher,
                custom_launcher_path=custom_path,
            )
            msg = "" if ok else "Failed to join by Job ID."
            print(f"[{'SUCCESS' if ok else 'ERROR'}] join_job_id {username}: {'OK' if ok else 'FAIL'}")
            on_done(ok, msg)
        except Exception as e:
            print(f"[ERROR] join_job_id {username}: {e}")
            on_done(False, str(e))
    threading.Thread(target=_worker, daemon=True, name=f"jobjoin-{username}").start()


def join_small_server(manager, username: str, place_id: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    print(f"[INFO] join_small_server: {username} -> place {place_id}")
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
            ok = manager.launch_roblox(
                username, place_id,
                job_id=job_id,
                launcher_preference=launcher,
                custom_launcher_path=custom_path,
            )
            msg = "" if ok else "Failed to join smallest server."
            print(f"[{'SUCCESS' if ok else 'ERROR'}] join_small_server {username}: {'OK' if ok else 'FAIL'}")
            on_done(ok, msg)
        except Exception as e:
            print(f"[ERROR] join_small_server {username}: {e}")
            on_done(False, str(e))
    threading.Thread(target=_worker, daemon=True, name=f"smalljoin-{username}").start()


def fetch_game_name_async(place_id: str, on_done: Callable[[str], None] = lambda _: None) -> None:
    def _worker():
        name = fetch_game_name(place_id)
        on_done(name)
    threading.Thread(target=_worker, daemon=True).start()


def import_cookie(manager, cookie: str, on_done: Callable[[bool, str], None] = lambda *_: None) -> None:
    add_account(manager, cookie, on_done=on_done)

def add_account_browser(manager, on_done: Callable[[bool, str], None] = lambda *_: None, javascript: str = "") -> None:
    def _worker():
        existing_before = set(manager.accounts.keys())
        try:
            ok = manager.add_account(javascript=javascript or "")
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

# Auto-rejoin
def start_auto_rejoin(config: dict, manager, on_status: Callable[[str, str], None] = lambda *_: None) -> None:
    ar.start(config, manager, on_status)

def stop_auto_rejoin(username: str) -> None:
    ar.stop(username)

def stop_all_auto_rejoin() -> None:
    ar.stop_all()

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
    import win32gui
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
        hwnds = []
        def _cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in pids:
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
            for hwnd in hwnds:
                if _afk_stop_event.is_set():
                    break

                window_spec = f"[HANDLE:0x{hwnd:08X}]"

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
    data_dir = os.path.join(_ROOT_DIR, "AccountManagerData")
    candidates = [
        os.path.join(data_dir, "handle64.exe"),
        os.path.join(_ROOT_DIR, "handle64.exe"),
        os.path.join(_ROOT_DIR, "handle", "handle64.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def download_handle64() -> bool:
    
    try:
        
        url = "https://download.sysinternals.com/files/Handle.zip"
        exe_name = "handle64.exe" if platform.architecture()[0] == "64bit" else "handle.exe"
        data_dir = os.path.join(_ROOT_DIR, "AccountManagerData")
        os.makedirs(data_dir, exist_ok=True)
        dest = os.path.join(data_dir, "handle64.exe")
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "Handle.zip")
            urlretrieve(url, zip_path)
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
                    stdin=subprocess.DEVNULL, text=True, shell=True
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
                    stdin=subprocess.DEVNULL, shell=True
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

    try:
        mutex = win32event.CreateMutex(None, True, "ROBLOX_singletonEvent")
        if win32api.GetLastError() == 183:
            print("[Multi Roblox] Mutex already existed — took ownership.")
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
            try:
                win32event.ReleaseMutex(m)
                win32api.CloseHandle(m)
                print("[Multi Roblox] Mutex released.")
            except Exception as e:
                print(f"[Multi Roblox] Failed to release mutex: {e}")

        _mr_handle = None
        print("[Multi Roblox] Stopped.")
