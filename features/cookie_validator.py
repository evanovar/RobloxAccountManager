"""
features/cookie_validator.py
Core logic for cookie validation.
"""

from __future__ import annotations

import threading
import requests
import time
from typing import Callable


def is_flagged(data: dict) -> bool:
    return isinstance(data, dict) and data.get("valid") is False


def flag_invalid(manager, username: str) -> None:
    data = manager.accounts.get(username)
    if not isinstance(data, dict):
        return
    if data.get("valid") is not False:
        data["valid"] = False
        try:
            manager.save_accounts()
        except Exception as exc:
            print(f"[WARNING] cookie_validator: could not persist flag for {username}: {exc}")


def _check(cookie: str) -> bool:
    try:
        r = requests.get(
            "https://users.roblox.com/v1/users/authenticated",
            headers={"Cookie": f".ROBLOSECURITY={cookie}"},
            timeout=8,
        )
        return r.status_code == 200
    except Exception:
        return False

class CookieValidator:
    def __init__(
        self,
        manager,
        on_result: Callable[[str, bool], None],
        on_done: Callable[[], None] | None = None,
        delay_sec: float = 1.5,
    ):
        self._manager = manager
        self._on_result = on_result
        self._on_done = on_done or (lambda: None)
        self._delay = max(0.5, float(delay_sec))
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="CookieValidator"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()

    def _run(self) -> None:
        # print("[INFO] Cookie validation started.")
        accounts_snapshot = list(self._manager.accounts.items())
        checked = 0

        for username, data in accounts_snapshot:
            if self._stop_evt.is_set():
                break
            if not isinstance(data, dict):
                continue

            if is_flagged(data):
                # print(f"[INFO] Cookie validation: skipping {username} (already flagged invalid)")
                continue

            cookie = data.get("cookie", "")
            if not cookie:
                continue

            is_valid = _check(cookie)
            checked += 1

            if not is_valid:
                flag_invalid(self._manager, username)
                print(f"[WARNING] Cookie validation: {username} has an invalid/expired cookie.")
            else:
                data["valid"] = True

            try:
                self._on_result(username, is_valid)
            except Exception as exc:
                print(f"[WARNING] cookie_validator on_result error: {exc}")

            if not self._stop_evt.wait(timeout=self._delay):
                pass

        # print(f"[INFO] Cookie validation complete. Checked {checked} account(s).")
        try:
            self._on_done()
        except Exception:
            pass
