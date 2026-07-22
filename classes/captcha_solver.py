"""
2captcha integration for Arkose Labs FunCaptcha (used by Roblox).
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests

# From https://apis.rbxcdn.com/captcha/v1/metadata
ROBLOX_LOGIN_PUBLIC_KEY = "476068BF-9607-4799-B53D-966BE98E2B81"
ROBLOX_SIGNUP_PUBLIC_KEY = "A2A14B1D-1AF3-C791-9BBC-EE33CC7A0A6F"
ROBLOX_GENERIC_CHALLENGE_PUBLIC_KEY = "CC30DB96-0C88-4DEB-86E5-6601927ACBB4"

# Back-compat alias used by older code
ROBLOX_FUNCAPTCHA_PUBLIC_KEY = ROBLOX_LOGIN_PUBLIC_KEY
ROBLOX_FUNCAPTCHA_SURL = "https://roblox-api.arkoselabs.com"
ROBLOX_LOGIN_URL = "https://www.roblox.com/login"

_FALLBACK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)


def get_browser_user_agent(browser_path: str | None = None) -> str:
    """Return a Chrome UA matching the installed browser when possible."""
    candidates: list[str] = []
    if browser_path:
        candidates.append(browser_path)

    for env_name, suffix in (
        ("ProgramFiles", os.path.join("Google", "Chrome", "Application", "chrome.exe")),
        ("ProgramFiles(x86)", os.path.join("Google", "Chrome", "Application", "chrome.exe")),
        ("LOCALAPPDATA", os.path.join("Google", "Chrome", "Application", "chrome.exe")),
    ):
        root = os.environ.get(env_name)
        if root:
            candidates.append(os.path.join(root, suffix))

    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            import win32api

            info = win32api.GetFileVersionInfo(path, "\\")
            major = win32api.HIWORD(info["FileVersionMS"])
            if major:
                return (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    f"Chrome/{major}.0.0.0 Safari/537.36"
                )
        except Exception:
            continue

    return _FALLBACK_USER_AGENT


DEFAULT_USER_AGENT = get_browser_user_agent()

# Kept as a compatibility symbol for older integrations. API keys must be
# supplied by the user in Settings → Captcha Solver; none is bundled.
DEFAULT_TWOCAPTCHA_KEY = ""


class TwoCaptchaSolver:
    """Solve Arkose Labs FunCaptcha via 2captcha createTask / getTaskResult."""

    CREATE_URL = "https://api.2captcha.com/createTask"
    RESULT_URL = "https://api.2captcha.com/getTaskResult"
    BALANCE_URL = "https://api.2captcha.com/getBalance"

    def __init__(self, api_key: str, polling_interval: float = 5.0, timeout: float = 180.0):
        self.api_key = (api_key or "").strip()
        self.polling_interval = polling_interval
        self.timeout = timeout
        self.session = requests.Session()
        self.last_error_code = ""
        self.last_error_description = ""

    def _set_error(self, code: str, description: str) -> None:
        self.last_error_code = str(code or "")
        self.last_error_description = str(description or "")

    def get_balance(self) -> Optional[float]:
        if not self.api_key:
            return None
        try:
            resp = self.session.post(
                self.BALANCE_URL,
                json={"clientKey": self.api_key},
                timeout=15,
            )
            data = resp.json()
            if data.get("errorId") == 0:
                return float(data.get("balance", 0))
            print(f"[2captcha] balance error: {data}")
        except Exception as e:
            print(f"[2captcha] balance request failed: {e}")
        return None

    def solve_funcaptcha(
        self,
        public_key: str,
        page_url: str = ROBLOX_LOGIN_URL,
        surl: str = ROBLOX_FUNCAPTCHA_SURL,
        blob: str | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> Optional[str]:
        """
        Solve a FunCaptcha challenge.

        Returns the captcha token string, or None on failure.
        """
        self._set_error("", "")
        if not self.api_key:
            self._set_error("NO_API_KEY", "No 2captcha API key is configured")
            print("[2captcha] No API key configured")
            return None

        public_key = (public_key or ROBLOX_LOGIN_PUBLIC_KEY).strip()
        if not public_key:
            self._set_error("MISSING_PUBLIC_KEY", "FunCaptcha public key is missing")
            print("[2captcha] Missing FunCaptcha public key")
            return None

        if not blob:
            print("[2captcha] WARNING: No dataExchangeBlob — solve may fail or be rejected by Roblox")

        task: dict = {
            "type": "FunCaptchaTaskProxyless",
            "websiteURL": page_url or ROBLOX_LOGIN_URL,
            "websitePublicKey": public_key,
            "userAgent": user_agent or DEFAULT_USER_AGENT,
        }
        if surl:
            # 2captcha expects subdomain host only
            surl_clean = surl.replace("https://", "").replace("http://", "").split("/")[0]
            task["funcaptchaApiJSSubdomain"] = surl_clean
        if blob:
            task["data"] = json.dumps({"blob": blob})

        print(
            f"[2captcha] Creating FunCaptcha task "
            f"(pk={public_key}, blob={'yes' if blob else 'no'}, surl={surl})"
        )
        try:
            create_resp = self.session.post(
                self.CREATE_URL,
                json={"clientKey": self.api_key, "task": task},
                timeout=30,
            )
            create_resp.raise_for_status()
            create_data = create_resp.json()
        except Exception as e:
            self._set_error("CREATE_TASK_REQUEST_FAILED", str(e))
            print(f"[2captcha] createTask failed: {e}")
            return None

        if create_data.get("errorId") not in (0, None):
            self._set_error(
                create_data.get("errorCode") or f"ERROR_{create_data.get('errorId')}",
                create_data.get("errorDescription") or str(create_data),
            )
            print(f"[2captcha] createTask error: {create_data}")
            return None

        task_id = create_data.get("taskId")
        if not task_id:
            self._set_error("NO_TASK_ID", "2captcha createTask returned no taskId")
            print(f"[2captcha] No taskId in response: {create_data}")
            return None

        print(f"[2captcha] Task {task_id} created, polling for solution...")
        deadline = time.time() + self.timeout
        time.sleep(min(self.polling_interval, 8.0))

        while time.time() < deadline:
            try:
                result_resp = self.session.post(
                    self.RESULT_URL,
                    json={"clientKey": self.api_key, "taskId": task_id},
                    timeout=30,
                )
                result_resp.raise_for_status()
                result_data = result_resp.json()
            except Exception as e:
                print(f"[2captcha] getTaskResult failed: {e}")
                time.sleep(self.polling_interval)
                continue

            if result_data.get("errorId") not in (0, None):
                self._set_error(
                    result_data.get("errorCode") or f"ERROR_{result_data.get('errorId')}",
                    result_data.get("errorDescription") or str(result_data),
                )
                print(f"[2captcha] getTaskResult error: {result_data}")
                return None

            status = result_data.get("status")
            if status == "ready":
                solution = result_data.get("solution") or {}
                token = solution.get("token") or solution.get("text")
                if token:
                    print(f"[2captcha] Solved captcha (token length={len(token)})")
                    return token
                self._set_error("EMPTY_SOLUTION", "2captcha returned ready without a token")
                print(f"[2captcha] Ready but no token: {result_data}")
                return None
            if status == "processing":
                time.sleep(self.polling_interval)
                continue

            print(f"[2captcha] Unexpected result: {result_data}")
            time.sleep(self.polling_interval)

        self._set_error("TIMEOUT", "Timed out waiting for a 2captcha result")
        print("[2captcha] Timed out waiting for captcha solution")
        return None


def get_2captcha_key_from_settings(manager=None) -> str:
    """
    Resolve the user-supplied 2captcha API key from GUI settings.

    ``manager`` remains in the signature for compatibility with existing
    callers, but the GUI settings file is the single source of truth.
    """
    try:
        from features.account_actions import load_ui_settings

        settings = load_ui_settings()
        key = settings.get("twocaptcha_api_key", "") or ""
        if key:
            return str(key).strip()
    except Exception:
        pass

    return ""
