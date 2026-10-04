import unittest
from unittest import mock

from features import websocket_server
from features.websocket_server import WebSocketServer


class FakeManager:
    accounts = {}

    def get_secure_setting(self, key, default=""):
        return "secret"


def make_server(**extra):
    settings = {"websocket_require_password": True, **extra}
    return WebSocketServer(FakeManager(), {}, {}, lambda: settings)


def guess(server, password):
    return server._execute(f"AUTH {password} | Ping")


class LockoutTests(unittest.TestCase):
    def test_repeated_wrong_passwords_lock_further_attempts(self):
        server = make_server(websocket_max_auth_failures=3)
        for _ in range(3):
            self.assertEqual(guess(server, "nope")["error"], "Authentication failed")
        reply = guess(server, "secret")
        self.assertFalse(reply["ok"])
        self.assertIn("Too many failed attempts", reply["error"])

    def test_correct_password_works_below_the_limit(self):
        server = make_server(websocket_max_auth_failures=3)
        guess(server, "nope")
        guess(server, "nope")
        self.assertEqual(guess(server, "secret"), {"ok": True, "result": "Pong"})

    def test_lockout_expires_after_the_window(self):
        server = make_server(websocket_max_auth_failures=2)
        now = [1000.0]
        with mock.patch.object(websocket_server.time, "monotonic", side_effect=lambda: now[0]):
            guess(server, "nope")
            guess(server, "nope")
            self.assertFalse(guess(server, "secret")["ok"])
            now[0] += websocket_server.AUTH_FAILURE_WINDOW_SECONDS + 1
            self.assertTrue(guess(server, "secret")["ok"])

    def test_zero_disables_the_lockout(self):
        server = make_server(websocket_max_auth_failures=0)
        for _ in range(50):
            guess(server, "nope")
        self.assertTrue(guess(server, "secret")["ok"])

    def test_default_limit_applies_when_unset_or_invalid(self):
        for extra in ({}, {"websocket_max_auth_failures": "many"}):
            with self.subTest(extra=extra):
                server = make_server(**extra)
                for _ in range(websocket_server.DEFAULT_MAX_AUTH_FAILURES):
                    guess(server, "nope")
                self.assertIn("Too many failed attempts", guess(server, "secret")["error"])

    def test_format_errors_do_not_count_as_failures(self):
        server = make_server(websocket_max_auth_failures=2)
        for _ in range(10):
            server._execute("Ping")
        self.assertTrue(guess(server, "secret")["ok"])

    def test_servers_do_not_share_failures(self):
        first, second = make_server(websocket_max_auth_failures=1), make_server(websocket_max_auth_failures=1)
        guess(first, "nope")
        self.assertTrue(guess(second, "secret")["ok"])


if __name__ == "__main__":
    unittest.main()
