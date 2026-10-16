import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from features import window_log_probe as probe


class ProbeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.result = str(Path(self.directory) / "result.json")
        self.key = (123, 100.0)

    def read(self, payload):
        Path(self.result).write_text(json.dumps(payload), encoding="utf-8")
        return probe._read_result(self.result, self.key)

    def test_success_is_tied_to_pid_and_creation_time(self):
        path = str(Path(self.directory) / "player_last.log")
        result = self.read(dict(status="ok", pid=123, create_time=100.0, paths=[path]))
        self.assertEqual(result, probe.ProbeResult("ok", frozenset({os.path.normcase(path)})))
        self.assertEqual(self.read(dict(status="ok", pid=123, create_time=200.0,
                                        paths=[path])).status, "error")

    def test_rejects_invalid_payloads_and_paths(self):
        for payload in ([], {}, dict(status="ok", pid=123, create_time=100.0,
                                      paths=["relative_last.log"]),
                        dict(status="ok", pid=123, create_time=100.0,
                             paths=[str(Path(self.directory) / "other.txt")])):
            with self.subTest(payload=payload):
                self.assertEqual(self.read(payload).status, "error")

    def test_rejects_oversized_output(self):
        Path(self.result).write_bytes(b" " * (probe._MAX_RESULT_BYTES + 1))
        self.assertEqual(probe._read_result(self.result, self.key).status, "error")

    def test_helper_rechecks_pid_after_scan(self):
        import psutil
        old = MagicMock()
        old.create_time.return_value = 100.0
        old.name.return_value = "RobloxPlayerBeta.exe"
        old.open_files.return_value = [SimpleNamespace(path=str(Path(self.directory) / "player_last.log"))]
        reused = MagicMock()
        reused.create_time.return_value = 200.0
        with patch.object(psutil, "Process", side_effect=[old, reused]):
            self.assertEqual(probe._scan(123, 100.0)["status"], "process_changed")

    def test_wrong_process_is_not_scanned(self):
        import psutil
        process = MagicMock()
        process.create_time.return_value = 100.0
        process.name.return_value = "other.exe"
        with patch.object(psutil, "Process", return_value=process):
            self.assertEqual(probe._scan(123, 100.0)["status"], "process_changed")
        process.open_files.assert_not_called()

    def test_windowed_helper_uses_result_file_without_stdout(self):
        with patch.object(probe, "_scan", return_value={"status": "process_changed"}), \
             patch("sys.stdout", None):
            self.assertEqual(probe.helper_main(["123", "100.0", self.result]), 0)
        self.assertEqual(json.loads(Path(self.result).read_text())["status"], "process_changed")

    def test_helper_arguments_cannot_start_ui_on_error(self):
        self.assertEqual(probe.helper_main([]), 2)
        self.assertEqual(probe.helper_main(["123", "nan", self.result]), 2)

    def test_frozen_command_reuses_executable(self):
        with patch.object(probe.sys, "frozen", True, create=True):
            command = probe._helper_command(self.key, self.result)
        self.assertEqual(command[:2], [probe.sys.executable, probe.HELPER_OPTION])
        self.assertEqual(command[2:], ["123", "100.0", self.result])


class ProbeLifetimeTests(unittest.TestCase):
    def test_timeout_kills_and_reaps_helper(self):
        child = MagicMock()
        child.poll.return_value = None
        with patch.object(probe.subprocess, "Popen", return_value=child):
            result = probe.probe_open_log_paths((123, 100.0), threading.Event(), timeout=0)
        self.assertEqual(result.status, "timeout")
        child.kill.assert_called_once()
        child.wait.assert_called_once_with(timeout=1)

    def test_cancelled_scan_does_not_start_a_process(self):
        stop = threading.Event()
        stop.set()
        with patch.object(probe.subprocess, "Popen") as start:
            result = probe.probe_open_log_paths((123, 100.0), stop)
        self.assertEqual(result.status, "cancelled")
        start.assert_not_called()

    def test_running_helper_is_cancelled_and_reaped(self):
        stop = threading.Event()
        child = MagicMock()
        def started(*args, **kwargs):
            stop.set()
            return child
        child.poll.return_value = None
        with patch.object(probe.subprocess, "Popen", side_effect=started):
            result = probe.probe_open_log_paths((123, 100.0), stop)
        self.assertEqual(result.status, "cancelled")
        child.kill.assert_called_once()
        child.wait.assert_called_once_with(timeout=1)
