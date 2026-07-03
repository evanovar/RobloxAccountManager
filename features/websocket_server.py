"""
features/websocket_server.py
Websocket Server core logic.

Supported commands (case-insensitive, shlex-parsed):
  Ping
  AccountList
  Add <cookie> [cookie2 ...]
  Launch <account> <place_id> [private_server] [job_id]
  JoinUser <account> <target_username>
  AutoRejoin <start|stop> <account>
  GetStatus

Authentication (when websocket_require_password is true):
  AUTH <password> | <command>
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shlex
import threading
import websockets
import psutil
from datetime import datetime, timezone
from typing import Callable
import features.auto_rejoin as _ar
from classes.roblox_api import RobloxAPI
from classes.account_manager import RobloxAccountManager


class WebSocketServer:
    SUPPORTED_COMMANDS = [
        "AccountList", "Add", "AutoRejoin",
        "GetStatus", "JoinUser", "Launch", "Ping",
    ]

    def __init__(
        self,
        manager: "RobloxAccountManager",
        ar_workers: dict,
        ar_configs: dict,
        get_settings: Callable[[], dict],
        refresh_ui_callback: Callable[[], None] | None = None,
    ):
        self.manager = manager
        self._ar_workers = ar_workers
        self._ar_configs = ar_configs
        self._settings_fn = get_settings
        self._refresh_ui = refresh_ui_callback

        self._thread: threading.Thread | None = None
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self.running = False


    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="WebSocketServer"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(lambda: None)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        self._loop = None
        self.running = False

    def restart(self) -> None:
        self.stop()
        s = self._get_settings()
        if s.get("websocket_enabled") and s.get("developer_mode"):
            self.start()

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._server_main())
        except Exception as exc:
            print(f"[ERROR] WebSocket server crashed: {exc}")
        finally:
            self.running = False
            self._loop = None
            try:
                loop.close()
            except Exception:
                pass

    async def _server_main(self) -> None:
        port = self._get_port()
        host = "localhost"
        try:
            async with websockets.serve(self._client_handler, host, port):
                self.running = True
                print(f"[INFO] WebSocket server started at ws://{host}:{port}")
                while not self._stop.is_set():
                    await asyncio.sleep(0.2)
        except OSError as exc:
            print(f"[ERROR] WebSocket server failed on port {port}: {exc}")
        finally:
            if self.running:
                print("[INFO] WebSocket server stopped")
            self.running = False

    async def _client_handler(self, websocket) -> None:
        try:
            async for raw in websocket:
                message = str(raw or "")
                max_len = self._get_max_message_len()
                if max_len > 0 and len(message) > max_len:
                    resp = {"ok": False, "error": f"Message too long (max {max_len} chars)"}
                else:
                    resp = self._execute(message)
                await websocket.send(json.dumps(resp, ensure_ascii=False))
        except Exception as exc:
            print(f"[ERROR] WebSocket client error: {exc}")

    def _execute(self, raw: str) -> dict:
        ok, command, err = self._extract_auth(raw)
        if not ok:
            return {"ok": False, "error": err}
        if not command.strip():
            return {"ok": False, "error": "Empty command"}
        try:
            parts = shlex.split(command)
        except Exception:
            parts = command.split()
        if not parts:
            return {"ok": False, "error": "Empty command"}

        action = parts[0].lower()
        try:
            handlers = {
                "ping":        lambda: {"ok": True, "result": "Pong"},
                "accountlist": lambda: self._cmd_account_list(),
                "add":         lambda: self._cmd_add(command),
                "launch":      lambda: self._cmd_launch(parts),
                "joinuser":    lambda: self._cmd_join_user(parts),
                "autorejoin":  lambda: self._cmd_auto_rejoin(parts),
                "getstatus":   lambda: self._cmd_get_status(),
            }
            handler = handlers.get(action)
            if handler:
                return handler()
            return {
                "ok": False,
                "error": "Unknown command",
                "supported": self.SUPPORTED_COMMANDS,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _extract_auth(self, raw: str):
        message = str(raw or "").strip()
        s = self._get_settings()
        req_pw = bool(s.get("websocket_require_password", False))

        if not req_pw:
            return True, message, None

        stored = self._get_password()
        if not stored:
            return False, "", "Password required but not configured in Developer settings"

        if "|" not in message:
            return False, "", "Auth format: AUTH <password> | <command>"

        auth_seg, cmd_seg = message.split("|", 1)
        auth_seg = auth_seg.strip()
        cmd_seg = cmd_seg.strip()

        try:
            auth_parts = shlex.split(auth_seg)
        except Exception:
            auth_parts = auth_seg.split()

        if len(auth_parts) < 2 or auth_parts[0].lower() != "auth":
            return False, "", "Auth format: AUTH <password> | <command>"

        provided = " ".join(auth_parts[1:])
        if not secrets.compare_digest(provided, stored):
            return False, "", "Authentication failed"

        return True, cmd_seg, None

    def _cmd_account_list(self) -> dict:
        try:
            names = sorted(str(n) for n in self.manager.accounts.keys())
        except Exception:
            names = []
        return {
            "ok": True,
            "result": {"action": "AccountList", "accounts": names, "count": len(names)},
        }

    def _cmd_add(self, command_text: str) -> dict:
        payload = str(command_text or "").strip()
        if len(payload) <= 3:
            return {"ok": False, "error": "Usage: Add <cookie> [cookie2 ...]"}

        cookie_payload = payload[3:].strip()
        cookies = self._parse_cookies(cookie_payload)
        if not cookies:
            return {"ok": False, "error": "No cookies provided"}

        max_c = self._get_max_cookies()
        if len(cookies) > max_c:
            return {"ok": False, "error": f"Too many cookies (max {max_c})"}

        imported, failed = [], []
        for cookie in cookies:
            if not cookie:
                failed.append({"cookie": "", "error": "Empty cookie"})
                continue
            if len(cookie) > 4096:
                failed.append({"cookie": cookie[:32] + "...", "error": "Cookie too long"})
                continue
            try:
                success, username = self.manager.import_cookie_account(cookie)
                if success and username:
                    imported.append(username)
                else:
                    failed.append({"cookie": cookie[:32] + "...", "error": "Import failed"})
            except Exception as exc:
                failed.append({"cookie": cookie[:32] + "...", "error": str(exc)})

        if not imported:
            return {"ok": False, "error": "Failed to import any accounts", "failed": failed}

        if self._refresh_ui:
            try:
                self._refresh_ui()
            except Exception:
                pass

        print(f"[SUCCESS] WebSocket: imported {len(imported)} account(s)")
        return {
            "ok": True,
            "result": {
                "action": "Add",
                "imported": imported,
                "imported_count": len(imported),
                "failed_count": len(failed),
            },
            "failed": failed,
        }

    def _cmd_launch(self, parts: list) -> dict:
        if len(parts) < 3:
            return {"ok": False, "error": "Usage: Launch <account> <place_id> [private_server] [job_id]"}

        account = parts[1]
        place_id = str(parts[2]).strip()
        private_srv = str(parts[3]).strip() if len(parts) >= 4 else ""
        job_id = str(parts[4]).strip() if len(parts) >= 5 else ""

        if account not in self.manager.accounts:
            return {"ok": False, "error": f"Account not found: {account}"}
        if not place_id.isdigit():
            return {"ok": False, "error": "place_id must be numeric"}

        s = self._get_settings()
        launcher = s.get("roblox_launcher", "default")
        custom = s.get("custom_launcher_path", "")
        launched = self.manager.launch_roblox(account, place_id, private_srv, launcher, job_id, custom)

        if launched:
            print(f"[SUCCESS] WebSocket: launched {account} in place {place_id}")
            return {
                "ok": True,
                "result": {
                    "action": "Launch",
                    "account": account,
                    "place_id": place_id,
                    "private_server": private_srv,
                    "job_id": job_id,
                },
            }
        return {"ok": False, "error": f"Failed to launch {account}"}

    def _cmd_join_user(self, parts: list) -> dict:
        if len(parts) < 3:
            return {"ok": False, "error": "Usage: JoinUser <account> <target_username>"}

        account = parts[1]
        target_user = parts[2]

        if account not in self.manager.accounts:
            return {"ok": False, "error": f"Account not found: {account}"}

        user_id = RobloxAPI.get_user_id_from_username(target_user)
        if not user_id:
            return {"ok": False, "error": f"Roblox user not found: {target_user}"}

        acc_data = self.manager.accounts.get(account)
        cookie = acc_data.get("cookie") if isinstance(acc_data, dict) else None
        if not cookie:
            return {"ok": False, "error": f"No cookie for account: {account}"}

        presence = RobloxAPI.get_player_presence(user_id, cookie)
        if not presence:
            return {"ok": False, "error": "Failed to fetch player presence"}
        if not presence.get("in_game"):
            return {
                "ok": False,
                "error": f"{target_user} is not currently in a game",
                "status": presence.get("last_location", "Unknown"),
            }

        place_id = str(presence.get("place_id", "") or "")
        game_id = str(presence.get("game_id",  "") or "")
        if not place_id:
            return {"ok": False, "error": "Missing place_id in presence data"}

        s = self._get_settings()
        launcher = s.get("roblox_launcher", "default")
        custom = s.get("custom_launcher_path", "")
        launched = self.manager.launch_roblox(account, place_id, "", launcher, game_id, custom)

        if launched:
            print(f"[SUCCESS] WebSocket: {account} joined {target_user} in place {place_id}")
            return {
                "ok": True,
                "result": {
                    "action": "JoinUser",
                    "account": account,
                    "target_user": target_user,
                    "place_id": place_id,
                    "job_id": game_id,
                },
            }
        return {"ok": False, "error": f"Failed to join {target_user} with {account}"}

    def _cmd_auto_rejoin(self, parts: list) -> dict:
        if len(parts) < 3:
            return {"ok": False, "error": "Usage: AutoRejoin <start|stop> <account>"}

        mode = parts[1].lower()
        account = parts[2]

        if account not in self.manager.accounts:
            return {"ok": False, "error": f"Account not found: {account}"}

        if mode == "start":
            if account not in self._ar_configs:
                return {"ok": False, "error": f"No auto-rejoin config for: {account}"}
            if account not in self._ar_workers or not self._ar_workers[account].is_alive():
                worker = _ar.AutoRejoinWorker(account, self._ar_configs[account], self.manager)
                worker.start()
                self._ar_workers[account] = worker
            return {"ok": True, "result": {"action": "AutoRejoin", "mode": "start", "account": account}}

        if mode == "stop":
            worker = self._ar_workers.get(account)
            if worker:
                worker.stop()
                self._ar_workers.pop(account, None)
            return {"ok": True, "result": {"action": "AutoRejoin", "mode": "stop", "account": account}}

        return {"ok": False, "error": "mode must be 'start' or 'stop'"}

    def _cmd_get_status(self) -> dict:
        data = []
        try:
            pids = [
                p.info["pid"]
                for p in psutil.process_iter(["pid", "name"])
                if (p.info.get("name") or "").lower() == "robloxplayerbeta.exe"
            ]
            for pid in pids:
                uid = _get_user_id_from_pid(pid)
                if uid:
                    username = RobloxAPI.get_username_from_user_id(uid)
                    data.append({"pid": pid, "username": username or None, "user_id": uid})
                else:
                    data.append({"pid": pid, "username": None})
        except Exception as exc:
            print(f"[WARNING] GetStatus scan error: {exc}")
        return {"ok": True, "action": "GetStatus", "result": data}

    def _get_settings(self) -> dict:
        try:
            return self._settings_fn()
        except Exception:
            return {}

    def _get_port(self) -> int:
        try:
            return int(self._get_settings().get("websocket_port", 7963))
        except Exception:
            return 7963

    def _get_max_message_len(self) -> int:
        try:
            return max(0, int(self._get_settings().get("websocket_max_message_length", 4096)))
        except Exception:
            return 4096

    def _get_max_cookies(self) -> int:
        try:
            return max(1, int(self._get_settings().get("websocket_max_add_cookies", 25)))
        except Exception:
            return 25

    def _get_password(self) -> str:
        try:
            return str(self.manager.get_secure_setting("websocket_password", "") or "")
        except Exception:
            return ""

    @staticmethod
    def _parse_cookies(text: str) -> list[str]:
        text = str(text or "").strip()
        if not text:
            return []
        if "_|WARNING:-" in text:
            parts = text.split("_|WARNING:-")
            return ["_|WARNING:-" + p.strip() for p in parts if p.strip()]
        return [c.strip() for c in text.split() if c.strip()]



def _get_user_id_from_pid(pid: int) -> str | None:
    try:
        proc = psutil.Process(pid)
        create_utc = datetime.fromtimestamp(
            proc.create_time(), tz=timezone.utc
        ).replace(tzinfo=None)
        logs_dir = os.path.join(os.getenv("LOCALAPPDATA", ""), "Roblox", "logs")
        if not os.path.isdir(logs_dir):
            return None
        candidates = []
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
                    content = fh.read(50000)
                if "userid:" in content:
                    uid = content.split("userid:")[1].split(",")[0].strip()
                    if uid.isdigit():
                        return uid
            except Exception:
                continue
    except Exception:
        pass
    return None