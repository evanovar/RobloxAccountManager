"""
features/auto_rejoin.py
Core logic for auto-rejoin purposes.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import random
import psutil
import requests
from typing import Callable, Optional
from classes.roblox_api import RobloxAPI

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_FILE = os.path.join(_ROOT_DIR, "AccountManagerData", "auto_rejoin.json")

def load_configs() -> dict:
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_configs(configs: dict) -> None:
    os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=2)
    except Exception:
        pass

def _has_internet(timeout: int = 3) -> bool:
    for url in ("https://www.google.com/generate_204",
                "https://www.cloudflare.com/cdn-cgi/trace"):
        try:
            if requests.get(url, timeout=timeout).status_code < 500:
                return True
        except Exception:
            pass
    return False


def _get_roblox_pids() -> set:
    try:
        pids = set()
        for p in psutil.process_iter(["pid", "name"]):
            if (p.info["name"] or "").lower() == "robloxplayerbeta.exe":
                pids.add(p.info["pid"])
        return pids
    except Exception:
        return set()


def _pid_alive(pid: int) -> bool:
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.name().lower() == "robloxplayerbeta.exe"
    except Exception:
        return False


def _kill_pid(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass

_presence_lock = threading.Lock()
_presence_next_time = 0.0

def _wait_presence_slot(stop_event: threading.Event, gap: float = 0.4) -> bool:
    global _presence_next_time
    while True:
        now = time.time()
        with _presence_lock:
            wait = _presence_next_time - now
            if wait <= 0:
                _presence_next_time = now + gap
                return True
        sleep = min(0.25, max(0.05, wait))
        if stop_event.wait(sleep):
            return False

class AutoRejoinWorker:
    def __init__(
        self,
        account:   str,
        config:    dict,
        manager,
        on_status: Callable[[str, str], None],  # (account, status_string)
    ):
        self.account = account
        self.config = config
        self.manager = manager
        self.on_status = on_status

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pid: Optional[int] = None 
        self._launch_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"AutoRejoin-{self.account}",
        )
        self._thread.start()

    def stop(self, join_timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=join_timeout)

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _emit(self, status: str) -> None:
        try:
            self.on_status(self.account, status)
        except Exception:
            pass

    def _wait(self, seconds: float) -> bool:
        base = max(3, int(seconds))
        jitter = random.uniform(0.2, min(1.5, base * 0.2))
        return self._stop.wait(base + jitter)

    def _can_launch(self) -> bool:
        if not self.config.get("check_internet", True):
            return True
        return _has_internet()

    def _launch_and_track(self, place_id: str, private_server: str, job_id: str) -> bool:
        with self._launch_lock:
            pids_before = _get_roblox_pids()

            acc_data = self.manager.accounts.get(self.account, {})
            ok = self.manager.launch_roblox(
                self.account, place_id, private_server, "default", job_id, None
            )
            if not ok:
                return False

            time.sleep(5)

            pids_after = _get_roblox_pids()
            new_pids = pids_after - pids_before

            if not new_pids:
                return False

            free = new_pids - {self._pid} if self._pid else new_pids
            self._pid = max(free) if free else max(new_pids)
            print(f"[Auto-Rejoin] [{self.account}] Tracked PID {self._pid}")
            return True

    def _is_in_game(self, user_id, cookie: str, place_id: str) -> tuple:
        if not _wait_presence_slot(self._stop):
            return False, None
        try:
            presence = RobloxAPI.get_player_presence(user_id, cookie)
            if not presence:
                return False, None
            in_game = presence.get("in_game", False)
            cur_pid = presence.get("place_id")
            game_id = presence.get("game_id", "")
            if in_game:
                try:
                    if int(cur_pid) == int(place_id):
                        return True, game_id
                except (TypeError, ValueError):
                    pass
            return False, game_id
        except Exception as e:
            print(f"[Auto-Rejoin] [{self.account}] Presence error: {e}")
            return False, None

    def _run(self) -> None:
        cfg = self.config
        place_id = str(cfg.get("place_id", ""))
        private_server = cfg.get("private_server", "")
        job_id = cfg.get("job_id", "")
        check_interval = int(cfg.get("check_interval", 10))
        max_retries = int(cfg.get("max_retries", 5))
        check_presence = bool(cfg.get("check_presence", True))

        if not place_id:
            self._emit("ERROR: no place_id")
            return
        if self.account not in self.manager.accounts:
            self._emit("ERROR: account not found")
            return

        acc_data = self.manager.accounts[self.account]
        cookie = acc_data.get("cookie", "")
        user_id = acc_data.get("user_id") or RobloxAPI.get_user_id_from_username(self.account)

        if not user_id:
            self._emit("ERROR: cannot resolve user ID")
            return

        stagger = random.uniform(4.0, 8.0)
        if self._stop.wait(stagger):
            return

        retry_count = 0
        consec_fails = 0

        if not self._pid or not _pid_alive(self._pid):
            self._emit(f"Launching... (Place {place_id})")
            while not self._stop.is_set() and not self._can_launch():
                if self._wait(check_interval):
                    return
            ok = self._launch_and_track(place_id, private_server, job_id)
            if not ok:
                retry_count += 1
                self._emit(f"Launch failed ({retry_count}/{max_retries})")
                if retry_count >= max_retries:
                    self._emit("STOPPED: max retries")
                    return
            else:
                self._emit(f"ACTIVE — Place {place_id}")
            if self._stop.wait(10):
                return

        self._emit(f"ACTIVE — Place {place_id}")

        while not self._stop.is_set():
            try:
                disconnected = False
                game_id = ""

                if check_presence:
                    in_game, gid = self._is_in_game(user_id, cookie, place_id)
                    game_id = gid or ""
                    if in_game:
                        disconnected = False
                        consec_fails = 0
                    else:
                        consec_fails += 1
                        if consec_fails < 2:
                            if self._wait(check_interval):
                                break
                            continue
                        disconnected = True
                else:
                    if self._pid and not _pid_alive(self._pid):
                        consec_fails += 1
                        if consec_fails < 2:
                            if self._wait(check_interval):
                                break
                            continue
                        disconnected = True
                    else:
                        consec_fails = 0

                if disconnected:
                    retry_count  += 1
                    consec_fails = 0
                    print(f"[Auto-Rejoin] [{self.account}] Disconnect detected — attempt {retry_count}/{max_retries}")
                    self._emit(f"Rejoining... ({retry_count}/{max_retries})")

                    if self._pid:
                        _kill_pid(self._pid)
                        time.sleep(1)
                        self._pid = None

                    while not self._stop.is_set() and not self._can_launch():
                        if self._wait(check_interval):
                            break

                    if self._stop.is_set():
                        break

                    rejoin_jid = job_id if job_id else game_id
                    ok = self._launch_and_track(place_id, private_server, rejoin_jid)

                    if ok:
                        print(f"[Auto-Rejoin] [{self.account}] Rejoin successful")
                        retry_count = 0
                        self._emit(f"ACTIVE — Place {place_id}")
                        if self._stop.wait(10):
                            break
                    else:
                        self._emit(f"Launch failed ({retry_count}/{max_retries})")
                        if retry_count >= max_retries:
                            self._emit("STOPPED: max retries reached")
                            print(f"[Auto-Rejoin] [{self.account}] Max retries reached, stopping.")
                            break
                        if self._wait(check_interval):
                            break
                else:
                    retry_count = 0
                    if self._wait(check_interval):
                        break

            except Exception as e:
                print(f"[Auto-Rejoin] [{self.account}] Unhandled error: {e}")
                self._emit(f"ERROR: {e}")
                if self._wait(check_interval):
                    break

        self._emit("INACTIVE")
        print(f"[Auto-Rejoin] [{self.account}] Worker stopped.")
