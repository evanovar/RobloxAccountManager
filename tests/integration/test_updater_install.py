import base64
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from features import updater

CMD_EXE = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
NO_PROCESS = "99999999"


def sha256_of(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest().upper()


def read(path):
    with open(path, "rb") as handle:
        return handle.read()


@unittest.skipUnless(sys.platform == "win32" and os.path.exists(CMD_EXE), "Requires Windows PowerShell")
class InstallerScriptTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.app_dir = os.path.join(self.folder, "app dir")
        self.update_dir = os.path.join(self.folder, "update")
        os.makedirs(self.app_dir)
        os.makedirs(self.update_dir)
        self.app = os.path.join(self.app_dir, "RAM.exe")
        self.update = os.path.join(self.update_dir, "update.exe")
        self.marker = os.path.join(self.folder, "launched.txt")
        self.log = os.path.join(self.folder, "update.log")
        self.script = os.path.join(self.update_dir, "install_update.ps1")
        shutil.copy(CMD_EXE, self.app)
        shutil.copy(CMD_EXE, self.update)
        with open(self.update, "ab") as handle:
            handle.write(b"\x00new-version-marker")
        self.old_bytes = read(self.app)
        self.new_bytes = read(self.update)
        with open(self.script, "w", encoding="utf-8") as handle:
            handle.write(updater._build_installer_script())

    def launch_arguments(self):
        text = f'/c echo launched> "{self.marker}"'
        return base64.b64encode(text.encode("utf-8")).decode("ascii")

    def run_script(self, pid=NO_PROCESS, sha=None, source=None, with_arguments=True, timeout=60):
        checksum = sha256_of(self.update) if sha is None else sha
        command = [
            updater._system_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", self.script,
            "-TargetProcessId", pid,
            "-SourcePath", source or self.update,
            "-DestinationPath", self.app,
            "-LogPath", self.log,
            "-UpdateDirectory", self.update_dir,
            "-ExpectedSha256", checksum,
            "-LaunchArgumentsBase64", self.launch_arguments() if with_arguments else "",
        ]
        return subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            env=updater._powershell_environment(),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def wait_for_marker(self, present=True, seconds=15):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if os.path.exists(self.marker) == present:
                return True
            time.sleep(0.1)
        return os.path.exists(self.marker) == present

    def leftovers(self):
        return [name for name in os.listdir(self.app_dir) if name != "RAM.exe"]

    def test_a_good_update_replaces_the_app_and_starts_it_again(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(read(self.app), self.new_bytes)
        self.assertEqual(self.leftovers(), [])
        self.assertTrue(self.wait_for_marker(), "the new version was not started")
        self.assertFalse(os.path.exists(self.update_dir))
        self.assertFalse(os.path.exists(self.log))

    def test_the_app_is_restarted_from_a_folder_with_a_space_and_gets_its_arguments(self):
        self.assertIn(" ", self.app_dir)
        self.assertEqual(self.run_script().returncode, 0)
        self.assertTrue(self.wait_for_marker())
        with open(self.marker) as handle:
            self.assertIn("launched", handle.read())

    def test_without_launch_arguments_the_update_still_installs(self):
        result = self.run_script(with_arguments=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(read(self.app), self.new_bytes)
        self.assertFalse(os.path.exists(self.marker))

    def test_a_checksum_mismatch_leaves_the_old_version_in_place_and_starts_it(self):
        result = self.run_script(sha="0" * 64)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(read(self.app), self.old_bytes)
        self.assertEqual(self.leftovers(), [])
        with open(self.log, encoding="utf-8-sig") as handle:
            self.assertIn("published checksum", handle.read())
        self.assertTrue(self.wait_for_marker(), "the previous version was not started again")

    def test_a_missing_download_leaves_the_old_version_in_place(self):
        result = self.run_script(source=os.path.join(self.update_dir, "missing.exe"), sha="")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(read(self.app), self.old_bytes)
        self.assertEqual(self.leftovers(), [])

    def test_the_checksum_is_optional(self):
        self.assertEqual(self.run_script(sha="").returncode, 0)
        self.assertEqual(read(self.app), self.new_bytes)

    def test_it_waits_for_the_running_app_to_exit_before_replacing_it(self):
        process = subprocess.Popen(
            [self.app, "/c", "ping -n 4 127.0.0.1 > nul"], creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.addCleanup(process.kill)
        started = time.time()
        result = self.run_script(pid=str(process.pid))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(time.time() - started, 1.5)
        self.assertEqual(read(self.app), self.new_bytes)
        self.assertIsNotNone(process.poll())

    def test_leftover_files_from_an_earlier_attempt_do_not_block_an_update(self):
        for suffix in (".new", ".old"):
            with open(self.app + suffix, "wb") as handle:
                handle.write(b"stale")
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(read(self.app), self.new_bytes)
        self.assertEqual(self.leftovers(), [])


if __name__ == "__main__":
    unittest.main()
