"""
features/cookie_validator.py
Core logic for cookie validation.
"""

from __future__ import annotations

import threading
import requests
import time
from typing import Callable

VALID = "valid"
INVALID = "invalid"
UNKNOWN = "unknown"
_VALIDATION_URL = "https://users.roblox.com/v1/users/authenticated"
_VALIDATION_ATTEMPTS = 2
_RETRY_DELAY = 0.75

def is_flagged(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if "cookie_valid" in data:
        return data.get("cookie_valid") is False
    return data.get("valid") is False


def _set_status(manager, username: str, status: str) -> bool:
    data = manager.accounts.get(username)
    if not isinstance(data, dict):
        return False

    value = {
        VALID: True,
        INVALID: False,
        UNKNOWN: None,
    }.get(status)
    changed = (
        "cookie_valid" not in data
        or data.get("cookie_valid") is not value
        or "valid" in data
    )
    if not changed:
        return False

    account_lock = getattr(manager, "_accounts_lock", None)
    if account_lock is None:
        data["cookie_valid"] = value
        data.pop("valid", None)
    else:
        with account_lock:
            data["cookie_valid"] = value
            data.pop("valid", None)
    return True


def _check(cookie: str, session: requests.Session) -> tuple[str, str, bool]:
    last_detail = "No response from Roblox."
    authentication_failures = 0

    for attempt in range(_VALIDATION_ATTEMPTS):
        try:
            response = session.get(
                _VALIDATION_URL,
                headers={"Cookie": f".ROBLOSECURITY={cookie}"},
                timeout=8,
            )
            if response.status_code == 200:
                return VALID, "Authenticated successfully.", False
            if response.status_code in (401, 403):
                authentication_failures += 1
                last_detail = (
                    f"Roblox returned HTTP {response.status_code}."
                )
            elif response.status_code == 429:
                last_detail = "Roblox rate limited validation with HTTP 429."
                return UNKNOWN, last_detail, True
            else:
                last_detail = f"Roblox returned HTTP {response.status_code}."
        except requests.RequestException as exc:
            last_detail = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            last_detail = f"{type(exc).__name__}: {exc}"

        if attempt + 1 < _VALIDATION_ATTEMPTS:
            time.sleep(_RETRY_DELAY)

    if authentication_failures == _VALIDATION_ATTEMPTS:
        return INVALID, last_detail, False
    return UNKNOWN, last_detail, False


class CookieValidator:
    def __init__(
        self,
        manager,
        on_result: Callable[[str, str], None],
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
        account_lock = getattr(self._manager, "_accounts_lock", None)
        if account_lock is None:
            accounts_snapshot = list(self._manager.accounts.items())
        else:
            with account_lock:
                accounts_snapshot = list(self._manager.accounts.items())
        changed = False
        checked = 0
        invalid = 0
        unknown = 0
        rate_limited = False
        session = requests.Session()

        try:
            for username, data in accounts_snapshot:
                if self._stop_evt.is_set():
                    break
                if not isinstance(data, dict):
                    continue

                cookie = data.get("cookie", "")
                if not cookie:
                    continue

                status, detail, rate_limited = _check(cookie, session)
                changed = _set_status(self._manager, username, status) or changed
                checked += 1

                if status == INVALID:
                    invalid += 1
                    print(
                        f"[WARNING] Cookie validation: {username} received "
                        f"repeated unauthorized responses."
                    )
                elif status == UNKNOWN:
                    unknown += 1
                    print(
                        f"[WARNING] Cookie validation: could not verify {username}. "
                        f"{detail} The account was not marked invalid."
                    )

                try:
                    self._on_result(username, status)
                except Exception as exc:
                    print(f"[WARNING] cookie_validator on_result error: {exc}")

                if rate_limited:
                    print(
                        "[WARNING] Cookie validation paused because Roblox "
                        "returned HTTP 429."
                    )
                    break
                self._stop_evt.wait(timeout=self._delay)
        finally:
            session.close()

        if changed:
            try:
                self._manager.save_accounts()
            except Exception as exc:
                print(f"[WARNING] Cookie validation statuses could not be saved: {exc}")

        print(
            f"[INFO] Cookie validation complete: checked {checked}, "
            f"invalid {invalid}, unknown {unknown}."
        )

        try:
            self._on_done()
        except Exception:
            pass
