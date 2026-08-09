"""
Account Activity Monitor process scanning.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import re
import threading
from typing import Callable

import psutil
import win32api

def _get_user_id_from_pid(
    pid: int,
    used_logs: set[str] | None = None,
) -> str | None:
    try:
        proc = psutil.Process(pid)
        create_utc = datetime.fromtimestamp(
            proc.create_time(),
            tz=timezone.utc,
        ).replace(tzinfo=None)

        logs_dir = os.path.join(
            os.getenv("LOCALAPPDATA", ""),
            "Roblox",
            "logs",
        )
        if not os.path.isdir(logs_dir):
            return None

        candidates: list[tuple[float, str]] = []
        for filename in os.listdir(logs_dir):
            if not filename.endswith("_last.log"):
                continue
            match = re.search(r"(\d{8}T\d{6}Z)", filename)
            if not match:
                continue
            try:
                log_time = datetime.strptime(
                    match.group(1),
                    "%Y%m%dT%H%M%SZ",
                )
                diff = (log_time - create_utc).total_seconds()
                if 0 <= diff <= 60:
                    candidates.append((
                        diff,
                        os.path.join(logs_dir, filename),
                    ))
            except ValueError:
                continue

        candidates.sort(key=lambda item: item[0])
        for _, log_path in candidates:
            if used_logs is not None and log_path in used_logs:
                continue
            try:
                with open(
                    log_path,
                    "r",
                    encoding="utf-8",
                    errors="ignore",
                ) as handle:
                    content = handle.read(50_000)
                if "userid:" not in content:
                    continue
                user_id = content.split("userid:", 1)[1].split(",", 1)[0].strip()
                if user_id.isdigit():
                    if used_logs is not None:
                        used_logs.add(log_path)
                    return user_id
            except (OSError, UnicodeError):
                continue
    except (
        OSError,
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        psutil.ZombieProcess,
    ):
        return None
    except Exception:
        return None
    return None


def _get_exe_description(pid: int) -> str:
    try:
        process = psutil.Process(pid)
        executable = process.exe()
        translations = win32api.GetFileVersionInfo(
            executable,
            r"\VarFileInfo\Translation",
        )
        if not translations:
            return ""
        lang, codepage = translations[0]
        key = (
            f"\\StringFileInfo\\{lang:04X}{codepage:04X}"
            "\\FileDescription"
        )
        return win32api.GetFileVersionInfo(executable, key) or ""
    except Exception:
        return ""


def _is_valid_roblox_game_client(
    pid: int,
    process_name_lower: str | None = None,
) -> bool:
    try:
        if process_name_lower is None:
            try:
                process_name_lower = psutil.Process(pid).name().lower()
            except Exception:
                return False

        if process_name_lower != "robloxplayerbeta.exe":
            return False

        description = _get_exe_description(pid)
        if description:
            return "roblox" in description.lower()

        return True
    except Exception:
        return process_name_lower == "robloxplayerbeta.exe" if process_name_lower else False


def _get_roblox_processes() -> dict[int, tuple[float, psutil.Process]]:
    processes: dict[int, tuple[float, psutil.Process]] = {}
    try:
        process_iter = psutil.process_iter(
            ["pid", "name", "create_time"],
        )
        for process in process_iter:
            try:
                process_name = (process.info.get("name") or "").lower()
                if process_name != "robloxplayerbeta.exe":
                    continue

                pid = int(process.info["pid"])
                if not _is_valid_roblox_game_client(pid, process_name):
                    continue

                create_time = process.info.get("create_time")
                if create_time is None:
                    create_time = process.create_time()
                processes[pid] = (float(create_time), process)
            except (
                OSError,
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess,
            ):
                continue
    except (
        OSError,
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        psutil.ZombieProcess,
    ):
        pass
    return processes


def _get_roblox_pids() -> set[int]:
    return set(_get_roblox_processes())


def _build_uid_map(manager) -> dict[str, str]:
    result: dict[str, str] = {}
    accounts_lock = getattr(manager, "_accounts_lock", None)
    if accounts_lock is not None:
        with accounts_lock:
            accounts = list(manager.accounts.items())
    else:
        accounts = list(manager.accounts.items())

    for username, data in accounts:
        if not isinstance(data, dict):
            continue
        user_id = str(data.get("user_id", "") or "")
        if user_id and user_id != "0":
            result[user_id] = username
    return result


class PresenceScanner:
    def __init__(
        self,
        manager,
        on_update: Callable[[dict[str, dict]], None],
        interval_sec: int = 5,
    ):
        self._manager = manager
        self._on_update = on_update
        self._interval = max(5, int(interval_sec))
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._pid_uid_cache: dict[int, tuple[float, str]] = {}
        self._process_cache: dict[int, tuple[float, psutil.Process]] = {}
        self._logical_cpu_count = max(1, psutil.cpu_count() or 1)
        self.latest_snapshot: dict[str, dict] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="AccountActivityMonitor",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.5)
        self._pid_uid_cache.clear()
        self._process_cache.clear()
        self.latest_snapshot = {}

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            self._do_scan()
            if self._stop_evt.wait(self._interval):
                break

    def _resolve_pid_user_id(
        self,
        pid: int,
        create_time: float,
        used_logs: set[str],
    ) -> str | None:
        cached = self._pid_uid_cache.get(pid)
        if cached is not None and cached[0] == create_time:
            return cached[1]

        user_id = _get_user_id_from_pid(pid, used_logs)
        if user_id:
            self._pid_uid_cache[pid] = (create_time, user_id)
        return user_id

    def _do_scan(self) -> None:
        try:
            discovered_processes = _get_roblox_processes()
            current_pids = set(discovered_processes)
            self._pid_uid_cache = {
                pid: value
                for pid, value in self._pid_uid_cache.items()
                if pid in current_pids
                and value[0] == discovered_processes[pid][0]
            }
            self._process_cache = {
                pid: value
                for pid, value in self._process_cache.items()
                if pid in current_pids
                and value[0] == discovered_processes[pid][0]
            }

            current_processes: dict[int, tuple[float, psutil.Process]] = {}
            for pid, (create_time, discovered_process) in discovered_processes.items():
                cached = self._process_cache.get(pid)
                if cached is None:
                    cached = (create_time, discovered_process)
                    self._process_cache[pid] = cached
                current_processes[pid] = cached

            uid_map = _build_uid_map(self._manager)
            if not uid_map:
                self.latest_snapshot = {}
                self._on_update({})
                return

            used_logs: set[str] = set()
            matched_processes: list[tuple[str, psutil.Process]] = []
            for pid in sorted(current_processes):
                create_time, process = current_processes[pid]
                user_id = self._resolve_pid_user_id(
                    pid,
                    create_time,
                    used_logs,
                )
                username = uid_map.get(user_id or "")
                if username:
                    matched_processes.append((username, process))

            aggregates: dict[str, dict] = {}
            for username, process in matched_processes:
                entry = aggregates.setdefault(username, {
                    "pids": [],
                    "ram_mb": 0.0,
                    "cpu_percent": 0.0,
                    "ram_available": False,
                    "cpu_available": False,
                })
                try:
                    entry["pids"].append(process.pid)
                    entry["ram_mb"] += process.memory_info().rss / 1024 / 1024
                    entry["ram_available"] = True
                except (
                    OSError,
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    pass
                try:
                    entry["cpu_percent"] += max(
                        0.0,
                        float(process.cpu_percent(interval=None)),
                    )
                    entry["cpu_available"] = True
                except (
                    OSError,
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    pass

            snapshot: dict[str, dict] = {}
            for username, entry in aggregates.items():
                entry["cpu_percent"] = min(
                    100.0,
                    entry["cpu_percent"] / self._logical_cpu_count,
                )
                snapshot[username] = entry

            self.latest_snapshot = snapshot
            try:
                self._on_update(snapshot)
            except Exception:
                pass
        except Exception as exc:
            print(
                f"[ERROR] Account Activity Monitor scan failed: "
                f"{type(exc).__name__}: {exc}"
            )
