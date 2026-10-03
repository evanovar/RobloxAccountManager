import unittest
from unittest.mock import Mock, patch
import requests
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
    def test_background_validator_marks_repeated_403_invalid(self, sleep):
        session = Mock()
        session.get.return_value = Mock(status_code=403)
        status, detail, rate_limited = cookie_validator._check(
            "cookie",
            session,
        )
        self.assertEqual(status, cookie_validator.INVALID)
        self.assertIn("403", detail)
        self.assertFalse(rate_limited)
