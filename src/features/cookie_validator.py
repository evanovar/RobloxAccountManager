"""
features/cookie_validator.py
Core logic for cookie validation.
"""

from __future__ import annotations

import threading
from contextlib import nullcontext
import requests
import time
from typing import Callable

VALID = "valid"
INVALID = "invalid"
UNKNOWN = "unknown"
_VALIDATION_URL = "https://users.roblox.com/v1/users/authenticated"
_VALIDATION_ATTEMPTS = 2
_RETRY_DELAY = 0.75
DEFAULT_DELAY = 1.5
MIN_DELAY = 0.5
MAX_DELAY = 60.0


def validation_enabled(settings: dict) -> bool:
    return bool(settings.get("validate_cookies_on_startup", True))


def get_validation_delay(settings: dict) -> float:
    try:
        delay = float(settings.get("cookie_validation_delay_seconds", DEFAULT_DELAY))
    except (TypeError, ValueError):
        return DEFAULT_DELAY
    if delay != delay:
        return DEFAULT_DELAY
    return max(MIN_DELAY, min(MAX_DELAY, delay))


def is_flagged(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if "cookie_valid" in data:
        return data.get("cookie_valid") is False
    return data.get("valid") is False


def _set_status(manager, username: str, status: str, *, checked_cookie=None, checked_record=None) -> bool:
    if status not in (VALID, INVALID):
        return False
    account_lock = getattr(manager, "_accounts_lock", None)
    with account_lock if account_lock is not None else nullcontext():
        data = manager.accounts.get(username)
        if not isinstance(data, dict) or is_flagged(data):
            return False
        # A response for an old cookie must not invalidate a replacement account.
        if checked_record is not None and data is not checked_record:
            return False
        if checked_cookie is not None and data.get("cookie") != checked_cookie:
            return False
        value = status == VALID
        if data.get("cookie_valid") is value and "valid" not in data:
            return False
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

    def stop(self, join_timeout: float = 2.0) -> bool:
        self._stop_evt.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(join_timeout)))
        return not bool(thread and thread.is_alive())

    def _run(self) -> None:
        account_lock = getattr(self._manager, "_accounts_lock", None)
        with account_lock if account_lock is not None else nullcontext():
            accounts_snapshot = list(self._manager.accounts)
        changed = False
        checked = 0
        invalid = 0
        unknown = 0
        rate_limited = False
        session = requests.Session()

        try:
            for username in accounts_snapshot:
                if self._stop_evt.is_set():
                    break
                with account_lock if account_lock is not None else nullcontext():
                    data = self._manager.accounts.get(username)
                    if not isinstance(data, dict) or is_flagged(data):
                        continue
                    cookie = data.get("cookie", "")
                if not cookie:
                    continue

                status, detail, rate_limited = _check(cookie, session)
                updated = _set_status(self._manager, username, status,
                                      checked_cookie=cookie, checked_record=data)
                changed = updated or changed
                if updated and status == INVALID:
                    changed = not self._save_statuses()
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

                if not self._stop_evt.is_set():
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
            self._save_statuses()

        print(
            f"[INFO] Cookie validation complete: checked {checked}, "
            f"invalid {invalid}, unknown {unknown}."
        )

        if not self._stop_evt.is_set():
            try:
                self._on_done()
            except Exception:
                pass

    def _save_statuses(self) -> bool:
        try:
            self._manager.save_accounts()
            return True
        except Exception as exc:
            print(f"[WARNING] Cookie validation statuses could not be saved: {exc}")
            return False
