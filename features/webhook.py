"""
features/webhook.py
Core logic discord webhook integration.
"""

from __future__ import annotations

import collections
import os
import subprocess
import tempfile
import threading
import sys


import time
import requests
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Callable


_APP_FOOTER = "Evanovar's Roblox Account Manager"
_AR_EVENTS: list[tuple[str, str, int]] = [
    ("started monitoring", "Auto Rejoin Started",    0x3498DB),
    ("rejoining",          "Account Disconnected!",  0xF39C12),
    ("rejoin successful",  "Rejoin Successful",      0x2ECC71),
    ("launch failed",      "Launch Failed",          0xE74C3C),
    ("max retries",        "Auto Rejoin Stopped",    0xE74C3C),
    ("stopped",            "Auto Rejoin Stopped",    0xE74C3C),
    ("disconnect",         "Account Disconnected!",  0xF39C12),
]

_COLOR_PRIO: list[int] = [0xE74C3C, 0xF39C12, 0x2ECC71, 0x3498DB, 0x9B59B6]

CONSOLE_COLORS: dict[str, str] = {
    "[ERROR]":       "#EF5350",
    "[SUCCESS]":     "#66BB6A",
    "[WARNING]":     "#FFA726",
    "[INFO]":        "#5BB8FF",
    "[Auto-Rejoin]": "#AB47BC",
}


def send_embed(url: str, title: str, description: str, color: int, ping_user_id: str | None = None,) -> None:
    def _post():
        try:
            now = datetime.now(timezone.utc)
            payload = {
                "content": f"<@{ping_user_id}>" if ping_user_id else "",
                "embeds": [{
                    "title": title,
                    "description": description,
                    "color": color,
                    "footer": {"text": _APP_FOOTER},
                    "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                }],
                "attachments": [],
            }
            requests.post(url, json=payload, timeout=10)
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True, name="webhook-embed").start()


def send_screenshot(url: str, caption: str = "") -> None:
    def _do():
        tmp_path: str | None = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp.name
            tmp.close()
            ps_cmd = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
                "$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                "$b=New-Object System.Drawing.Bitmap($s.Width,$s.Height); "
                "$g=[System.Drawing.Graphics]::FromImage($b); "
                "$g.CopyFromScreen($s.Location,[System.Drawing.Point]::Empty,$s.Size); "
                f"$b.Save('{tmp_path}',[System.Drawing.Imaging.ImageFormat]::Png); "
                "$g.Dispose();$b.Dispose()"
            )
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                return
            with open(tmp_path, "rb") as fh:
                image_bytes = fh.read()
            if not image_bytes:
                return
            with BytesIO(image_bytes) as stream:
                requests.post(
                    url,
                    data={"content": caption},
                    files={"file": ("screenshot.png", stream, "image/png")},
                    timeout=15,
                )
        except Exception:
            pass
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    threading.Thread(target=_do, daemon=True, name="webhook-screenshot").start()

_ss_stop = threading.Event()
_ss_thread: threading.Thread | None = None

def start_screenshot_loop(get_cfg: Callable[[], dict]) -> None:
    global _ss_thread
    if _ss_thread and _ss_thread.is_alive():
        return
    _ss_stop.clear()
    _state = {"last_sent": 0.0}

    def _loop():
        while not _ss_stop.wait(30):
            try:
                cfg = get_cfg()
                if not cfg.get("enabled"):
                    continue
                url = str(cfg.get("url", "") or "").strip()
                if not url or not cfg.get("screenshot_enabled"):
                    continue
                interval_min = max(1, int(cfg.get("screenshot_interval_minutes", 60)))
                now = time.time()
                if now - _state["last_sent"] >= interval_min * 60:
                    _state["last_sent"] = now
                    send_screenshot(url, caption="Scheduled screenshot")
            except Exception:
                pass

    _ss_thread = threading.Thread(target=_loop, daemon=True, name="WebhookScreenshot")
    _ss_thread.start()


def stop_screenshot_loop() -> None:
    """Signal the screenshot loop to stop."""
    global _ss_thread
    _ss_stop.set()
    _ss_thread = None



class WebhookStdoutInterceptor:
    def __init__(self, orig, get_cfg: Callable[[], dict]):
        self._orig = orig
        self._get_cfg = get_cfg
        self._buf = ""

        self._pending: list[tuple[str, str, int]] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

        self._console_queue: collections.deque = collections.deque(maxlen=2000)

    def write(self, text: str) -> None:
        if self._orig is not None:
            self._orig.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._handle(line.rstrip("\r"))

    def flush(self) -> None:
        if self._orig is not None:
            self._orig.flush()

    def fileno(self) -> int:
        try:
            return self._orig.fileno()
        except Exception:
            return -1

    def _handle(self, line: str) -> None:
        self._push_console(line)
        if not line.strip():
            return
        try:
            cfg = self._get_cfg()
            if not cfg.get("enabled"):
                return
            url = str(cfg.get("url", "") or "").strip()
            if not url:
                return

            ts = datetime.now().strftime("%H:%M:%S")
            lw = line.lower()

            if line.startswith("[Auto-Rejoin]") and cfg.get("log_auto_rejoin", True):
                for keyword, title, color in _AR_EVENTS:
                    if keyword in lw:
                        self._send_ar_embed(url, title, line, color, cfg)
                        return
                if cfg.get("log_auto_rejoin_console", False):
                    self._enqueue(ts, line, 0x9B59B6, url, cfg)
                return

            if cfg.get("log_everything", False):
                self._enqueue(ts, line, 0x5865F2, url, cfg)
                return

            FILTERS = [
                ("[ERROR]",   cfg.get("log_errors",   True),  0xE74C3C),
                ("[SUCCESS]", cfg.get("log_success",  True),  0x2ECC71),
                ("[WARNING]", cfg.get("log_warnings", True),  0xF39C12),
                ("[INFO]",    cfg.get("log_info",     False), 0x3498DB),
            ]
            for prefix, enabled, color in FILTERS:
                if enabled and line.startswith(prefix):
                    self._enqueue(ts, line, color, url, cfg)
                    return
        except Exception:
            pass

    def _push_console(self, line: str) -> None:
        if not line.strip():
            return
        ts = datetime.now().strftime("%H:%M:%S")
        text = f"[{ts}] {line}"
        color: str | None = None
        for prefix, col in CONSOLE_COLORS.items():
            if line.startswith(prefix):
                color = col
                break
        self._console_queue.append((text, color))

    def _enqueue(self, ts: str, line: str, color: int, url: str, cfg: dict) -> None:
        with self._lock:
            self._pending.append((ts, line, color))
            if len(self._pending) >= 10:
                self._flush_locked(url, cfg)
                return
            if self._timer is None:
                self._timer = threading.Timer(3.0, self._flush_timer, args=(url, cfg))
                self._timer.daemon = True
                self._timer.start()

    def _flush_timer(self, url: str, cfg: dict) -> None:
        with self._lock:
            self._flush_locked(url, cfg)

    def _flush_locked(self, url: str, cfg: dict) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if not self._pending:
            return
        lines = list(self._pending)
        self._pending.clear()

        colors_in = [c for _, _, c in lines]
        color = next((c for c in _COLOR_PRIO if c in colors_in), 0x5865F2)

        ping: str | None = None
        if cfg.get("enable_ping") and cfg.get("ping_on_error"):
            uid = str(cfg.get("ping_user_id", "") or "").strip()
            if uid and any(ln.startswith("[ERROR]") for _, ln, _ in lines):
                ping = uid

        now = datetime.now(timezone.utc)
        body = "\n".join(f"[{ts}] {ln}" for ts, ln, _ in lines)
        payload = {
            "content": f"<@{ping}>" if ping else "",
            "embeds": [{
                "title": "**Log**",
                "description": f"```{body[:3900]}```",
                "color": color,
                "footer": {"text": _APP_FOOTER},
                "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }],
            "attachments": [],
        }

        def _post():
            try:
                requests.post(url, json=payload, timeout=10)
            except Exception:
                pass
        threading.Thread(target=_post, daemon=True, name="webhook-batch").start()

    @staticmethod
    def _send_ar_embed(url: str, title: str, line: str, color: int, cfg: dict) -> None:
        desc = line
        m = re.match(r'\[Auto-Rejoin\]\s*\[([^\]]+)\]\s*(.*)', line)
        if m:
            desc = f"**{m.group(1)}**\n{m.group(2)}"

        ping: str | None = None
        if cfg.get("enable_ping") and cfg.get("ping_user_id") and color == 0xE74C3C:
            ping = str(cfg.get("ping_user_id", "") or "").strip() or None

        now = datetime.now(timezone.utc)
        payload = {
            "content": f"<@{ping}>" if ping else "",
            "embeds": [{
                "title": title,
                "description": desc,
                "color": color,
                "footer": {"text": _APP_FOOTER},
                "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }],
            "attachments": [],
        }

        def _post():
            try:
                requests.post(url, json=payload, timeout=10)
            except Exception:
                pass
        threading.Thread(target=_post, daemon=True, name="webhook-ar").start()


class WebhookStderrInterceptor:
    def __init__(self, orig, stdout_interceptor):
        self._orig = orig
        self._stdout = stdout_interceptor
        self._buf = ""

    def write(self, text: str) -> None:
        if self._orig is not None:
            self._orig.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                if not any(line.startswith(prefix) for prefix in ("[ERROR]", "[WARNING]", "[INFO]", "[SUCCESS]")):
                    line = f"[ERROR] {line}"
                if self._stdout is not None:
                    self._stdout.write(line + "\n")

    def flush(self) -> None:
        if self._orig is not None:
            self._orig.flush()

    def fileno(self) -> int:
        try:
            return self._orig.fileno()
        except Exception:
            return -1


def install_console_capture(get_cfg: Callable[[], dict]):
    stdout = sys.stdout
    if isinstance(stdout, WebhookStdoutInterceptor):
        stdout._get_cfg = get_cfg
    else:
        stdout = WebhookStdoutInterceptor(
            stdout if stdout is not None else getattr(sys, "__stdout__", None),
            get_cfg,
        )
        sys.stdout = stdout

    stderr = sys.stderr
    if isinstance(stderr, WebhookStderrInterceptor):
        stderr._stdout = stdout
    else:
        stderr = WebhookStderrInterceptor(
            stderr if stderr is not None else getattr(sys, "__stderr__", None),
            stdout,
        )
        sys.stderr = stderr

    return stdout, stderr


class WebhookStderrInterceptor:
    def __init__(self, orig, stdout_interceptor):
        self._orig = orig
        self._stdout = stdout_interceptor
        self._buf = ""

    def write(self, text: str) -> None:
        if self._orig is not None:
            self._orig.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                if not any(line.startswith(prefix) for prefix in ("[ERROR]", "[WARNING]", "[INFO]", "[SUCCESS]")):
                    line = f"[ERROR] {line}"
                if self._stdout is not None:
                    self._stdout.write(line + "\n")

    def flush(self) -> None:
        if self._orig is not None:
            self._orig.flush()

    def fileno(self) -> int:
        try:
            return self._orig.fileno()
        except Exception:
            return -1


def install_console_capture(get_cfg: Callable[[], dict]):
    stdout = sys.stdout
    if isinstance(stdout, WebhookStdoutInterceptor):
        stdout._get_cfg = get_cfg
    else:
        stdout = WebhookStdoutInterceptor(
            stdout if stdout is not None else getattr(sys, "__stdout__", None),
            get_cfg,
        )
        sys.stdout = stdout

    stderr = sys.stderr
    if isinstance(stderr, WebhookStderrInterceptor):
        stderr._stdout = stdout
    else:
        stderr = WebhookStderrInterceptor(
            stderr if stderr is not None else getattr(sys, "__stderr__", None),
            stdout,
        )
        sys.stderr = stderr

    return stdout, stderr