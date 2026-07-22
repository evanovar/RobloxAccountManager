import json
import unittest
from unittest.mock import patch

from classes.captcha_solver import (
    DEFAULT_TWOCAPTCHA_KEY,
    TwoCaptchaSolver,
    get_2captcha_key_from_settings,
)
from classes.roblox_challenge import RobloxChallengeLogin
from classes.roblox_login import CaptchaAwareLogin, login_and_extract


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class CaptchaSolverTests(unittest.TestCase):
    def test_api_key_comes_only_from_gui_settings(self):
        class _Manager:
            def get_secure_setting(self, *_args):
                return "not-the-gui-value"

        self.assertEqual(DEFAULT_TWOCAPTCHA_KEY, "")
        with patch(
            "features.account_actions.load_ui_settings",
            return_value={"twocaptcha_api_key": "  gui-key  "},
        ):
            self.assertEqual(get_2captcha_key_from_settings(_Manager()), "gui-key")

        with patch("features.account_actions.load_ui_settings", return_value={}):
            self.assertEqual(get_2captcha_key_from_settings(_Manager()), "")

    def test_funcaptcha_task_uses_host_blob_and_user_agent(self):
        solver = TwoCaptchaSolver("key", polling_interval=0, timeout=1)
        solver.session = _Session(
            [
                _Response({"errorId": 0, "taskId": 123}),
                _Response(
                    {
                        "errorId": 0,
                        "status": "ready",
                        "solution": {"token": "solved-token"},
                    }
                ),
            ]
        )

        token = solver.solve_funcaptcha(
            public_key="public-key",
            page_url="https://www.roblox.com/login",
            surl="https://roblox-api.arkoselabs.com/path",
            blob="fresh-blob",
            user_agent="test-agent",
        )

        self.assertEqual(token, "solved-token")
        task = solver.session.calls[0][1]["json"]["task"]
        self.assertEqual(task["funcaptchaApiJSSubdomain"], "roblox-api.arkoselabs.com")
        self.assertEqual(json.loads(task["data"]), {"blob": "fresh-blob"})
        self.assertEqual(task["userAgent"], "test-agent")

    def test_provider_error_is_preserved(self):
        solver = TwoCaptchaSolver("key", polling_interval=0, timeout=1)
        solver.session = _Session(
            [
                _Response({"errorId": 0, "taskId": 123}),
                _Response(
                    {
                        "errorId": 12,
                        "errorCode": "ERROR_CAPTCHA_UNSOLVABLE",
                        "errorDescription": "Workers could not solve the Captcha",
                    }
                ),
            ]
        )

        self.assertIsNone(solver.solve_funcaptcha("public-key", blob="fresh-blob"))
        self.assertEqual(solver.last_error_code, "ERROR_CAPTCHA_UNSOLVABLE")
        self.assertIn("Workers", solver.last_error_description)


class ChallengeFlowTests(unittest.TestCase):
    def test_same_id_with_new_type_is_not_already_handled(self):
        helper = CaptchaAwareLogin.__new__(CaptchaAwareLogin)
        helper._handled_challenges = {("same-id", "proofofwork")}

        self.assertFalse(helper._is_handled({"id": "same-id", "type": "captcha"}))
        self.assertTrue(helper._is_handled({"id": "same-id", "type": "proofofwork"}))

    def test_captcha_continue_metadata_preserves_original_fields(self):
        class _Solver:
            last_error_code = ""
            last_error_description = ""

            def __init__(self):
                self.calls = 0

            def solve_funcaptcha(self, **kwargs):
                self.calls += 1
                return "token"

        client = RobloxChallengeLogin("")
        client.solver = _Solver()
        original = {
            "dataExchangeBlob": "blob",
            "unifiedCaptchaId": "unified",
            "actionType": "Login",
            "requestPath": "/v2/login",
            "requestMethod": "POST",
            "sharedParameters": {"useContinueMode": False},
        }

        result = client.solve_captcha_challenge(
            {"id": "challenge-id", "type": "captcha", "metadata": original}
        )

        self.assertEqual(client.solver.calls, 1)
        self.assertEqual(result["captchaToken"], "token")
        self.assertEqual(result["requestPath"], "/v2/login")
        self.assertEqual(result["sharedParameters"], {"useContinueMode": False})

    def test_login_and_extract_retries_with_a_fresh_client(self):
        outcomes = [
            (False, "FunCaptcha solve failed (ERROR_CAPTCHA_UNSOLVABLE).", ""),
            (True, "cookie-value", ""),
        ]
        clients = []

        class _Client:
            def __init__(self, **kwargs):
                clients.append(self)

            def login(self, username, password):
                return outcomes.pop(0)

        class _Manager:
            pass

        with (
            patch("classes.roblox_challenge.RobloxChallengeLogin", _Client),
            patch("classes.roblox_login.get_browser_user_agent", return_value="agent"),
            patch("classes.roblox_login._save_account_from_cookie", return_value=(True, "name")),
        ):
            ok, name = login_and_extract(
                _Manager(),
                username="user",
                password="pass",
                twocaptcha_key="key",
            )

        self.assertTrue(ok)
        self.assertEqual(name, "name")
        self.assertEqual(len(clients), 2)


if __name__ == "__main__":
    unittest.main()
