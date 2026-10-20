import unittest
import tempfile
from unittest.mock import Mock, patch
import requests
from classes import account_manager as am
from classes.roblox_api import RobloxAPI
from features import cookie_validator

class AuthenticationTests(unittest.TestCase):
    @patch("classes.roblox_api.time.sleep")
    @patch("classes.roblox_api.requests.post")
    def test_403_without_csrf_marks_cookie_invalid(self, post, sleep):
        post.return_value = Mock(status_code=403, headers={})
        result = RobloxAPI.get_auth_ticket("cookie")
        self.assertFalse(result)
        self.assertEqual(result.code, "COOKIE_INVALID")
        sleep.assert_not_called()

    @patch("classes.roblox_api.time.sleep")
    @patch("classes.roblox_api.requests.post")
    def test_429_is_reported_as_rate_limit(self, post, sleep):
        post.return_value = Mock(status_code=429, headers={})
        result = RobloxAPI.get_auth_ticket("cookie")
        self.assertFalse(result)
        self.assertEqual(result.code, "RATE_LIMITED")
        self.assertEqual(post.call_count, 4)

    @patch("classes.roblox_api.requests.post")
    def test_authentication_ticket_success(self, post):
        post.side_effect = [
            Mock(status_code=403, headers={"x-csrf-token": "csrf"}),
            Mock(
                status_code=200,
                headers={"rbx-authentication-ticket": "ticket"},
            ),
        ]
        result = RobloxAPI.get_auth_ticket("cookie")
        self.assertTrue(result)
        self.assertEqual(result.data, "ticket")

    @patch("classes.roblox_api.requests.post")
    def test_authentication_timeout_is_retryable(self, post):
        post.side_effect = requests.Timeout("timed out")
        result = RobloxAPI.get_auth_ticket("cookie")
        self.assertFalse(result)
        self.assertEqual(result.code, "NETWORK_TIMEOUT")
        self.assertTrue(result.retryable)

    @patch("classes.roblox_api.requests.get")
    def test_cookie_validator_keeps_429_distinct(self, get):
        get.return_value = Mock(status_code=429)
        result = RobloxAPI.validate_cookie("cookie")
        self.assertFalse(result)
        self.assertEqual(result.code, "RATE_LIMITED")
        self.assertTrue(result.retryable)

    @patch("features.cookie_validator.time.sleep")
    def test_background_validator_does_not_expire_cookie_on_429(self, sleep):
        session = Mock()
        session.get.return_value = Mock(status_code=429)
        status, detail, rate_limited = cookie_validator._check(
            "cookie",
            session,
        )
        self.assertEqual(status, cookie_validator.UNKNOWN)
        self.assertIn("429", detail)
        self.assertTrue(rate_limited)

    @patch("features.cookie_validator.time.sleep")
    def test_background_validator_marks_repeated_401_invalid(self, sleep):
        session = Mock()
        session.get.return_value = Mock(status_code=401)
        status, detail, rate_limited = cookie_validator._check(
            "cookie",
            session,
        )
        self.assertEqual(status, cookie_validator.INVALID)
        self.assertIn("401", detail)
        self.assertFalse(rate_limited)

    @patch("features.cookie_validator.time.sleep")
    def test_other_failures_are_inconclusive_even_after_an_unauthorized_response(self, sleep):
        for responses in ((403, 403), (500, 500), (401, 500), (401, 429), (401, requests.Timeout("timeout"))):
            with self.subTest(responses=responses):
                session = Mock()
                session.get.side_effect = [Mock(status_code=value) if isinstance(value, int) else value for value in responses]
                status, _, _ = cookie_validator._check("synthetic-cookie", session)
                self.assertEqual(status, cookie_validator.UNKNOWN)


class CookieValidationPersistenceTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(am, "get_data_dir", return_value=folder))
        self.enterContext(patch.object(cookie_validator.time, "sleep"))
        self.manager = am.RobloxAccountManager()
        self.manager.accounts = {"alice": {"cookie": "synthetic-cookie", "cookie_valid": True}}
        self.session = self.enterContext(patch.object(cookie_validator.requests, "Session")).return_value
        self.session.get.return_value = Mock(status_code=401)

    def worker(self, callback=None):
        worker = cookie_validator.CookieValidator(self.manager, on_result=callback or Mock())
        worker._stop_evt.wait = Mock(return_value=False)
        return worker

    def test_invalid_status_is_saved_before_callback_and_skipped_after_restart(self):
        def on_result(username, status):
            self.assertEqual(status, cookie_validator.INVALID)
            self.assertFalse(am.RobloxAccountManager().accounts[username]["cookie_valid"])

        self.worker(on_result)._run()
        self.assertEqual(self.session.get.call_count, 2)
        self.manager = am.RobloxAccountManager()
        self.session.get.reset_mock()
        self.worker()._run()
        self.session.get.assert_not_called()

    def test_inconclusive_results_preserve_status_without_saving(self):
        for initial in (True, None):
            for response in (403, 429, 500, requests.ConnectionError("offline")):
                with self.subTest(initial=initial, response=response):
                    self.manager.accounts["alice"]["cookie_valid"] = initial
                    self.session.get.side_effect = response if isinstance(response, Exception) else None
                    self.session.get.return_value = Mock(status_code=response if isinstance(response, int) else 500)
                    with patch.object(self.manager, "save_accounts") as save:
                        self.worker()._run()
                    self.assertIs(self.manager.accounts["alice"]["cookie_valid"], initial)
                    save.assert_not_called()

    def test_invalid_status_cannot_be_cleared_by_another_validation_result(self):
        self.manager.accounts["alice"]["cookie_valid"] = False
        for status in (cookie_validator.VALID, cookie_validator.UNKNOWN):
            self.assertFalse(cookie_validator._set_status(self.manager, "alice", status))
            self.assertFalse(self.manager.accounts["alice"]["cookie_valid"])

    def test_stop_after_confirmed_unauthorized_response_still_saves(self):
        worker = self.worker()

        def check(*_args):
            worker._stop_evt.set()
            return cookie_validator.INVALID, "HTTP 401", False

        with patch.object(cookie_validator, "_check", side_effect=check):
            worker._run()
        self.assertFalse(am.RobloxAccountManager().accounts["alice"]["cookie_valid"])

    def test_changed_cookie_or_replaced_record_does_not_receive_stale_invalid_result(self):
        for replace_record in (False, True):
            with self.subTest(replace_record=replace_record):
                self.manager.accounts["alice"] = {"cookie": "synthetic-cookie", "cookie_valid": True}

                def check(*_args):
                    if replace_record:
                        self.manager.accounts["alice"] = dict(self.manager.accounts["alice"])
                    else:
                        self.manager.accounts["alice"]["cookie"] = "synthetic-replacement"
                    return cookie_validator.INVALID, "HTTP 401", False

                with patch.object(cookie_validator, "_check", side_effect=check), patch.object(self.manager, "save_accounts") as save:
                    self.worker()._run()
                self.assertTrue(self.manager.accounts["alice"]["cookie_valid"])
                save.assert_not_called()

    def test_legacy_invalid_status_survives_loading_and_is_not_checked(self):
        self.manager.accounts["alice"] = {"cookie": "synthetic-cookie", "valid": False}
        self.manager.save_accounts()
        self.manager = am.RobloxAccountManager()
        self.worker()._run()
        self.assertFalse(self.manager.accounts["alice"]["cookie_valid"])
        self.session.get.assert_not_called()

    def test_deleting_and_readding_account_allows_checks_again(self):
        self.manager.accounts["alice"]["cookie_valid"] = False
        self.manager.delete_account("alice")
        self.manager.accounts["alice"] = {"cookie": "synthetic-cookie", "cookie_valid": None}
        self.session.get.return_value = Mock(status_code=200)
        self.worker()._run()
        self.session.get.assert_called_once()
        self.assertTrue(am.RobloxAccountManager().accounts["alice"]["cookie_valid"])
