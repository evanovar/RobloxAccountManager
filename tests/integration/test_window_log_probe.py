"""Real Windows open-file scanning against an isolated test process."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import psutil

from features import window_log_probe as probe


@unittest.skipUnless(sys.platform == "win32", "Requires Windows process inspection")
class RealOpenLogProbeTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="ram-probe-test-")))
        self.executable = self.folder / "RobloxPlayerBeta.exe"
        base = Path(sys.base_prefix)
        shutil.copy2(sys._base_executable, self.executable)
        for dll in base.glob("python*.dll"):
            shutil.copy2(dll, self.folder / dll.name)
        self.log = self.folder / "fixture_last.log"
        self.ready = self.folder / "ready"
        script = (
            "import sys, time; from pathlib import Path; "
            "handle = open(sys.argv[1], 'w'); "
            "handle.write('isolated test log'); handle.flush(); "
            "Path(sys.argv[2]).write_text('ready'); time.sleep(20)"
        )
        self.child = subprocess.Popen(
            [str(self.executable), "-c", script, str(self.log), str(self.ready)],
            env={**os.environ, "PYTHONHOME": str(base)},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.addCleanup(self.stop_child)
        deadline = time.monotonic() + 5
        while not self.ready.exists() and time.monotonic() < deadline:
            if self.child.poll() is not None:
                self.fail(f"Fixture exited early: {self.child.returncode}")
            time.sleep(0.02)
        self.assertTrue(self.ready.exists(), "Fixture did not become ready")
        self.key = (self.child.pid, psutil.Process(self.child.pid).create_time())

    def stop_child(self):
        if self.child.poll() is None:
            self.child.kill()
        self.child.wait(timeout=5)

    def test_actual_helper_finds_only_fixture_log(self):
        result = probe.probe_open_log_paths(self.key, threading.Event())
        self.assertEqual(result.status, "ok")
        self.assertIn(os.path.normcase(str(self.log)), result.paths)
        self.assertIsNone(self.child.poll(), "Probe must not terminate the inspected process")

    def test_actual_helper_rejects_reused_process_identity(self):
        result = probe.probe_open_log_paths((self.key[0], self.key[1] - 100), threading.Event())
        self.assertEqual(result.status, "process_changed")
        self.assertFalse(result.paths)
