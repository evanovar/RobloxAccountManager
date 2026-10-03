"""Origin restrictions exercised through a real loopback WebSocket server."""

import socket
import time
import unittest

from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

from features.websocket_server import WebSocketServer


class FakeManager:
    accounts = {"alice": {}}

    def get_secure_setting(self, key, default=""):
        return ""


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class OriginTests(unittest.TestCase):
    def start_server(self, **extra):
        self.port = free_port()
        settings = {"websocket_port": self.port, **extra}
        server = WebSocketServer(FakeManager(), {}, {}, lambda: settings)
        server.start()
        self.addCleanup(server.stop)
        deadline = time.time() + 5
        while not server.running and time.time() < deadline:
            time.sleep(0.02)
        self.assertTrue(server.running, "server did not start")

    def ask(self, command, origin=None):
        with connect(f"ws://localhost:{self.port}", origin=origin, open_timeout=5) as ws:
            ws.send(command)
            return ws.recv(timeout=5)

    def test_client_without_origin_is_accepted(self):
        self.start_server()
        self.assertIn("Pong", self.ask("Ping"))

    def test_browser_origin_is_rejected(self):
        self.start_server()
        with self.assertRaises(InvalidStatus) as caught:
            self.ask("AccountList", origin="https://evil.example")
        self.assertEqual(caught.exception.response.status_code, 403)

    def test_configured_origin_is_accepted(self):
        self.start_server(websocket_allowed_origins=["http://localhost:3000"])
        self.assertIn("Pong", self.ask("Ping", origin="http://localhost:3000"))

    def test_other_origin_is_still_rejected_when_one_is_configured(self):
        self.start_server(websocket_allowed_origins=["http://localhost:3000"])
        with self.assertRaises(InvalidStatus):
            self.ask("Ping", origin="https://evil.example")


if __name__ == "__main__":
    unittest.main()
