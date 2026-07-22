"""
Roblox username/password login with automatic FunCaptcha solving via 2captcha.

Strategy:
1. Open browser login page
2. Inject fetch/XHR interceptor that captures rblx-challenge-* headers from login
3. Submit credentials
4. When a captcha challenge is captured (or captcha UI is visible), solve with 2captcha
5. POST challenge/continue with captcha token, then retry login with redemption headers
6. Extract .ROBLOSECURITY cookie and save account
"""

from __future__ import annotations

import base64
import json
import time
import traceback
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from .captcha_solver import (
    DEFAULT_USER_AGENT,
    ROBLOX_FUNCAPTCHA_SURL,
    ROBLOX_LOGIN_PUBLIC_KEY,
    ROBLOX_LOGIN_URL,
    TwoCaptchaSolver,
    get_browser_user_agent,
)

# ---------------------------------------------------------------------------
# Injected into the page BEFORE login click so we capture challenge headers
# ---------------------------------------------------------------------------
_INTERCEPTOR_JS = r"""
return (function() {
  if (window.__ramChallengeHook) return true;
  window.__ramChallengeHook = true;
  window.__ramChallenges = window.__ramChallenges || [];
  window.__ramLoginResults = window.__ramLoginResults || [];
  window.__ramLastLoginStatus = null;

  function pushChallenge(headers, url, status, body) {
    try {
      var h = {};
      if (headers && typeof headers.forEach === 'function') {
        headers.forEach(function(v, k) { h[String(k).toLowerCase()] = v; });
      } else if (headers && typeof headers === 'object') {
        Object.keys(headers).forEach(function(k) {
          h[String(k).toLowerCase()] = headers[k];
        });
      }
      var cid = h['rblx-challenge-id'] || '';
      var ctype = h['rblx-challenge-type'] || '';
      var cmeta = h['rblx-challenge-metadata'] || '';
      if (!cid && !ctype && !cmeta) return;
      var entry = {
        id: cid || '',
        type: (ctype || '').toLowerCase(),
        metadata_b64: cmeta || '',
        metadata: null,
        url: url || '',
        status: status || 0,
        body: (body || '').slice(0, 500),
        ts: Date.now()
      };
      if (cmeta) {
        try {
          entry.metadata = JSON.parse(atob(cmeta));
        } catch (e1) {
          try { entry.metadata = JSON.parse(cmeta); } catch (e2) {}
        }
      }
      // de-dupe by id+type
      var exists = window.__ramChallenges.some(function(c) {
        return c.id && c.id === entry.id && c.type === entry.type;
      });
      if (!exists) {
        window.__ramChallenges.push(entry);
        console.log('[RAM] captured challenge', entry.type, entry.id);
      }
    } catch (e) {
      console.log('[RAM] pushChallenge error', e);
    }
  }

  // ---- fetch hook ----
  var origFetch = window.fetch;
  window.fetch = function() {
    var args = arguments;
    var input = args[0];
    var url = (typeof input === 'string') ? input : (input && input.url) || '';
    return origFetch.apply(this, args).then(function(response) {
      try {
        var u = url || response.url || '';
        if (/auth\.roblox\.com|apis\.roblox\.com|challenge|login|captcha|arkose/i.test(u)) {
          var clone = response.clone();
          clone.text().then(function(text) {
            pushChallenge(response.headers, u, response.status, text);
            if (/\/v2\/login/i.test(u)) {
              window.__ramLoginResults.push({
                status: response.status,
                url: u,
                body: (text || '').slice(0, 500),
                ts: Date.now()
              });
              window.__ramLastLoginStatus = response.status;
            }
          }).catch(function(){});
        }
      } catch (e) {}
      return response;
    });
  };

  // ---- XHR hook ----
  var OrigXHR = window.XMLHttpRequest;
  function HookedXHR() {
    var xhr = new OrigXHR();
    var _url = '';
    var _open = xhr.open;
    xhr.open = function(method, url) {
      _url = url || '';
      return _open.apply(xhr, arguments);
    };
    xhr.addEventListener('load', function() {
      try {
        if (/auth\.roblox\.com|apis\.roblox\.com|challenge|login|captcha|arkose/i.test(_url)) {
          var headers = {};
          var raw = xhr.getAllResponseHeaders() || '';
          raw.split(/\r?\n/).forEach(function(line) {
            var idx = line.indexOf(':');
            if (idx > 0) {
              headers[line.slice(0, idx).trim().toLowerCase()] = line.slice(idx + 1).trim();
            }
          });
          ['rblx-challenge-id','rblx-challenge-type','rblx-challenge-metadata','x-csrf-token'].forEach(function(name) {
            try {
              var v = xhr.getResponseHeader(name);
              if (v) headers[name] = v;
            } catch (e) {}
          });
          pushChallenge(headers, _url, xhr.status, xhr.responseText || '');
          if (/\/v2\/login/i.test(_url)) {
            window.__ramLoginResults.push({
              status: xhr.status,
              url: _url,
              body: String(xhr.responseText || '').slice(0, 500),
              ts: Date.now()
            });
            window.__ramLastLoginStatus = xhr.status;
          }
        }
      } catch (e) {}
    });
    return xhr;
  }
  HookedXHR.prototype = OrigXHR.prototype;
  window.XMLHttpRequest = HookedXHR;

  return true;
})();
"""

_DETECT_JS = r"""
return (function() {
  var bodyText = (document.body && document.body.innerText) ? document.body.innerText : '';
  var bodyLower = bodyText.toLowerCase();
  var iframes = Array.from(document.querySelectorAll('iframe')).map(function(f) {
    return {
      src: f.src || '',
      id: f.id || '',
      name: f.name || '',
      title: f.title || '',
      w: f.offsetWidth || 0,
      h: f.offsetHeight || 0
    };
  });
  var captchaIframe = iframes.find(function(f) {
    var s = (f.src || '').toLowerCase();
    return s.indexOf('arkose') !== -1 || s.indexOf('funcaptcha') !== -1
      || s.indexOf('arkoselabs') !== -1
      || (s.indexOf('captcha') !== -1 && s.indexOf('download') === -1);
  });
  // large iframes often hold the captcha even with delayed src
  var bigIframe = iframes.find(function(f) {
    return (f.w >= 200 && f.h >= 200) && f.id !== 'downloadInstallerIFrame';
  });

  var pkey = null, blob = null, surl = null;
  var el = document.querySelector('[data-pkey]');
  if (el) pkey = el.getAttribute('data-pkey');

  var html = document.documentElement.innerHTML || '';
  var m;
  m = html.match(/data-pkey=["']([A-Fa-f0-9-]{30,})["']/i); if (m) pkey = pkey || m[1];
  m = html.match(/publicKey["']?\s*[:=]\s*["']([A-Fa-f0-9-]{30,})["']/i); if (m) pkey = pkey || m[1];
  m = html.match(/["']pk["']\s*[:=]\s*["']([A-Fa-f0-9-]{30,})["']/i); if (m) pkey = pkey || m[1];
  m = html.match(/dataExchangeBlob["']?\s*[:=]\s*["']([^"']{20,})["']/); if (m) blob = m[1];
  m = html.match(/["']blob["']\s*:\s*["']([^"']{20,})["']/); if (m) blob = blob || m[1];

  function parseFrame(src) {
    try {
      var u = new URL(src);
      pkey = pkey || u.searchParams.get('pk') || u.searchParams.get('public_key');
      blob = blob || u.searchParams.get('data[blob]') || u.searchParams.get('blob');
      if (u.host) surl = u.protocol + '//' + u.host;
    } catch (e) {}
  }
  if (captchaIframe && captchaIframe.src) parseFrame(captchaIframe.src);
  if (bigIframe && bigIframe.src) parseFrame(bigIframe.src);

  var verifyWords = [
    'start puzzle', 'verify', 'captcha', 'are you a human', 'security check',
    'prove you are', 'just a moment', 'confirm you are', 'complete the challenge',
    'verification', 'puzzle'
  ];
  var verifyText = verifyWords.some(function(w) { return bodyLower.indexOf(w) !== -1; });

  // Roblox challenge modal / captcha containers
  var challengeNodes = document.querySelectorAll(
    '#challenge-container, #challenge-dom-container, [id*="challenge" i], [class*="challenge" i], ' +
    '#FunCaptcha, .captcha-container, [id*="captcha" i], [class*="Captcha"], [class*="arkose" i], ' +
    '[data-testid*="challenge" i], [data-testid*="captcha" i]'
  );
  var visibleChallenge = false;
  for (var i = 0; i < challengeNodes.length; i++) {
    var n = challengeNodes[i];
    var r = n.getBoundingClientRect();
    if (r.width > 50 && r.height > 50) { visibleChallenge = true; break; }
    // modal may be zero size host with iframe child
    if ((n.id || '').toLowerCase().indexOf('challenge') !== -1) {
      visibleChallenge = true; break;
    }
  }

  var dialogs = Array.from(document.querySelectorAll('[role="dialog"], .modal-dialog, .modal.show, .modal.in'))
    .map(function(d) {
      return {
        text: (d.innerText || '').trim().slice(0, 200),
        cls: String(d.className || '').slice(0, 80),
        id: d.id || ''
      };
    });

  var captchaVisible = !!(captchaIframe || visibleChallenge || (verifyText && bigIframe) ||
    (verifyText && bodyLower.indexOf('log in') !== -1 && bodyLower.indexOf('puzzle') !== -1));

  // Intercepted challenges from our hook
  var challenges = window.__ramChallenges ? window.__ramChallenges.slice() : [];
  var loginResults = window.__ramLoginResults ? window.__ramLoginResults.slice() : [];

  return {
    url: location.href,
    captchaVisible: captchaVisible,
    verifyText: verifyText,
    visibleChallenge: visibleChallenge,
    pkey: pkey,
    blob: blob,
    surl: surl,
    iframeSrc: captchaIframe ? captchaIframe.src : (bigIframe ? bigIframe.src : null),
    iframes: iframes,
    dialogs: dialogs,
    bodyText: bodyText.slice(0, 600),
    challenges: challenges,
    loginResults: loginResults,
    lastLoginStatus: window.__ramLastLoginStatus || null,
    hookReady: !!window.__ramChallengeHook
  };
})();
"""


def _build_fill_script(username: str, password: str) -> str:
    return f"""
    (function() {{
        function setNativeValue(el, value) {{
            var proto = Object.getPrototypeOf(el);
            var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(el, value);
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
        function tryFill(attemptsLeft) {{
            var userEl = document.getElementById('login-username')
              || document.querySelector('input[name="username"]')
              || document.querySelector('#login-username');
            var passEl = document.getElementById('login-password')
              || document.querySelector('input[type="password"]');
            var btn = document.getElementById('login-button')
              || document.querySelector('button[type="submit"]');
            if (userEl && passEl && btn) {{
                setNativeValue(userEl, {json.dumps(username)});
                setNativeValue(passEl, {json.dumps(password)});
                setTimeout(function() {{ btn.click(); }}, 400);
                return;
            }}
            if (attemptsLeft > 0) {{
                setTimeout(function() {{ tryFill(attemptsLeft - 1); }}, 250);
            }}
        }}
        tryFill(40);
    }})();
    """


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


def _encode_meta(meta: dict) -> str:
    return base64.b64encode(
        json.dumps(meta, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def _is_logged_in_url(url: str) -> bool:
    u = (url or "").lower()
    if any(x in u for x in ("/login", "/signup", "/createaccount")):
        return False
    return any(
        p in u
        for p in (
            "/home", "/games", "/catalog", "/avatar", "/discover",
            "/friends", "/profile", "/groups", "/develop", "/create",
            "/transactions", "/users/",
        )
    )


def _challenge_blob(meta: dict) -> Optional[str]:
    if not meta:
        return None
    return (
        meta.get("dataExchangeBlob")
        or meta.get("dataExchangeBlob".lower())
        or meta.get("blob")
        or (meta.get("sharedParameters") or {}).get("dataExchangeBlob")
    )


def _challenge_unified_id(meta: dict) -> str:
    if not meta:
        return ""
    return (
        meta.get("unifiedCaptchaId")
        or meta.get("unifiedCaptchaID")
        or meta.get("captchaId")
        or ""
    )


def _challenge_public_key(meta: dict) -> Optional[str]:
    if not meta:
        return None
    return (
        meta.get("publicKey")
        or meta.get("captchaPublicKey")
        or meta.get("funCaptchaPublicKey")
        or (meta.get("sharedParameters") or {}).get("publicKey")
    )


class CaptchaAwareLogin:
    """Browser login helper with 2captcha FunCaptcha solving."""

    def __init__(
        self,
        driver,
        twocaptcha_key: str,
        username: str = "",
        password: str = "",
        timeout: float = 180.0,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        self.driver = driver
        self.username = username
        self.password = password
        self.timeout = timeout
        self.on_status = on_status or (lambda msg: print(msg))
        self.solver = TwoCaptchaSolver(twocaptcha_key) if twocaptcha_key else None
        # Roblox commonly reuses one ID while changing proofofwork -> captcha.
        # Track both fields so the captcha step is not discarded as a duplicate.
        self._handled_challenges: set[tuple[str, str]] = set()
        self._captcha_attempts = 0
        self._max_captcha_attempts = 4
        self._solving = False
        self.user_agent = DEFAULT_USER_AGENT
        try:
            detected_ua = self.driver.execute_script("return navigator.userAgent || ''")
            if detected_ua:
                self.user_agent = str(detected_ua)
        except Exception:
            pass

    def log(self, msg: str) -> None:
        self.on_status(msg)

    def install_hooks(self) -> None:
        try:
            ok = self.driver.execute_script(_INTERCEPTOR_JS)
            self.log(f"[Captcha] Challenge interceptor installed: {ok}")
        except Exception as e:
            self.log(f"[Captcha] Failed to install interceptor: {e}")

    def enable_network_capture(self) -> None:
        try:
            self.driver.execute_cdp_cmd("Network.enable", {})
        except Exception:
            pass
        # Enable performance log buffer for header scraping
        try:
            self.driver.execute_cdp_cmd(
                "Network.setExtraHTTPHeaders",
                {"headers": {"Accept-Language": "en-US,en;q=0.9"}},
            )
        except Exception:
            pass
        self.install_hooks()

    def _ingest_perf_challenges(self) -> list[dict]:
        """Parse Selenium performance logs for rblx-challenge-* response headers."""
        found: list[dict] = []
        try:
            logs = self.driver.get_log("performance")
        except Exception:
            return found

        for entry in logs:
            try:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method") != "Network.responseReceived":
                    continue
                resp = (msg.get("params") or {}).get("response") or {}
                url = resp.get("url") or ""
                headers = {str(k).lower(): v for k, v in (resp.get("headers") or {}).items()}
                cid = headers.get("rblx-challenge-id")
                ctype = headers.get("rblx-challenge-type")
                cmeta = headers.get("rblx-challenge-metadata")
                if not (cid or ctype or cmeta):
                    continue
                meta = _decode_meta(cmeta or "")
                found.append(
                    {
                        "id": cid or "",
                        "type": (ctype or "").lower(),
                        "metadata_b64": cmeta or "",
                        "metadata": meta,
                        "url": url,
                        "status": resp.get("status") or 0,
                        "body": "",
                        "ts": int(time.time() * 1000),
                        "source": "cdp",
                    }
                )
            except Exception:
                continue
        return found

    def detect(self) -> dict:
        try:
            info = self.driver.execute_script(_DETECT_JS) or {}
            if not isinstance(info, dict):
                info = {}
        except Exception as e:
            self.log(f"[Captcha] detect failed: {e}")
            info = {}

        # Merge CDP-captured challenges into the page store + result
        cdp_challenges = self._ingest_perf_challenges()
        if cdp_challenges:
            existing = info.get("challenges") or []
            existing_ids = {c.get("id") for c in existing if c.get("id")}
            for ch in cdp_challenges:
                if ch.get("id") and ch["id"] not in existing_ids:
                    existing.append(ch)
                    existing_ids.add(ch["id"])
                    # also push into page store for consistency
                    try:
                        self.driver.execute_script(
                            """
                            if (!window.__ramChallenges) window.__ramChallenges = [];
                            var ch = arguments[0];
                            var exists = window.__ramChallenges.some(function(c){ return c.id === ch.id; });
                            if (!exists) window.__ramChallenges.push(ch);
                            """,
                            ch,
                        )
                    except Exception:
                        pass
            info["challenges"] = existing
            for ch in cdp_challenges:
                if (ch.get("type") or "") == "captcha":
                    self.log(
                        f"[Captcha] CDP captured captcha challenge id={ch.get('id','')[:40]} "
                        f"blob={'yes' if _challenge_blob(ch.get('metadata') or {}) else 'no'}"
                    )
        return info

    # alias used by account_manager.wait_for_login
    def detect_captcha_dom(self) -> dict:
        return self.detect()

    @staticmethod
    def _challenge_key(challenge: dict) -> tuple[str, str]:
        return (
            str(challenge.get("id") or ""),
            str(challenge.get("type") or "").lower(),
        )

    def _is_handled(self, challenge: dict) -> bool:
        return self._challenge_key(challenge) in self._handled_challenges

    def _pick_captcha_challenge(self, info: dict) -> Optional[dict]:
        challenges = info.get("challenges") or []
        # Prefer captcha type, newest first
        captcha_ones = [
            c for c in challenges
            if (c.get("type") or "").lower() == "captcha"
            and c.get("id")
            and not self._is_handled(c)
        ]
        if captcha_ones:
            return captcha_ones[-1]

        # Any unhandled challenge that has a captcha blob in metadata
        for c in reversed(challenges):
            cid = c.get("id") or ""
            if self._is_handled(c):
                continue
            meta = c.get("metadata") or {}
            if isinstance(meta, str):
                meta = _decode_meta(meta)
            if _challenge_blob(meta) or _challenge_unified_id(meta):
                c = dict(c)
                c["metadata"] = meta
                c["type"] = c.get("type") or "captcha"
                return c
        return None

    def _get_csrf_from_page(self) -> str:
        try:
            token = self.driver.execute_async_script(
                """
                const done = arguments[arguments.length - 1];
                fetch('https://auth.roblox.com/v2/login', {
                  method: 'POST', credentials: 'include',
                  headers: {'Content-Type': 'application/json'},
                  body: '{}'
                }).then(r => done(r.headers.get('x-csrf-token') || ''))
                  .catch(() => done(''));
                """
            )
            return token or ""
        except Exception:
            return ""

    def _pick_any_challenge(self, info: dict, preferred: str | None = None) -> Optional[dict]:
        challenges = info.get("challenges") or []
        if preferred:
            for c in reversed(challenges):
                if (c.get("type") or "").lower() == preferred and not self._is_handled(c):
                    return c
        for c in reversed(challenges):
            if c.get("id") and not self._is_handled(c):
                return c
        return None

    def solve_and_continue(self, dom_info: dict | None = None) -> bool:
        """Handle verification (POW) and FunCaptcha when shown in the browser."""
        if self._solving:
            return False
        if self._captcha_attempts >= self._max_captcha_attempts:
            self.log("[Captcha] Max solve attempts reached")
            return False

        info = dom_info or self.detect()
        challenge = (
            self._pick_any_challenge(info, "proofofwork")
            or self._pick_captcha_challenge(info)
            or self._pick_any_challenge(info)
        )

        if not challenge:
            self.log("[Captcha] No challenge headers yet — probing login API...")
            self._probe_login_for_challenge()
            info = self.detect()
            challenge = (
                self._pick_any_challenge(info, "proofofwork")
                or self._pick_captcha_challenge(info)
                or self._pick_any_challenge(info)
            )

        if not challenge:
            if info.get("verifyText") or info.get("captchaVisible"):
                self.log("[Captcha] Verification UI visible but no challenge id captured yet")
            return False

        challenge_id = challenge.get("id") or ""
        challenge_type = (challenge.get("type") or "").lower()
        meta = challenge.get("metadata") or {}
        if isinstance(meta, str):
            meta = _decode_meta(meta)
        if not meta and challenge.get("metadata_b64"):
            meta = _decode_meta(challenge.get("metadata_b64"))

        self._solving = True
        self._captcha_attempts += 1
        try:
            # Proof-of-work = Roblox "Verifying you are not a bot" screen
            if challenge_type == "proofofwork":
                self.log(f"[Captcha] Solving proof-of-work verification id={challenge_id[:40]}...")
                from .roblox_challenge import RobloxChallengeLogin

                client = RobloxChallengeLogin(twocaptcha_key="")
                for c in self.driver.get_cookies():
                    try:
                        client.session.cookies.set(c["name"], c["value"], domain=c.get("domain"))
                    except Exception:
                        pass
                pow_meta = client.solve_proof_of_work(
                    {"id": challenge_id, "type": "proofofwork", "metadata": meta}
                )
                if not pow_meta:
                    self.log("[Captcha] POW solve failed")
                    return False

                meta_json = json.dumps(pow_meta, separators=(",", ":"))
                cont = self.driver.execute_async_script(
                    """
                    const challengeId = arguments[0];
                    const metadataJson = arguments[1];
                    const done = arguments[arguments.length - 1];
                    function csrf() {
                      return fetch('https://auth.roblox.com/v2/login', {
                        method:'POST', credentials:'include',
                        headers:{'Content-Type':'application/json'}, body:'{}'
                      }).then(r => r.headers.get('x-csrf-token') || '');
                    }
                    csrf().then(function(token) {
                      return fetch('https://apis.roblox.com/challenge/v1/continue', {
                        method:'POST', credentials:'include',
                        headers:{'Content-Type':'application/json','X-CSRF-TOKEN': token||''},
                        body: JSON.stringify({
                          challengeId: challengeId,
                          challengeType: 'proofofwork',
                          challengeMetadata: metadataJson
                        })
                      }).then(async function(r) {
                        const text = await r.text();
                        let body = null;
                        try { body = JSON.parse(text); } catch(e) {}
                        done({status:r.status, body: body, text: text.slice(0,500)});
                      });
                    }).catch(e => done({status:0, text:String(e)}));
                    """,
                    challenge_id,
                    meta_json,
                )
                self.log(f"[Captcha] POW continue => {cont}")
                self._handled_challenges.add((challenge_id, "proofofwork"))

                body = (cont or {}).get("body") if isinstance(cont, dict) else None
                if isinstance(body, dict) and (body.get("challengeType") or "").lower() == "captcha":
                    next_meta_raw = body.get("challengeMetadata") or "{}"
                    try:
                        next_meta_obj = (
                            json.loads(next_meta_raw)
                            if isinstance(next_meta_raw, str)
                            else next_meta_raw
                        )
                    except Exception:
                        next_meta_obj = {}
                    ch = {
                        "id": body.get("challengeId") or challenge_id,
                        "type": "captcha",
                        "metadata": next_meta_obj,
                        "metadata_b64": _encode_challenge_metadata(next_meta_obj)
                        if isinstance(next_meta_obj, dict)
                        else "",
                        "ts": int(time.time() * 1000),
                    }
                    try:
                        self.driver.execute_script(
                            "if(!window.__ramChallenges) window.__ramChallenges=[];"
                            "window.__ramChallenges.push(arguments[0]);",
                            ch,
                        )
                    except Exception:
                        pass
                    self.log("[Captcha] POW done → captcha next")
                    # fall through by calling captcha path on next detect
                    self._solving = False
                    return self.solve_and_continue(self.detect())

                return self._continue_and_redeem(
                    challenge_id=challenge_id,
                    challenge_type="proofofwork",
                    continue_meta=pow_meta,
                )

            # FunCaptcha
            if not self.solver:
                self.log("[Captcha] No 2captcha API key — cannot solve captcha")
                return False

            blob = _challenge_blob(meta) or info.get("blob")
            public_key = (
                _challenge_public_key(meta) or info.get("pkey") or ROBLOX_LOGIN_PUBLIC_KEY
            )
            unified = _challenge_unified_id(meta) or challenge_id
            surl = info.get("surl") or ROBLOX_FUNCAPTCHA_SURL

            if not blob and challenge_type != "captcha":
                self.log(f"[Captcha] Unsupported challenge type '{challenge_type}'")
                return False

            self.log(
                f"[Captcha] Solving FunCaptcha attempt {self._captcha_attempts}/"
                f"{self._max_captcha_attempts} (pk={public_key}, blob={'yes' if blob else 'NO'})"
            )
            # Never submit the same short-lived blob twice. If this provider
            # task fails, the loop may create a new Roblox challenge instead.
            self._handled_challenges.add((challenge_id, "captcha"))
            token = self.solver.solve_funcaptcha(
                public_key=public_key,
                page_url="https://www.roblox.com/login",
                surl=surl or ROBLOX_FUNCAPTCHA_SURL,
                blob=blob,
                user_agent=self.user_agent,
            )
            if not token:
                code = self.solver.last_error_code or "CAPTCHA_SOLVE_FAILED"
                detail = self.solver.last_error_description or "No token returned"
                self.log(f"[Captcha] 2captcha failed: {code}: {detail}")
                return False

            continue_meta = dict(meta)
            continue_meta.update(
                {
                    "unifiedCaptchaId": unified,
                    "captchaToken": token,
                    "actionType": meta.get("actionType") or "Login",
                }
            )
            if challenge_id:
                ok = self._continue_and_redeem(
                    challenge_id=challenge_id,
                    challenge_type="captcha",
                    continue_meta=continue_meta,
                )
                return bool(ok)

            self._inject_token_dom(token)
            self._click_login_again()
            return False
        except Exception as e:
            self.log(f"[Captcha] solve_and_continue error: {e}")
            traceback.print_exc()
            return False
        finally:
            self._solving = False

    def _inject_token_dom(self, token: str) -> None:
        try:
            self.driver.execute_script(
                """
                const token = arguments[0];
                window.__ram_funcaptcha_token = token;
                document.querySelectorAll('input, textarea').forEach(function(el) {
                  var key = ((el.name||'')+' '+(el.id||'')+' '+(el.className||'')).toLowerCase();
                  if (/captcha|fc-token|arkose|fun-captcha|verification|challenge/.test(key)) {
                    el.value = token;
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                  }
                });
                // Arkose-style completion postMessages
                [
                  {eventId:'challenge-complete', payload:{sessionToken: token}},
                  {type:'FunCaptcha-Complete', token: token},
                  {msg:'verification_complete', token: token}
                ].forEach(function(p) {
                  try { window.postMessage(JSON.stringify(p), '*'); } catch(e) {}
                  try { window.postMessage(p, '*'); } catch(e) {}
                });
                """,
                token,
            )
        except Exception as e:
            self.log(f"[Captcha] DOM token inject failed: {e}")

    def _click_login_again(self) -> None:
        try:
            self.driver.execute_script(
                """
                var btn = document.getElementById('login-button')
                  || document.querySelector('button[type="submit"]');
                if (btn) btn.click();
                """
            )
        except Exception:
            pass

    def _probe_login_for_challenge(self) -> None:
        """Hit login API from page context so interceptor captures challenge headers."""
        if not self.username or not self.password:
            return
        try:
            result = self.driver.execute_async_script(
                """
                const username = arguments[0];
                const password = arguments[1];
                const done = arguments[arguments.length - 1];
                function csrf() {
                  return fetch('https://auth.roblox.com/v2/login', {
                    method:'POST', credentials:'include',
                    headers:{'Content-Type':'application/json'}, body:'{}'
                  }).then(r => r.headers.get('x-csrf-token') || '');
                }
                csrf().then(function(token) {
                  return fetch('https://auth.roblox.com/v2/login', {
                    method:'POST', credentials:'include',
                    headers:{
                      'Content-Type':'application/json',
                      'X-CSRF-TOKEN': token || ''
                    },
                    body: JSON.stringify({ctype:'Username', cvalue:username, password:password})
                  }).then(async function(r) {
                    const text = await r.text();
                    const headers = {};
                    r.headers.forEach((v,k) => headers[k.toLowerCase()] = v);
                    // also push into our store in case fetch hook missed header iteration
                    if (window.__ramChallenges && headers['rblx-challenge-id']) {
                      var meta = null;
                      try { meta = JSON.parse(atob(headers['rblx-challenge-metadata']||'')); } catch(e) {}
                      window.__ramChallenges.push({
                        id: headers['rblx-challenge-id'],
                        type: (headers['rblx-challenge-type']||'').toLowerCase(),
                        metadata_b64: headers['rblx-challenge-metadata']||'',
                        metadata: meta,
                        url: r.url,
                        status: r.status,
                        body: text.slice(0,500),
                        ts: Date.now()
                      });
                    }
                    done({status:r.status, headers:headers, body:text.slice(0,500)});
                  });
                }).catch(e => done({status:0, body:String(e), headers:{}}));
                """,
                self.username,
                self.password,
            )
            if isinstance(result, dict):
                self.log(
                    f"[Captcha] Probe login status={result.get('status')} "
                    f"challenge-type={ (result.get('headers') or {}).get('rblx-challenge-type') }"
                )
        except Exception as e:
            self.log(f"[Captcha] Probe login failed: {e}")

    def _continue_and_redeem(
        self,
        challenge_id: str,
        challenge_type: str,
        continue_meta: dict,
    ) -> bool:
        meta_json = json.dumps(continue_meta, separators=(",", ":"))
        meta_b64 = _encode_meta(continue_meta)
        self.log(f"[Captcha] Calling challenge/continue for {challenge_id}...")

        try:
            cont = self.driver.execute_async_script(
                """
                const challengeId = arguments[0];
                const challengeType = arguments[1];
                const metadataJson = arguments[2];
                const done = arguments[arguments.length - 1];

                function getCsrf() {
                  return fetch('https://auth.roblox.com/v2/logout', {
                    method: 'POST', credentials: 'include'
                  }).then(r => r.headers.get('x-csrf-token') || '')
                    .catch(() =>
                      fetch('https://auth.roblox.com/v2/login', {
                        method:'POST', credentials:'include',
                        headers:{'Content-Type':'application/json'}, body:'{}'
                      }).then(r => r.headers.get('x-csrf-token') || '')
                    );
                }

                getCsrf().then(function(csrf) {
                  return fetch('https://apis.roblox.com/challenge/v1/continue', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                      'Content-Type': 'application/json',
                      'X-CSRF-TOKEN': csrf || ''
                    },
                    body: JSON.stringify({
                      challengeId: challengeId,
                      challengeType: challengeType,
                      challengeMetadata: metadataJson
                    })
                  }).then(async function(r) {
                    const text = await r.text();
                    const headers = {};
                    r.headers.forEach((v,k) => headers[k.toLowerCase()] = v);
                    // capture nested challenges
                    if (headers['rblx-challenge-id'] && window.__ramChallenges) {
                      var meta = null;
                      try { meta = JSON.parse(atob(headers['rblx-challenge-metadata']||'')); } catch(e) {}
                      window.__ramChallenges.push({
                        id: headers['rblx-challenge-id'],
                        type: (headers['rblx-challenge-type']||'').toLowerCase(),
                        metadata_b64: headers['rblx-challenge-metadata']||'',
                        metadata: meta, url: r.url, status: r.status,
                        body: text.slice(0,500), ts: Date.now()
                      });
                    }
                    done({status: r.status, body: text, headers: headers, csrf: csrf});
                  });
                }).catch(e => done({status:0, body:String(e), headers:{}}));
                """,
                challenge_id,
                challenge_type,
                meta_json,
            )
        except Exception as e:
            self.log(f"[Captcha] challenge/continue threw: {e}")
            cont = {"status": 0, "body": str(e), "headers": {}}

        self.log(f"[Captcha] continue => status={cont.get('status') if isinstance(cont, dict) else cont}")
        if isinstance(cont, dict) and cont.get("body"):
            body_preview = str(cont.get("body"))[:300]
            self.log(f"[Captcha] continue body: {body_preview}")

        # Redeem: retry login with challenge headers
        self.log("[Captcha] Retrying login with challenge redemption headers...")
        try:
            retry = self.driver.execute_async_script(
                """
                const username = arguments[0];
                const password = arguments[1];
                const challengeId = arguments[2];
                const challengeType = arguments[3];
                const metadataB64 = arguments[4];
                const done = arguments[arguments.length - 1];

                function getCsrf() {
                  return fetch('https://auth.roblox.com/v2/login', {
                    method:'POST', credentials:'include',
                    headers:{'Content-Type':'application/json'}, body:'{}'
                  }).then(r => r.headers.get('x-csrf-token') || '');
                }

                getCsrf().then(function(csrf) {
                  return fetch('https://auth.roblox.com/v2/login', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                      'Content-Type': 'application/json',
                      'X-CSRF-TOKEN': csrf || '',
                      'rblx-challenge-id': challengeId,
                      'rblx-challenge-type': challengeType || 'captcha',
                      'rblx-challenge-metadata': metadataB64
                    },
                    body: JSON.stringify({
                      ctype: 'Username',
                      cvalue: username,
                      password: password
                    })
                  }).then(async function(r) {
                    const text = await r.text();
                    const headers = {};
                    r.headers.forEach((v,k) => headers[k.toLowerCase()] = v);
                    if (headers['rblx-challenge-id'] && window.__ramChallenges) {
                      var meta = null;
                      try { meta = JSON.parse(atob(headers['rblx-challenge-metadata']||'')); } catch(e) {}
                      window.__ramChallenges.push({
                        id: headers['rblx-challenge-id'],
                        type: (headers['rblx-challenge-type']||'').toLowerCase(),
                        metadata_b64: headers['rblx-challenge-metadata']||'',
                        metadata: meta, url: r.url, status: r.status,
                        body: text.slice(0,500), ts: Date.now()
                      });
                    }
                    done({status: r.status, body: text, headers: headers});
                  });
                }).catch(e => done({status:0, body:String(e), headers:{}}));
                """,
                self.username,
                self.password,
                challenge_id,
                challenge_type,
                meta_b64,
            )
        except Exception as e:
            self.log(f"[Captcha] Redeem login threw: {e}")
            return False

        status = retry.get("status") if isinstance(retry, dict) else None
        self.log(f"[Captcha] Redeem login status={status}")
        if isinstance(retry, dict) and retry.get("body"):
            self.log(f"[Captcha] Redeem body: {str(retry.get('body'))[:300]}")

        if status == 200:
            try:
                self.driver.get("https://www.roblox.com/home")
                time.sleep(1.2)
            except Exception:
                pass
            return True

        # Nested captcha / new challenge after redeem
        if status == 403 and isinstance(retry, dict):
            h = retry.get("headers") or {}
            if h.get("rblx-challenge-type"):
                self.log(
                    f"[Captcha] New challenge after redeem: "
                    f"{h.get('rblx-challenge-type')} — will handle next loop"
                )
        return False

    def wait_until_logged_in(self) -> bool:
        start = time.time()
        last_status = 0.0
        last_solve = 0.0
        fill_script = _build_fill_script(self.username, self.password) if self.username else ""

        # Ensure hooks exist on the login document
        self.install_hooks()

        if fill_script:
            try:
                self.driver.execute_script(fill_script)
                self.log(f"[Captcha] Submitted credentials for {self.username}")
            except Exception as e:
                self.log(f"[Captcha] Credential fill failed: {e}")

        # Small delay for the form login request to fire
        time.sleep(1.5)
        # Re-install hooks if navigation wiped them
        self.install_hooks()

        while time.time() - start < self.timeout:
            try:
                url = self.driver.current_url or ""
                if _is_logged_in_url(url):
                    self.log("[Captcha] Login detected via URL")
                    return True

                # Cookie presence on non-login pages
                try:
                    for c in self.driver.get_cookies():
                        if c.get("name") == ".ROBLOSECURITY" and c.get("value"):
                            if "/login" not in url.lower():
                                self.log("[Captcha] Login detected via cookie")
                                return True
                except Exception:
                    pass

                # Page may have navigated — re-hook
                info = self.detect()
                if not info.get("hookReady"):
                    self.install_hooks()
                    info = self.detect()

                # Credential errors
                body = (info.get("bodyText") or "").lower()
                if "incorrect username or password" in body or "incorrect username" in body:
                    self.log("[Captcha] Incorrect username or password")
                    return False

                now = time.time()
                has_captcha_challenge = any(
                    (c.get("type") or "").lower() == "captcha"
                    and not self._is_handled(c)
                    for c in (info.get("challenges") or [])
                )
                challenges = info.get("challenges") or []
                has_pow = any(
                    (c.get("type") or "").lower() == "proofofwork"
                    and not self._is_handled(c)
                    for c in challenges
                )
                captcha_ui = (
                    info.get("captchaVisible")
                    or info.get("verifyText")
                    or info.get("visibleChallenge")
                    or has_captcha_challenge
                    or has_pow
                )
                # Roblox "Verifying you are not a bot" body text
                body_l = (info.get("bodyText") or "").lower()
                verification_ui = any(
                    x in body_l
                    for x in (
                        "verifying",
                        "not a bot",
                        "i'm a human",
                        "im a human",
                        "start puzzle",
                        "verification",
                    )
                )

                # Still on login page for a while with no success → force challenge probe
                elapsed = now - start
                stuck_on_login = (
                    "/login" in (url or "").lower()
                    and elapsed > 4
                    and info.get("lastLoginStatus") in (403, None, 0)
                )

                if (
                    captcha_ui
                    or verification_ui
                    or stuck_on_login
                    or has_captcha_challenge
                    or has_pow
                ) and (now - last_solve) > 2.5 and not self._solving:
                    last_solve = now
                    self.log(
                        "[Captcha] Verification/challenge detected — auto-solving "
                        f"(pow={has_pow}, captcha={has_captcha_challenge}, ui={bool(captcha_ui or verification_ui)})..."
                    )
                    if not challenges:
                        self._probe_login_for_challenge()
                        info = self.detect()

                    for c in (info.get("challenges") or [])[-5:]:
                        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
                        self.log(
                            f"[Captcha]   challenge type={c.get('type')} "
                            f"id={str(c.get('id') or '')[:40]} "
                            f"blob={'yes' if _challenge_blob(meta) else 'no'}"
                        )
                    self.solve_and_continue(info)
                    time.sleep(1.0)
                    continue

                if now - last_status > 8:
                    last_status = now
                    n_ch = len(info.get("challenges") or [])
                    self.log(
                        f"[Captcha] Waiting... url={url[:70]} "
                        f"captchaUI={bool(captcha_ui)} challenges={n_ch} "
                        f"loginStatus={info.get('lastLoginStatus')} "
                        f"hook={info.get('hookReady')}"
                    )

                time.sleep(0.6)
            except Exception as e:
                if "invalid session" in str(e).lower():
                    return False
                time.sleep(0.6)

        self.log("[Captcha] Login timed out")
        return False


def _save_account_from_cookie(manager, cookie: str, password: str = "") -> tuple[bool, str]:
    """Import a cookie into the account manager; returns (ok, username_or_error)."""
    try:
        ok, username = manager.import_cookie_account(cookie)
        if ok and username:
            # Attach password if the cookie import path doesn't store it
            if password and username in manager.accounts:
                manager.accounts[username]["password"] = password
                manager.save_accounts()
            return True, str(username)
        return False, "Cookie import failed"
    except Exception as e:
        return False, str(e)


def login_and_extract(
    manager,
    username: str,
    password: str,
    twocaptcha_key: str,
    browser_path: str | None = None,
    timeout: float = 180.0,
) -> tuple[bool, Optional[str]]:
    """
    Full flow:
      1) API login with POW + FunCaptcha (2captcha) challenge chain (preferred)
      2) Browser fallback with the same solvers if API path fails
    Returns (success, username_or_error).
    """
    # --- Preferred: pure API challenge chain (handles stuck "verification") ---
    api_error = ""
    try:
        from .roblox_challenge import RobloxChallengeLogin

        user_agent = get_browser_user_agent(browser_path)
        max_api_attempts = 2 if twocaptcha_key else 1
        for api_attempt in range(1, max_api_attempts + 1):
            print(
                f"[INFO] Challenge-aware API login for {username} "
                f"(attempt {api_attempt}/{max_api_attempts})..."
            )
            # A retry needs a new requests session, POW and dataExchangeBlob.
            client = RobloxChallengeLogin(
                twocaptcha_key=twocaptcha_key,
                user_agent=user_agent,
            )
            ok, cookie_or_err, _ = client.login(username, password)
            if ok and cookie_or_err:
                saved, name = _save_account_from_cookie(manager, cookie_or_err, password)
                if saved:
                    print(f"[SUCCESS] API login saved account: {name}")
                    return True, name
                api_error = f"Cookie received but save failed: {name}"
                print(f"[WARNING] API login got cookie but save failed: {name}")
                break

            api_error = str(cookie_or_err or "API login failed")
            print(f"[WARNING] API challenge login failed: {api_error}")
            retriable = any(
                code in api_error
                for code in ("ERROR_CAPTCHA_UNSOLVABLE", "TIMEOUT")
            )
            if not retriable or api_attempt >= max_api_attempts:
                break
            print("[INFO] Retrying with a fresh Roblox challenge and captcha blob...")
    except Exception as e:
        api_error = str(e)
        print(f"[WARNING] API challenge login error: {e}")
        traceback.print_exc()

    # --- Fallback: browser login with interceptors + solvers ---
    driver = None
    try:
        driver = manager.setup_chrome_driver(browser_path)
        if not driver:
            suffix = f"; API error: {api_error}" if api_error else ""
            return False, f"Failed to start browser{suffix}"

        try:
            driver.set_window_size(520, 720)
        except Exception:
            pass
        try:
            driver.set_script_timeout(90)
        except Exception:
            pass

        helper = CaptchaAwareLogin(
            driver=driver,
            twocaptcha_key=twocaptcha_key,
            username=username,
            password=password,
            timeout=timeout,
        )
        helper.enable_network_capture()

        print(f"[INFO] Opening Roblox login for {username} (browser fallback)...")
        driver.get(ROBLOX_LOGIN_URL)
        time.sleep(2.0)
        helper.install_hooks()

        if not helper.wait_until_logged_in():
            try:
                for c in driver.get_cookies():
                    if c.get("name") == ".ROBLOSECURITY" and c.get("value"):
                        driver.get("https://www.roblox.com/home")
                        time.sleep(1)
                        break
                else:
                    suffix = f" API error: {api_error}" if api_error else ""
                    return False, (
                        f"Login failed for {username} "
                        f"(verification/captcha/timeout).{suffix}"
                    )
            except Exception:
                return False, f"Login failed for {username}"

        try:
            if "roblox.com" not in (driver.current_url or ""):
                driver.get("https://www.roblox.com/home")
                time.sleep(1)
        except Exception:
            pass

        username_out, cookie, user_id, captured_password, avatar_url = manager.extract_user_info(driver)
        if not username_out or not cookie:
            return False, f"Failed to extract session for {username}"

        manager.accounts[username_out] = {
            "username": username_out,
            "cookie": cookie,
            "user_id": user_id or 0,
            "password": captured_password or password or "",
            "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": "",
            "avatar_url": avatar_url or "",
        }
        manager.save_accounts()
        print(f"[SUCCESS] Successfully added account: {username_out}")
        return True, username_out
    except Exception as e:
        print(f"[ERROR] login_and_extract({username}): {e}")
        traceback.print_exc()
        return False, str(e)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        try:
            manager.cleanup_temp_profile()
        except Exception:
            pass
