"""
features/presence.py
Core logic of Presence Indicator.
"""

from __future__ import annotations

import os
import re
import threading
import psutil
from datetime import datetime, timezone
from typing import Callable

def _get_user_id_from_pid(pid: int) -> str | None:
    try:
        proc = psutil.Process(pid)
        create_utc = datetime.fromtimestamp(
            proc.create_time(), tz=timezone.utc
        ).replace(tzinfo=None)

        logs_dir = os.path.join(
            os.getenv("LOCALAPPDATA", ""), "Roblox", "logs"
        )
        if not os.path.isdir(logs_dir):
            return None

        candidates: list[tuple[float, str]] = []
        for fn in os.listdir(logs_dir):
            if not fn.endswith("_last.log"):
                continue
            m = re.search(r"(\d{8}T\d{6}Z)", fn)
            if not m:
                continue
            try:
                log_time = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ")
                diff = (log_time - create_utc).total_seconds()
                if 0 <= diff <= 60:
                    candidates.append((diff, os.path.join(logs_dir, fn)))
            except ValueError:
                continue

        candidates.sort(key=lambda x: x[0])
        for _, log_path in candidates:
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read(50_000)
                if "userid:" in content:
                    uid = content.split("userid:")[1].split(",")[0].strip()
                    if uid.isdigit():
                        return uid
            except Exception:
                continue
    except Exception:
        pass
    return None


def _scan_running_user_ids() -> set[str]:
    try:
        pids = [
            p.info["pid"]
            for p in psutil.process_iter(["pid", "name"])
            if (p.info.get("name") or "").lower() == "robloxplayerbeta.exe"
        ]
    except Exception:
        return set()

    online: set[str] = set()
    for pid in pids:
        uid = _get_user_id_from_pid(pid)
        if uid:
            online.add(uid)
    return online


def _build_uid_map(manager) -> dict[str, str]:
    result: dict[str, str] = {}
    for username, data in manager.accounts.items():
        if not isinstance(data, dict):
            continue
        uid = str(data.get("user_id", "") or "")
        if uid and uid != "0":
            result[uid] = username
    return result

class PresenceScanner:
    def __init__(
        self,
        manager,
        on_update: Callable[[set[str]], None],
        interval_sec: int = 10,
    ):
        self._manager = manager
        self._on_update = on_update
        self._interval = max(5, int(interval_sec))
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._force_evt = threading.Event()
        self.online_usernames: set[str] = set()


    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="PresenceScanner"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        self._force_evt.set()
        self._thread = None

    def force_scan(self) -> None:
        self._force_evt.set()

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            self._do_scan()
            self._force_evt.wait(timeout=self._interval)
            self._force_evt.clear()

    def _do_scan(self) -> None:
        try:
            running_ids = _scan_running_user_ids()
            uid_map = _build_uid_map(self._manager)
            new_online = {uid_map[uid] for uid in running_ids if uid in uid_map}

            if new_online != self.online_usernames:
                self.online_usernames = new_online
                try:
                    self._on_update(new_online)
                except Exception:
                    pass
        except Exception:
            pass
