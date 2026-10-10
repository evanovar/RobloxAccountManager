import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch

import win32api

from scripts import build


class BuildTests(unittest.TestCase):
    def test_host_library_paths_are_removed_without_changing_the_parent(self):
        overrides = {
            "PATH": r"C:\unrelated\bin",
            "PYTHONPATH": r"C:\unrelated\python",
            "PYTHONHOME": r"C:\unrelated\python",
            "QT_PLUGIN_PATH": r"C:\unrelated\qt",
            "QT_QPA_PLATFORM_PLUGIN_PATH": r"C:\unrelated\platforms",
            "QML_IMPORT_PATH": r"C:\unrelated\qml",
            "QML2_IMPORT_PATH": r"C:\unrelated\qml2",
            "RAM_RELEASE_TAG": "v1.2.3",
        }
        with patch.dict(os.environ, overrides):
            parent = dict(os.environ)
            environment = build.build_environment()
            self.assertEqual(dict(os.environ), parent)
        self.assertNotIn(overrides["PATH"], environment["PATH"])
        for name in overrides.keys() - {"PATH", "RAM_RELEASE_TAG"}:
            self.assertNotIn(name, environment)
        paths = environment["PATH"].split(os.pathsep)
        self.assertIn(win32api.GetSystemDirectory(), paths)
        self.assertIn(str(Path(build.sys.executable).parent), paths)
        self.assertEqual(environment["RAM_RELEASE_TAG"], "v1.2.3")

    def test_failed_startup_prevents_build_success_and_release_copy(self):
        with patch.object(build, "validate_build_files"), \
                patch.object(build, "read_app_version", return_value="1.2.3"), \
                patch.object(build, "validate_release_tag", return_value=True), \
                patch.object(build, "generate_version_info"), \
                patch.object(build.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(build, "check_packaged_startup", side_effect=RuntimeError("startup failed")), \
                patch.object(build, "create_release_asset") as release_copy, \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(build.main(), 1)
        release_copy.assert_not_called()
        self.assertNotIn("[SUCCESS]", output.getvalue())

    def test_packaged_check_uses_temporary_data_and_rejects_failed_exit(self):
        process = MagicMock()
        process.wait.return_value = 5
        with patch.object(build.subprocess, "Popen") as launch:
            launch.return_value.__enter__.return_value = process
            with self.assertRaisesRegex(RuntimeError, "code 5"):
                build.check_packaged_startup(build.build_environment())
        command = launch.call_args.args[0]
        self.assertEqual(command[:3], [str(build.OUTPUT_PATH), "--smoke-test", "--data-dir"])
        self.assertFalse(Path(command[3]).exists())
        self.assertNotEqual(Path(command[3]), build.PROJECT_ROOT / "AccountManagerData")
        self.assertEqual(launch.call_args.kwargs["env"]["QT_QPA_PLATFORM"], "offscreen")

    def test_startup_timeout_stops_the_one_file_process_tree(self):
        process = MagicMock(pid=12345)
        process.wait.side_effect = subprocess.TimeoutExpired("app", 60)
        with patch.object(build.subprocess, "Popen") as launch, \
                patch.object(build.subprocess, "run") as stop:
            launch.return_value.__enter__.return_value = process
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                build.check_packaged_startup(build.build_environment())
        self.assertEqual(stop.call_args.args[0][1:], ["/PID", "12345", "/T", "/F"])


if __name__ == "__main__":
    unittest.main()
