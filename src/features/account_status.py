"""Read-only local Roblox client state for the Account Activity Monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import queue
import re
import threading
import time

import psutil
import win32con
import win32gui

from features.window_log_probe import probe_open_log_paths


COLORS = {"game": "#2ECC71", "background": "#F4C542", "error": "#E74C3C"}
SECURITY_CHALLENGE = "ROBLOX_SECURITY_CHALLENGE"
_PRIORITY = {"game": 3, "home": 2, "error": 1, "background": 0, None: -1}
_TRACKER = re.compile(r"browsertrackerid[^0-9]{0,32}(\d+)", re.I)
_WEB_TRACKER = re.compile(r"web launch, websiteBTId is (\d+)", re.I)
_USER = re.compile(r"\[FLog::GameJoinLoadTime\].*\buserid:(\d+)(?=[,\s])", re.I)
_JOIN = re.compile(r"! Joining game '([^']*)' place (\d+)")
_LOG_TIME = re.compile(r"(\d{8}T\d{6}Z)_Player_")
_CRASH = re.compile(r"\[(?:LOGCHANNELS \+ \d+|FLog::(?:Error|Output))\]\s+RBXCRASH:\s*")


@dataclass
class ClientLog:
    """Replay a client's events in order, then read only appended bytes."""

    created: float
    identity: tuple[int, int] | None = None
    offset: int = 0
    mtime: int = 0
    partial: bytes = b""
    trackers: set[str] = field(default_factory=set)
    web_trackers: set[str] = field(default_factory=set)
    user_id: str = ""
    signed_in: bool = False
    desktop: bool = False
    state: str | None = None
    reason: str = ""
    place_id: str = ""
    job_id: str = ""
    available: bool = False

    def event(self, line: str) -> None:
        self.trackers.update(_TRACKER.findall(line))
        self.web_trackers.update(_WEB_TRACKER.findall(line))
        user = _USER.search(line)
        if user:
            self.user_id = user[1]
        if "[FLog::SingleSurfaceApp]" in line:
            message = line.split("[FLog::SingleSurfaceApp]", 1)[1].strip()
            if message.startswith(("initializeLuaAppWithLoggedInUser:", "userDidLogin")):
                self.signed_in = True
                if self.desktop:
                    self.state, self.reason = "home", "Signed in to the Roblox desktop app; outside a game."
            elif message.startswith("setStage: (stage:LuaApp)"):
                self.desktop = True
                if self.signed_in:
                    self.state, self.reason = "home", "Signed in to the Roblox desktop app; outside a game."
                    self.place_id = self.job_id = ""
            elif message.startswith(("launchUGCGame", "setStage: (stage:UGCGame)")):
                self.desktop = False
                self.place_id = self.job_id = ""
            elif message.startswith(("returnToLuaApp", "leaveUGCGameInternal")):
                self.desktop = False
            elif message.startswith(("userDidLogout", "userDidLogOut", "shutDown:", "destroyLuaApp:")):
                self.signed_in = self.desktop = False
        if "[FLog::Output] ! Joining game" in line:
            self.desktop = False
            self.place_id = self.job_id = ""
            match = _JOIN.search(line)
            if match:
                self.job_id, self.place_id = match.groups()
        elif "[FLog::Network] Replicator created:" in line:
            # A connection marker is sufficient even if optional IDs are absent.
            self.desktop = False
            self.state, self.reason = "game", "Connected to a game server."
        elif "[FLog::Network] Time to disconnect replication data:" in line:
            self.desktop = False
            self.place_id = self.job_id = ""
        elif "[FLog::UgcExperienceController]" in line and "doTeleport:" in line:
            self.desktop = False
            self.place_id = self.job_id = ""
        # Routine asset/script/HTTP errors are common in healthy clients. Only
        # explicit session-failure, security-challenge or crash markers turn red.
        if "challengedByGcs" in line:
            self.desktop = False
            self.state, self.reason = "error", SECURITY_CHALLENGE
        elif "[FLog::Output] Session Transition FSM: Error Occurred." in line:
            self.desktop = False
            self.state, self.reason = "error", "Session failure"
        elif _CRASH.search(line):
            self.desktop = False
            self.state, self.reason = "error", "Fatal client crash (RBXCRASH)"

    def read(self, path: str) -> None:
        self.available = False
        try:
            with open(path, "rb") as handle:
                stat = os.fstat(handle.fileno())
                identity = (stat.st_dev, stat.st_ino)
                if (identity != self.identity or stat.st_size < self.offset
                        or (stat.st_size == self.offset and stat.st_mtime_ns != self.mtime)):
                    fresh = ClientLog(self.created)
                    self.__dict__.update(fresh.__dict__)
                    self.identity = identity
                handle.seek(self.offset)
                # Bound catch-up work so a large old log cannot monopolize a scan.
                for _ in range(16):
                    chunk = handle.read(64 * 1024)
                    if not chunk:
                        break
                    self.offset += len(chunk)
                    lines = (self.partial + chunk).split(b"\n")
                    self.partial = lines.pop()
                    for line in lines:
                        self.event(line.decode("utf-8", errors="replace"))
                    if len(self.partial) > 256 * 1024:
                        self.partial = b""
                self.mtime = stat.st_mtime_ns
                # Launch confirmation recognizes this marker before a trailing
                # newline too; a challenged client may stop writing at this point.
                if b"challengedByGcs" in self.partial:
                    self.desktop = False
                    self.state, self.reason = "error", SECURITY_CHALLENGE
                self.available = self.offset >= stat.st_size and stat.st_size > 0 and not self.partial
        except OSError:
            pass


def client_window_visible(hwnds: list[int]) -> bool | None:
    """Ignore helper/owned windows and titles changed by Window Renamer."""
    unknown = False
    for hwnd in hwnds:
        try:
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                continue
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if right <= left or bottom <= top or not win32gui.GetWindowText(hwnd):
                continue
            if win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return True
        except Exception:
            unknown = True
    return None if unknown else False


def has_error_dialog(hwnds: list[int]) -> bool:
    """Recognize explicit native error dialogs belonging to this Roblox PID."""
    for hwnd in hwnds:
        try:
            if (win32gui.IsWindowVisible(hwnd)
                    and win32gui.GetClassName(hwnd) == "#32770"
                    and win32gui.GetWindowText(hwnd).strip().casefold() in {
                        "error", "roblox error", "roblox crash",
                    }):
                return True
        except Exception:
            pass
    return False


def summarize_processes(processes: list[dict], headless: set[tuple[int, float]]) -> dict:
    """Apply background precedence per client, then aggregate per account."""
    rows = []
    for process in processes:
        row = dict(process)
        row["headless"] = (row["pid"], row["created"]) in headless
        state = row.get("client_state")
        if state != "error" and not row["headless"] and row.get("window_visible") is False:
            if time.time() - row["created"] >= 5:
                state = "background"
        row["state"] = state
        rows.append(row)
    selected = max(rows, key=lambda row: _PRIORITY[row["state"]])
    state = selected["state"]
    hollow = all(row["headless"] for row in rows)
    names = {"game": "In Game", "home": "In Main Screen",
             "background": "Running in Background", None: ""}
    tooltip = (f"Error: {selected.get('reason') or 'Roblox client error'}"
               if state == "error" else names[state])
    if tooltip and hollow:
        tooltip += " (Headless)"
    return {"state": state, "hollow": hollow, "tooltip": tooltip}


class ClientStatusTracker:
    """Keep log bindings scoped to process lifetimes, without changing windows."""

    def __init__(self, stop_event):
        self._stop = stop_event
        self._logs: dict[str, ClientLog] = {}
        self._bindings: dict[tuple[int, float], tuple[str, str]] = {}
        self._probe_retry: dict[tuple[int, float], float] = {}
        self._missing_since: dict[tuple[int, float], float] = {}
        self._last_windows: dict[tuple[int, float], bool] = {}
        self._probe_thread: threading.Thread | None = None
        self._probe_results = queue.SimpleQueue()
        self._open_paths: dict[tuple[int, float], set[str]] = {}

    def _probe(self, key: tuple[int, float]) -> None:
        self._probe_results.put((key, probe_open_log_paths(key, self._stop)))

    def scan(self, processes: dict, uid_map: dict, launch_records: dict,
             windows: dict[int, list[int]]) -> dict[tuple[int, float], dict]:
        live = {(pid, data[0]) for pid, data in processes.items()}
        self._bindings = {key: value for key, value in self._bindings.items() if key in live}
        self._probe_retry = {key: value for key, value in self._probe_retry.items() if key in live}
        self._open_paths = {key: value for key, value in self._open_paths.items() if key in live}
        while not self._probe_results.empty():
            key, probe = self._probe_results.get_nowait()
            if key in live:
                self._probe_retry[key] = time.monotonic() + (5 if probe.status == "ok" else 30)
                if probe.status == "ok":
                    self._open_paths[key] = set(probe.paths)
        self._missing_since = {key: value for key, value in self._missing_since.items() if key in live}
        self._last_windows = {key: value for key, value in self._last_windows.items() if key in live}
        if not live:
            self._logs.clear()
            return {}
        logs_dir = os.path.join(os.getenv("LOCALAPPDATA", ""), "Roblox", "logs")
        paths = set()
        try:
            filenames = os.listdir(logs_dir)
        except OSError:
            filenames = []
        earliest, latest = min(key[1] for key in live) - 2, max(key[1] for key in live) + 300
        for filename in filenames:
            match = _LOG_TIME.search(filename)
            if not match or not filename.endswith("_last.log") or "CrashHandler" in filename:
                continue
            created = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
            if not earliest <= created <= latest:
                continue
            path = os.path.normcase(os.path.abspath(os.path.join(logs_dir, filename)))
            paths.add(path)
            log = self._logs.setdefault(path, ClientLog(created))
            log.read(path)
        self._logs = {path: log for path, log in self._logs.items() if path in paths}
        trackers = {}
        for pid, (created, process) in processes.items():
            try:
                values = set(_TRACKER.findall(" ".join(process.cmdline())))
            except (OSError, psutil.Error):
                values = set()
            trackers[(pid, created)] = next(iter(values)) if len(values) == 1 else ""
        claimed = {path: key for key, (path, _) in self._bindings.items() if path}
        result = {}
        for key in sorted(live, key=lambda key: self._probe_retry.get(key, 0)):
            if self._stop.is_set():
                break
            tracker = trackers[key]
            record = launch_records.get(tracker)
            recorded_user = (str(record[0]) if record and -2 <= key[1] - record[1] <= 300
                             and list(trackers.values()).count(tracker) == 1 else "")
            path, user_id = self._bindings.get(key, ("", recorded_user))
            if not path or path not in self._logs:
                matches = [path for path, log in self._logs.items()
                           if tracker and tracker in (log.web_trackers or log.trackers)
                           and -2 <= log.created - key[1] <= 60
                           and claimed.get(path, key) == key]
                if len(matches) == 1 and list(trackers.values()).count(tracker) == 1:
                    path = matches[0]
                else:
                    matches = [path for path in self._open_paths.get(key, set()) if path in self._logs
                               and claimed.get(path, key) == key]
                    if len(matches) == 1:
                        path = matches[0]
                    elif (time.monotonic() >= self._probe_retry.get(key, 0)
                          and (self._probe_thread is None or not self._probe_thread.is_alive())):
                        # Native file discovery has its own bounded helper. Keep
                        # it off the status scan so slow identity work cannot
                        # hold up already identified clients' two-second updates.
                        self._probe_retry[key] = time.monotonic() + 30
                        self._probe_thread = threading.Thread(
                            target=self._probe, args=(key,), daemon=True, name="AccountLogProbe",
                        )
                        self._probe_thread.start()
            log = self._logs.get(path)
            if log and log.user_id:
                user_id = log.user_id
            if user_id not in uid_map:
                continue
            self._bindings[key] = (path, user_id)
            if path:
                claimed[path] = key
            visible = client_window_visible(windows.get(key[0], []))
            # Require a stable absence to avoid yellow during window replacement.
            if visible is False:
                since = self._missing_since.setdefault(key, time.monotonic())
                if time.monotonic() - since < 1:
                    visible = None
            else:
                self._missing_since.pop(key, None)
            if visible is None:
                visible = self._last_windows.get(key)
            else:
                self._last_windows[key] = visible
            available = bool(log and log.available)
            state = log.state if log and (available or log.state == "error") else None
            reason = log.reason if state is not None else ""
            if state != "error" and has_error_dialog(windows.get(key[0], [])):
                state, reason = "error", "Roblox error or crash dialog"
            result[key] = {
                "pid": key[0], "created": key[1], "username": uid_map[user_id],
                "client_state": state,
                "reason": reason,
                "window_visible": visible,
                "place_id": log.place_id if available else "",
                "job_id": log.job_id if available else "",
            }
        return result
