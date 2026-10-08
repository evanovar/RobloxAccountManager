import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from features import window_log_probe as probe


class IsolatedScanHeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def test_native_scan_holding_child_gil_cannot_freeze_qt(self):
        # PyDLL deliberately retains the child's GIL during Sleep. A scan run
        # inside the UI process would prevent these Python Qt callbacks running.
        command = [sys.executable, "-c",
                   "import ctypes; ctypes.PyDLL('kernel32').Sleep(15000)"]
        ticks = []
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        results = []
        done = threading.Event()
        children = []
        real_start = subprocess.Popen
        def start(*args, **kwargs):
            child = real_start(*args, **kwargs)
            children.append(child)
            return child
        def scan():
            try:
                results.append(probe.probe_open_log_paths((123, 100.0),
                                                          threading.Event(), timeout=1.0))
            finally:
                done.set()
        with patch.object(probe, "_helper_command", return_value=command), \
             patch.object(probe.subprocess, "Popen", side_effect=start):
            timer.start()
            worker = threading.Thread(target=scan)
            worker.start()
            deadline = time.monotonic() + 4
            while not done.is_set() and time.monotonic() < deadline:
                QTest.qWait(20)
            timer.stop()
            worker.join(timeout=2)
        self.assertTrue(done.is_set())
        self.assertEqual(results[0].status, "timeout")
        self.assertGreaterEqual(len(ticks), 15)
        self.assertLess(max(b - a for a, b in zip(ticks, ticks[1:])), 0.35)
        self.assertTrue(children)
        self.assertIsNotNone(children[0].poll())

    def test_real_early_entry_does_not_initialize_app_data_or_ui(self):
        import psutil
        with tempfile.TemporaryDirectory() as folder:
            output = str(Path(folder) / "result.json")
            data = str(Path(folder) / "must-not-be-created")
            key = (os.getpid(), psutil.Process().create_time())
            result = subprocess.run(
                probe._helper_command(key, output),
                env={**os.environ, "RAM_DATA_DIR": data},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(probe._read_result(output, key).status, "process_changed")
            self.assertFalse(Path(data).exists())
