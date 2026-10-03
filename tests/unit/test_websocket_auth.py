"""WebSocket command authentication, including Unicode passwords."""

import unittest

from features.websocket_server import WebSocketServer


class FakeManager:
    accounts = {}

    def __init__(self, password):
        self.password = password

    def get_secure_setting(self, key, default=""):
        return self.password


def make_server(password, require_password=True):
    settings = {"websocket_require_password": require_password}
    return WebSocketServer(FakeManager(password), {}, {}, lambda: settings)


class AuthTests(unittest.TestCase):
    def test_correct_password(self):
        reply = make_server("secret")._execute("AUTH secret | Ping")
        self.assertEqual(reply, {"ok": True, "result": "Pong"})

    def test_wrong_password(self):
        reply = make_server("secret")._execute("AUTH nope | Ping")
        self.assertEqual(reply, {"ok": False, "error": "Authentication failed"})

    def test_missing_auth_prefix(self):
        reply = make_server("secret")._execute("Ping")
        self.assertFalse(reply["ok"])

    def test_no_password_required(self):
        reply = make_server("", require_password=False)._execute("Ping")
        self.assertTrue(reply["ok"])

    def test_non_ascii_password_authenticates(self):
        reply = make_server("pässwörd")._execute("AUTH pässwörd | Ping")
        self.assertEqual(reply, {"ok": True, "result": "Pong"})

    def test_non_ascii_guess_against_ascii_password_is_rejected(self):
        reply = make_server("secret")._execute("AUTH sécret | Ping")
        self.assertEqual(reply, {"ok": False, "error": "Authentication failed"})

    def test_wrong_non_ascii_password_is_rejected(self):
        reply = make_server("pässwörd")._execute("AUTH pässword | Ping")
        self.assertEqual(reply, {"ok": False, "error": "Authentication failed"})


if __name__ == "__main__":
    unittest.main()
