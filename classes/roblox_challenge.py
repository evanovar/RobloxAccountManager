"""
Roblox login challenge chain: proof-of-work → FunCaptcha (2captcha) → redeem login.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Optional

import requests

from .captcha_solver import (
    DEFAULT_USER_AGENT,
    ROBLOX_FUNCAPTCHA_SURL,
    ROBLOX_LOGIN_PUBLIC_KEY,
    TwoCaptchaSolver,
)

POW_PUZZLE_URL = "https://apis.roblox.com/proof-of-work-service/v1/pow-puzzle"
CHALLENGE_CONTINUE_URL = "https://apis.roblox.com/challenge/v1/continue"
LOGIN_URL = "https://auth.roblox.com/v2/login"


def _b64_json(obj: dict) -> str:
    return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode("utf-8")).decode("ascii")


def _decode_meta(meta_b64: str) -> dict:
    if not meta_b64:
        return {}
    try:
        return json.loads(base64.b64decode(meta_b64).decode("utf-8", errors="replace"))
    except Exception:
        try:
            return json.loads(meta_b64)
        except Exception:
            return {}


def solve_pow_puzzle(artifacts: dict | str) -> str:
    """
    Rivest time-lock style puzzle: square A, T times, mod N.
    artifacts: {N, A, T} (ints or numeric strings)
    """
    if isinstance(artifacts, str):
        artifacts = json.loads(artifacts)
    n = int(artifacts["N"])
    a = int(artifacts["A"])
    t = int(artifacts["T"])
    x = a % n
    # Pure Python is fine for T~4e5 and 1024-bit N (~1s)
    for _ in range(t):
        x = (x * x) % n
    return str(x)


class RobloxChallengeLogin:
    """Username/password login that solves POW + FunCaptcha challenges."""

    def __init__(self, twocaptcha_key: str = "", user_agent: str = DEFAULT_USER_AGENT):
        self.session = requests.Session()
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://www.roblox.com",
                "Referer": "https://www.roblox.com/login",
            }
        )
        self.solver = TwoCaptchaSolver(twocaptcha_key) if twocaptcha_key else None
        self.csrf: str = ""
        self.last_error_code: str = ""

    def log(self, msg: str) -> None:
        print(msg)

    def refresh_csrf(self) -> str:
        try:
            r = self.session.post(LOGIN_URL, json={}, timeout=15)
            token = r.headers.get("x-csrf-token") or ""
            if token:
                self.csrf = token
                self.session.headers["X-CSRF-TOKEN"] = token
            return self.csrf
        except Exception as e:
            self.log(f"[Challenge] CSRF refresh failed: {e}")
            return self.csrf

    def _login_request(self, username: str, password: str, challenge_headers: dict | None = None) -> requests.Response:
        if not self.csrf:
            self.refresh_csrf()
        headers = {}
        if challenge_headers:
            headers.update(challenge_headers)
        resp = self.session.post(
            LOGIN_URL,
            json={"ctype": "Username", "cvalue": username, "password": password},
            headers=headers,
            timeout=20,
        )
        # CSRF rotate
        if resp.status_code == 403 and resp.headers.get("x-csrf-token"):
            self.csrf = resp.headers["x-csrf-token"]
            self.session.headers["X-CSRF-TOKEN"] = self.csrf
            headers = dict(headers)
            resp = self.session.post(
                LOGIN_URL,
                json={"ctype": "Username", "cvalue": username, "password": password},
                headers=headers,
                timeout=20,
            )
        return resp

    def _parse_challenge(self, resp: requests.Response) -> Optional[dict]:
        cid = resp.headers.get("rblx-challenge-id")
        ctype = (resp.headers.get("rblx-challenge-type") or "").lower()
        cmeta = resp.headers.get("rblx-challenge-metadata") or ""
        if not cid and not ctype:
            # continue endpoint may return body challenge
            try:
                body = resp.json()
                if body.get("challengeId") or body.get("challengeType"):
                    meta_raw = body.get("challengeMetadata") or "{}"
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
                    return {
                        "id": body.get("challengeId") or "",
                        "type": (body.get("challengeType") or "").lower(),
                        "metadata": meta,
                        "metadata_b64": _b64_json(meta) if isinstance(meta, dict) else "",
                    }
            except Exception:
                pass
            return None
        return {
            "id": cid or "",
            "type": ctype,
            "metadata": _decode_meta(cmeta),
            "metadata_b64": cmeta,
        }

    def solve_proof_of_work(self, challenge: dict) -> Optional[dict]:
        """Solve POW and return updated challenge metadata including redemptionToken."""
        meta = dict(challenge.get("metadata") or {})
        session_id = meta.get("sessionId") or meta.get("sessionID")
        if not session_id:
            self.log("[Challenge] POW missing sessionId")
            return None

        self.log(f"[Challenge] Fetching POW puzzle for session {session_id[:12]}...")
        try:
            pz = self.session.get(
                POW_PUZZLE_URL,
                params={"sessionID": session_id},
                timeout=20,
            )
            data = pz.json()
        except Exception as e:
            self.log(f"[Challenge] POW puzzle fetch failed: {e}")
            return None

        if pz.status_code != 200:
            self.log(f"[Challenge] POW puzzle status {pz.status_code}: {data}")
            return None

        artifacts = data.get("artifacts")
        self.log(f"[Challenge] Solving POW (puzzleType={data.get('puzzleType')})...")
        t0 = time.time()
        try:
            solution = solve_pow_puzzle(artifacts)
        except Exception as e:
            self.log(f"[Challenge] POW solve error: {e}")
            return None
        self.log(f"[Challenge] POW solved in {time.time() - t0:.2f}s")

        try:
            verify = self.session.post(
                POW_PUZZLE_URL,
                json={"sessionID": session_id, "solution": solution},
                timeout=20,
            )
            vdata = verify.json()
        except Exception as e:
            self.log(f"[Challenge] POW verify failed: {e}")
            return None

        if not vdata.get("answerCorrect"):
            self.log(f"[Challenge] POW answer rejected: {vdata}")
            return None

        redemption = vdata.get("redemptionToken") or ""
        self.log(f"[Challenge] POW redemption token ok")
        meta["redemptionToken"] = redemption
        return meta

    def continue_challenge(self, challenge_id: str, challenge_type: str, metadata: dict) -> tuple[int, dict, Optional[dict]]:
        """
        POST challenge/continue.
        Returns (status, body_dict, next_challenge_or_None)
        """
        if not self.csrf:
            self.refresh_csrf()
        payload = {
            "challengeId": challenge_id,
            "challengeType": challenge_type,
            "challengeMetadata": json.dumps(metadata, separators=(",", ":")),
        }
        try:
            resp = self.session.post(CHALLENGE_CONTINUE_URL, json=payload, timeout=20)
        except Exception as e:
            self.log(f"[Challenge] continue request failed: {e}")
            return 0, {"error": str(e)}, None

        if resp.status_code == 403 and resp.headers.get("x-csrf-token"):
            self.csrf = resp.headers["x-csrf-token"]
            self.session.headers["X-CSRF-TOKEN"] = self.csrf
            resp = self.session.post(CHALLENGE_CONTINUE_URL, json=payload, timeout=20)

        body: dict[str, Any] = {}
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:500]}

        next_ch = None
        # Body-embedded next challenge (common after POW)
        if body.get("challengeType") or body.get("challengeId"):
            meta_raw = body.get("challengeMetadata") or "{}"
            try:
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
            except Exception:
                meta = {}
            next_ch = {
                "id": body.get("challengeId") or challenge_id,
                "type": (body.get("challengeType") or "").lower(),
                "metadata": meta,
                "metadata_b64": _b64_json(meta) if isinstance(meta, dict) else "",
            }
        else:
            next_ch = self._parse_challenge(resp)

        return resp.status_code, body, next_ch

    def solve_captcha_challenge(self, challenge: dict) -> Optional[dict]:
        """Solve FunCaptcha via 2captcha; return full continue metadata."""
        if not self.solver:
            self.log("[Challenge] No 2captcha key — cannot solve captcha")
            return None

        meta = dict(challenge.get("metadata") or {})
        blob = meta.get("dataExchangeBlob") or meta.get("blob")
        public_key = (
            meta.get("publicKey")
            or meta.get("captchaPublicKey")
            or ROBLOX_LOGIN_PUBLIC_KEY
        )
        unified = (
            meta.get("unifiedCaptchaId")
            or meta.get("unifiedCaptchaID")
            or challenge.get("id")
            or ""
        )
        action = meta.get("actionType") or "Login"

        if not blob:
            self.log("[Challenge] Captcha challenge missing dataExchangeBlob")
            return None

        self.log(
            f"[Challenge] Solving FunCaptcha via 2captcha "
            f"(pk={public_key}, blob_len={len(blob)}, unified={str(unified)[:24]}...)"
        )

        # A Roblox dataExchangeBlob is short-lived and single-use. Submitting
        # several provider tasks with the same blob only creates stale tasks;
        # callers must restart the Roblox challenge to retry with a fresh blob.
        token = self.solver.solve_funcaptcha(
            public_key=public_key,
            page_url="https://www.roblox.com/login",
            surl=ROBLOX_FUNCAPTCHA_SURL,
            blob=blob,
            user_agent=self.user_agent,
        )

        if not token:
            self.last_error_code = self.solver.last_error_code or "CAPTCHA_SOLVE_FAILED"
            detail = self.solver.last_error_description or "No token returned"
            self.log(
                f"[Challenge] 2captcha could not solve FunCaptcha: "
                f"{self.last_error_code}: {detail}"
            )
            return None

        # Keep the original challenge metadata shape and fill in the token.
        # Roblox often rejects minimal {unifiedCaptchaId, captchaToken, actionType}.
        full = dict(meta)
        full["captchaToken"] = token
        full["unifiedCaptchaId"] = unified
        full["actionType"] = action
        if blob and "dataExchangeBlob" not in full:
            full["dataExchangeBlob"] = blob
        return full

    def login(self, username: str, password: str, max_steps: int = 6) -> tuple[bool, str, str]:
        """
        Full login with challenge handling.
        Returns (ok, cookie_or_error, resolved_username)
        """
        self.refresh_csrf()
        self.log(f"[Challenge] Logging in as {username}...")

        resp = self._login_request(username, password)
        if resp.status_code == 200:
            cookie = self.session.cookies.get(".ROBLOSECURITY", "") or ""
            if cookie:
                self.log("[Challenge] Login succeeded without challenge")
                return True, cookie, username
            # cookie might be in set-cookie with different parsing
            cookie = self._extract_cookie(resp)
            if cookie:
                return True, cookie, username

        challenge = self._parse_challenge(resp)
        if not challenge:
            # bad credentials etc.
            try:
                err = resp.json()
            except Exception:
                err = resp.text[:300]
            self.log(f"[Challenge] Login failed ({resp.status_code}): {err}")
            return False, f"Login failed ({resp.status_code}): {err}", ""

        # Walk the challenge chain
        last_captcha_meta = None
        last_challenge_id = challenge.get("id") or ""
        last_challenge_type = challenge.get("type") or ""

        for step in range(max_steps):
            ctype = (challenge.get("type") or "").lower()
            cid = challenge.get("id") or last_challenge_id
            self.log(f"[Challenge] Step {step + 1}: type={ctype} id={cid[:40]}")

            if ctype == "proofofwork":
                pow_meta = self.solve_proof_of_work(challenge)
                if not pow_meta:
                    return False, "Failed to solve proof-of-work verification", ""
                status, body, next_ch = self.continue_challenge(cid, "proofofwork", pow_meta)
                self.log(f"[Challenge] POW continue status={status} next={ (next_ch or {}).get('type') }")

                # Continue may return a nested captcha challenge
                next_type = ((next_ch or {}).get("type") or "").lower()
                if next_type == "captcha":
                    challenge = next_ch
                    last_challenge_id = next_ch.get("id") or cid
                    last_challenge_type = "captcha"
                    continue

                # Empty / no next challenge → redeem login with POW token
                redeem = self._redeem_login(
                    username, password, cid, "proofofwork", pow_meta
                )
                if redeem[0]:
                    return redeem
                if redeem[2]:  # nested challenge from redeem
                    challenge = redeem[2]
                    last_challenge_id = challenge.get("id") or cid
                    last_challenge_type = (challenge.get("type") or "").lower()
                    continue
                return False, redeem[1], ""

            if ctype == "captcha":
                cap_meta = self.solve_captcha_challenge(challenge)
                if not cap_meta:
                    code = self.last_error_code or "CAPTCHA_SOLVE_FAILED"
                    return (
                        False,
                        f"FunCaptcha solve failed ({code}). "
                        "A retry must use a fresh Roblox challenge.",
                        "",
                    )
                last_captcha_meta = cap_meta
                status, body, next_ch = self.continue_challenge(cid, "captcha", cap_meta)
                self.log(f"[Challenge] Captcha continue status={status} body={str(body)[:200]}")
                # Redeem with captcha token
                redeem = self._redeem_login(username, password, cid, "captcha", cap_meta)
                if redeem[0]:
                    return redeem
                if redeem[2]:
                    challenge = redeem[2]
                    continue
                if next_ch and next_ch.get("type"):
                    challenge = next_ch
                    continue
                return False, redeem[1], ""

            # Unknown challenge type
            self.log(f"[Challenge] Unsupported challenge type: {ctype}")
            return False, f"Unsupported challenge type: {ctype}", ""

        return False, "Too many challenge steps", ""

    def _redeem_login(
        self, username: str, password: str, challenge_id: str, challenge_type: str, metadata: dict
    ) -> tuple[bool, str, Optional[dict]]:
        """
        Retry login with challenge redemption headers.
        Returns (ok, cookie_or_error, next_challenge_or_None)
        """
        headers = {
            "rblx-challenge-id": challenge_id,
            "rblx-challenge-type": challenge_type,
            "rblx-challenge-metadata": _b64_json(metadata),
        }
        self.log(f"[Challenge] Redeeming login with type={challenge_type}...")
        resp = self._login_request(username, password, headers)
        if resp.status_code == 200:
            cookie = self.session.cookies.get(".ROBLOSECURITY", "") or self._extract_cookie(resp)
            if cookie:
                self.log("[Challenge] Login redeemed successfully")
                return True, cookie, None
            return False, "Login 200 but no .ROBLOSECURITY cookie", None

        next_ch = self._parse_challenge(resp)
        if next_ch:
            self.log(
                f"[Challenge] Redeem produced new challenge type={next_ch.get('type')}"
            )
            return False, f"New challenge: {next_ch.get('type')}", next_ch

        try:
            err = resp.json()
        except Exception:
            err = resp.text[:300]
        return False, f"Redeem failed ({resp.status_code}): {err}", None

    @staticmethod
    def _extract_cookie(resp: requests.Response) -> str:
        # requests usually puts it in session; also check raw headers
        for k, v in resp.cookies.items():
            if k == ".ROBLOSECURITY":
                return v
        sc = resp.headers.get("Set-Cookie") or ""
        if ".ROBLOSECURITY=" in sc:
            part = sc.split(".ROBLOSECURITY=", 1)[1]
            return part.split(";", 1)[0]
        return ""


def login_with_challenges(
    username: str,
    password: str,
    twocaptcha_key: str,
) -> tuple[bool, str, str]:
    """Convenience wrapper. Returns (ok, cookie_or_error, username)."""
    client = RobloxChallengeLogin(twocaptcha_key=twocaptcha_key)
    return client.login(username, password)
