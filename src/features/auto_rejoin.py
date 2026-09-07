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
import features.presence as presence_mod
from utils.app_paths import get_data_dir

_CONFIG_FILE = os.path.join(get_data_dir(), "auto_rejoin.json")
_CONFIG_LOCK = threading.RLock()
_CONFIG_CACHE: dict | None = None
_INTERNET_LOCK = threading.Lock()
_INTERNET_CACHE = (0.0, False)
_PID_UID_LOCK = threading.Lock()
_PID_UID_CACHE: dict[tuple[int, float], str] = {}
_LAUNCH_LOCK = threading.Lock()

RobloxProcessIdentity = tuple[int, float]

def load_configs() -> dict:
    global _CONFIG_CACHE
    with _CONFIG_LOCK:
        if _CONFIG_CACHE is None:
            data = {}
            if os.path.exists(_CONFIG_FILE):
                try:
                    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
                except (OSError, ValueError, TypeError):
                    pass
            _CONFIG_CACHE = data
        return dict(_CONFIG_CACHE)


def save_configs(configs: dict) -> None:
    global _CONFIG_CACHE
    with _CONFIG_LOCK:
        if _CONFIG_CACHE == configs:
            return
    os.makedirs(get_data_dir(), exist_ok=True)
    temp_file = _CONFIG_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=2)
        os.replace(temp_file, _CONFIG_FILE)
        with _CONFIG_LOCK:
            _CONFIG_CACHE = dict(configs)
    except Exception as e:
        print(f"[WARNING] Safe configs save failed: {e}. Falling back to original direct write.")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        # Original direct write fallback
        try:
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(configs, f, indent=2)
        except Exception:
            pass

def _has_internet(timeout: int = 3) -> bool:
    global _INTERNET_CACHE
    now = time.monotonic()
    with _INTERNET_LOCK:
        checked_at, cached = _INTERNET_CACHE
        if now - checked_at < 10.0:
            return cached
    for url in ("https://www.google.com/generate_204",
                "https://www.cloudflare.com/cdn-cgi/trace"):
        try:
            if requests.get(url, timeout=timeout).status_code < 500:
                with _INTERNET_LOCK:
                    _INTERNET_CACHE = (time.monotonic(), True)
                return True
        except Exception:
            pass
    with _INTERNET_LOCK:
        _INTERNET_CACHE = (time.monotonic(), False)
    return False


def _get_roblox_processes(force: bool = False) -> dict[int, tuple[float, psutil.Process]]:
    return presence_mod.get_roblox_processes(force=force)


def _get_roblox_pids(force: bool = False) -> set[int]:
    return set(_get_roblox_processes(force=force))


def _identity_matches(
    identity: RobloxProcessIdentity,
    processes: dict[int, tuple[float, psutil.Process]] | None = None,
) -> bool:
    if processes is None:
        processes = _get_roblox_processes(force=True)
    pid, create_time = identity
    current = processes.get(pid)
    return bool(current and abs(current[0] - create_time) <= 0.01)


def _pid_alive(
    pid: int,
    create_time: float | None = None,
) -> bool:
    processes = _get_roblox_processes(force=True)
    if create_time is None:
        return pid in processes
    return _identity_matches((pid, create_time), processes)


def _terminate_process(
    identity: RobloxProcessIdentity,
    account: str,
    stop_event: threading.Event | None = None,
) -> tuple[bool, str]:
    pid, create_time = identity
    last_detail = ""

    for attempt in range(1, 4):
        processes = _get_roblox_processes(force=True)
        current = processes.get(pid)
        if current is None or abs(current[0] - create_time) > 0.01:
            return True, "Process already exited."

        try:
            result = subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10,
            )
            output = (result.stdout or result.stderr or "").strip()
            last_detail = output[-500:]
            if result.returncode != 0:
                print(
                    f"[Auto-Rejoin] [{account}] taskkill failed for PID {pid} "
                    f"(attempt {attempt}/3, exit {result.returncode})"
                )
                try:
                    process = psutil.Process(pid)
                    if abs(process.create_time() - create_time) <= 0.01:
                        process.kill()
                except (OSError, psutil.Error):
                    pass
        except Exception as exc:
            last_detail = str(exc)
            print(
                f"[Auto-Rejoin] [{account}] Failed to terminate PID {pid} "
                f"(attempt {attempt}/3): {exc}"
            )

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not _identity_matches(identity, _get_roblox_processes(force=True)):
                print(f"[Auto-Rejoin] [{account}] Closed Roblox PID {pid}.")
                return True, "Process closed."
            if stop_event is not None and stop_event.wait(0.25):
                return False, "Auto-Rejoin stopped while closing the process."
            time.sleep(0.25)

    print(
        f"[Auto-Rejoin] [{account}] Could not confirm Roblox PID {pid} closed."
    )
    return False, last_detail or "The process is still running."


def scan_pid_uid_map(
    wanted_user_ids: set[str],
) -> dict[str, set[RobloxProcessIdentity]]:
    current_processes = _get_roblox_processes(force=True)
    current_identities = {
        (pid, process_data[0])
        for pid, process_data in current_processes.items()
    }
    used_logs: set[str] = set()

    with _PID_UID_LOCK:
        stale = set(_PID_UID_CACHE) - current_identities
        for identity in stale:
            _PID_UID_CACHE.pop(identity, None)

        for identity in sorted(current_identities, key=lambda item: item[1]):
            if identity in _PID_UID_CACHE:
                continue
            uid = presence_mod._get_user_id_from_pid(identity[0], used_logs)
            if uid:
                _PID_UID_CACHE[identity] = str(uid)

        result: dict[str, set[RobloxProcessIdentity]] = {}
        for identity, uid in _PID_UID_CACHE.items():
            if uid in wanted_user_ids:
                result.setdefault(uid, set()).add(identity)

    return result


def _get_configured_user_ids(manager) -> set[str]:
    wanted = set()
    for username in load_configs().keys():
        acc = manager.accounts.get(username)
        if isinstance(acc, dict):
            uid = str(acc.get("user_id", "") or "")
            if uid and uid != "0":
                wanted.add(uid)
    return wanted


def find_running_processes_for_user(
    manager,
    user_id: str,
) -> set[RobloxProcessIdentity]:
    normalized_user_id = str(user_id)
    wanted = _get_configured_user_ids(manager) | {normalized_user_id}
    return scan_pid_uid_map(wanted).get(normalized_user_id, set())


def find_running_pid_for_user(manager, user_id: str) -> int | None:
    identities = find_running_processes_for_user(manager, user_id)
    if not identities:
        return None
    return max(identities, key=lambda item: item[1])[0]

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
        self._process_identity: RobloxProcessIdentity | None = None
        self._owned_processes: set[RobloxProcessIdentity] = set()

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

    def _launch_and_track(
        self,
        user_id: str,
        place_id: str,
        private_server: str,
        job_id: str,
    ) -> bool:
        with _LAUNCH_LOCK:
            processes_before = _get_roblox_processes(force=True)
            identities_before = {
                (pid, process_data[0])
                for pid, process_data in processes_before.items()
            }

            ok = self.manager.launch_roblox(
                self.account, place_id, private_server, "default", job_id, None
            )
            if not ok:
                return False

            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                if self._stop.wait(0.5):
                    return False

                processes_after = _get_roblox_processes(force=True)
                candidates: set[RobloxProcessIdentity] = set()
                for pid, process_data in processes_after.items():
                    identity = (pid, process_data[0])
                    if identity in identities_before:
                        continue
                    resolved_user_id = presence_mod._get_user_id_from_pid(
                        pid,
                        set(),
                    )
                    if str(resolved_user_id or "") == str(user_id):
                        candidates.add(identity)

                if candidates:
                    self._owned_processes = candidates
                    self._process_identity = max(
                        candidates,
                        key=lambda item: item[1],
                    )
                    print(
                        f"[Auto-Rejoin] [{self.account}] Tracked PID "
                        f"{self._process_identity[0]} for user {user_id}."
                    )
                    if len(candidates) > 1:
                        print(
                            f"[Auto-Rejoin] [{self.account}] Detected "
                            f"{len(candidates)} matching Roblox processes."
                        )
                    return True

            processes_after = _get_roblox_processes(force=True)
            identities_after = {
                (pid, process_data[0])
                for pid, process_data in processes_after.items()
            }
            matching_identities: set[RobloxProcessIdentity] = set()
            for identity in identities_after - identities_before:
                resolved_user_id = presence_mod._get_user_id_from_pid(
                    identity[0],
                    set(),
                )
                if str(resolved_user_id or "") == str(user_id):
                    matching_identities.add(identity)

            for identity in matching_identities:
                closed, detail = _terminate_process(
                    identity,
                    self.account,
                    self._stop,
                )
                if not closed:
                    print(
                        f"[Auto-Rejoin] [{self.account}] Could not clean "
                        f"unresolved PID {identity[0]}: {detail}"
                    )

            print(
                f"[Auto-Rejoin] [{self.account}] Could not resolve the "
                "new Roblox process to the account."
            )
            return False

    def _is_in_game(
        self,
        user_id,
        cookie: str,
        place_id: str,
        check_place_id: bool = True,
    ) -> tuple[str, str]:
        if not self._process_identity or not _identity_matches(self._process_identity):
            return "disconnected", ""
        if not _wait_presence_slot(self._stop):
            return "unavailable", ""
        try:
            presence = RobloxAPI.get_player_presence(user_id, cookie)
            if not presence:
                return "unavailable", ""
            in_game = presence.get("in_game", False)
            cur_pid = presence.get("place_id")
            game_id = presence.get("game_id", "")
            status = presence.get("status")
            online = bool(status) if status is not None else bool(in_game)
            if not online:
                return "disconnected", game_id
            if not check_place_id:
                return "in_game", game_id
            if in_game:
                try:
                    if int(cur_pid) == int(place_id):
                        return "in_game", game_id
                except (TypeError, ValueError):
                    pass
            return "disconnected", game_id
        except Exception as e:
            print(f"[Auto-Rejoin] [{self.account}] Presence error: {e}")
            return "unavailable", ""

    def _run(self) -> None:
        cfg = self.config
        place_id = str(cfg.get("place_id", ""))
        private_server = cfg.get("private_server", "")
        job_id = cfg.get("job_id", "")
        check_interval = int(cfg.get("check_interval", 10))
        max_retries = int(cfg.get("max_retries", 5))
        check_presence = bool(cfg.get("check_presence", True))
        check_place_id = bool(cfg.get("check_place_id", True))

        if not place_id:
            self._emit("ERROR: no place_id")
            return
        if self.account not in self.manager.accounts:
            self._emit("ERROR: account not found")
            return

        acc_data = self.manager.accounts[self.account]
        cookie = acc_data.get("cookie", "")
        user_id = acc_data.get("user_id")
        if not user_id:
            user_id = RobloxAPI.get_user_id_from_username(self.account)
            if user_id:
                acc_data["user_id"] = user_id
                try:
                    self.manager.save_accounts()
                except Exception:
                    pass

        if not user_id:
            self._emit("ERROR: cannot resolve user ID")
            return

        stagger = random.uniform(4.0, 8.0)
        if self._stop.wait(stagger):
            return

        retry_count = 0
        consec_fails = 0

        if not self._process_identity or not _identity_matches(self._process_identity):
            while not self._stop.is_set():
                existing_processes = find_running_processes_for_user(
                    self.manager,
                    str(user_id),
                )
                if existing_processes:
                    self._owned_processes = existing_processes
                    self._process_identity = max(
                        existing_processes,
                        key=lambda item: item[1],
                    )
                    print(
                        f"[Auto-Rejoin] [{self.account}] Adopted existing PID "
                        f"{self._process_identity[0]} for user {user_id}"
                    )
                    self._emit(f"ACTIVE - Place {place_id} (existing client)")
                    break

                self._emit(f"Launching... (Place {place_id})")
                while not self._stop.is_set() and not self._can_launch():
                    if self._wait(check_interval):
                        return
                if self._stop.is_set():
                    return

                ok = self._launch_and_track(
                    str(user_id),
                    place_id,
                    private_server,
                    job_id,
                )
                if ok:
                    self._emit(f"ACTIVE - Place {place_id}")
                    break

                retry_count += 1
                self._emit(f"Launch failed ({retry_count}/{max_retries})")
                if retry_count >= max_retries:
                    self._emit("STOPPED: max retries")
                    return
                if self._wait(check_interval):
                    return

        self._emit(f"ACTIVE - Place {place_id}")

        while not self._stop.is_set():
            try:
                disconnected = False
                game_id = ""

                if check_presence:
                    presence_state, gid = self._is_in_game(
                        user_id,
                        cookie,
                        place_id,
                        check_place_id,
                    )
                    game_id = gid or ""
                    if presence_state == "in_game":
                        disconnected = False
                        consec_fails = 0
                    elif presence_state == "unavailable":
                        consec_fails = 0
                        if self._wait(check_interval):
                            break
                        continue
                    else:
                        consec_fails += 1
                        if consec_fails < 2:
                            if self._wait(check_interval):
                                break
                            continue
                        disconnected = True
                else:
                    if (
                        self._process_identity
                        and not _identity_matches(self._process_identity)
                    ):
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
                    print(f"[Auto-Rejoin] [{self.account}] Disconnect detected, attempt {retry_count}/{max_retries}")
                    self._emit(f"Rejoining... ({retry_count}/{max_retries})")

                    identities_to_close = set(self._owned_processes)
                    if self._process_identity:
                        identities_to_close.add(self._process_identity)
                    identities_to_close.update(
                        find_running_processes_for_user(
                            self.manager,
                            str(user_id),
                        )
                    )

                    cleanup_ok = True
                    for identity in sorted(
                        identities_to_close,
                        key=lambda item: item[1],
                    ):
                        closed, detail = _terminate_process(
                            identity,
                            self.account,
                            self._stop,
                        )
                        if not closed:
                            cleanup_ok = False
                            print(
                                f"[Auto-Rejoin] [{self.account}] Cleanup "
                                f"failed for PID {identity[0]}: {detail}"
                            )

                    if not cleanup_ok:
                        self._emit("Rejoin delayed: closing old client")
                        if self._wait(check_interval):
                            break
                        continue

                    self._process_identity = None
                    self._owned_processes.clear()

                    while not self._stop.is_set() and not self._can_launch():
                        if self._wait(check_interval):
                            break

                    if self._stop.is_set():
                        break

                    rejoin_jid = job_id if job_id else game_id
                    existing_processes = find_running_processes_for_user(
                        self.manager,
                        str(user_id),
                    )
                    if existing_processes:
                        self._owned_processes = existing_processes
                        self._process_identity = max(
                            existing_processes,
                            key=lambda item: item[1],
                        )
                        ok = True
                        print(
                            f"[Auto-Rejoin] [{self.account}] Adopted existing "
                            f"PID {self._process_identity[0]} instead of relaunching"
                        )
                    else:
                        ok = self._launch_and_track(
                            str(user_id),
                            place_id,
                            private_server,
                            rejoin_jid,
                        )

                    if ok:
                        print(f"[Auto-Rejoin] [{self.account}] Rejoin successful")
                        retry_count = 0
                        self._emit(f"ACTIVE - Place {place_id}")
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
