import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from classes.operation_result import OperationResult
from features import windows_startup


DETAILS = {
    "target": r"C:\Apps\Pealz $Tools\RAM.exe",
    "arguments": "",
    "working_directory": r"C:\Apps\Pealz $Tools",
    "icon_path": "",
}


class ScriptTests(unittest.TestCase):
    def test_values_are_single_quoted_so_dollar_signs_stay_literal(self):
        script = windows_startup._build_shortcut_script(r"C:\Menu\RAM.lnk", DETAILS, "Roblox Account Manager")
        self.assertIn(r"$shortcut.TargetPath = 'C:\Apps\Pealz $Tools\RAM.exe';", script)
        self.assertNotIn('"', script)

    def test_single_quotes_in_paths_are_doubled(self):
        details = {**DETAILS, "target": r"C:\Bob's Apps\RAM.exe"}
        script = windows_startup._build_shortcut_script(r"C:\Menu\RAM.lnk", details, "x")
        self.assertIn(r"'C:\Bob''s Apps\RAM.exe'", script)

    def test_icon_is_only_set_when_there_is_one(self):
        without = windows_startup._build_shortcut_script("a.lnk", DETAILS, "x")
        with_icon = windows_startup._build_shortcut_script("a.lnk", {**DETAILS, "icon_path": r"C:\i.ico"}, "x")
        self.assertNotIn("IconLocation", without)
        self.assertIn(r"$shortcut.IconLocation = 'C:\i.ico,0';", with_icon)


class StartMenuTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.enterContext(patch.dict(os.environ, {"APPDATA": self.folder.name}))
        self.path = windows_startup.get_start_menu_shortcut_path()

    def launch_details(self):
        return OperationResult.success(data=DETAILS)

    def test_shortcut_lives_in_the_programs_folder(self):
        self.assertTrue(self.path.endswith(os.path.join("Start Menu", "Programs", "Roblox Account Manager.lnk")))

    def test_enable_reports_success_only_when_the_shortcut_exists(self):
        def create(script, kind):
            open(self.path, "w").close()
            return OperationResult.success()

        with patch.object(windows_startup, "_get_launch_details", return_value=self.launch_details()), \
                patch.object(windows_startup, "_run_powershell", side_effect=create):
            self.assertTrue(windows_startup.enable_start_menu())
        self.assertTrue(windows_startup.is_start_menu_enabled())

    def test_enable_passes_a_powershell_failure_through(self):
        failure = OperationResult.failure("X", "Title", "Message")
        with patch.object(windows_startup, "_get_launch_details", return_value=self.launch_details()), \
                patch.object(windows_startup, "_run_powershell", return_value=failure):
            result = windows_startup.enable_start_menu()
        self.assertFalse(result)
        self.assertFalse(windows_startup.is_start_menu_enabled())

    def test_enable_detects_a_shortcut_that_was_not_created(self):
        with patch.object(windows_startup, "_get_launch_details", return_value=self.launch_details()), \
                patch.object(windows_startup, "_run_powershell", return_value=OperationResult.success()):
            result = windows_startup.enable_start_menu()
        self.assertFalse(result)
        self.assertEqual(result.code, "START_MENU_SHORTCUT_INVALID")

    def test_disable_removes_the_shortcut_and_is_fine_when_missing(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        open(self.path, "w").close()
        self.assertTrue(windows_startup.disable_start_menu())
        self.assertFalse(os.path.exists(self.path))
        self.assertTrue(windows_startup.disable_start_menu())

    def test_missing_appdata_is_reported(self):
        with patch.dict(os.environ, {"APPDATA": ""}):
            self.assertEqual(windows_startup.enable_start_menu().code, "START_MENU_FOLDER_UNAVAILABLE")
            self.assertEqual(windows_startup.disable_start_menu().code, "START_MENU_FOLDER_UNAVAILABLE")
            self.assertFalse(windows_startup.is_start_menu_enabled())


class FailureLabelTests(unittest.TestCase):
    def failing_run(self, kind):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with patch.object(windows_startup.subprocess, "run", return_value=completed):
            return windows_startup._run_powershell("exit 1", kind)

    def test_startup_failure_keeps_its_code(self):
        result = self.failing_run("Startup")
        self.assertEqual(result.code, "STARTUP_SHORTCUT_CREATE_FAILED")
        self.assertIn("Startup shortcut", result.message)

    def test_start_menu_failure_has_its_own_code(self):
        result = self.failing_run("Start Menu")
        self.assertEqual(result.code, "START_MENU_SHORTCUT_CREATE_FAILED")
        self.assertIn("Start Menu shortcut", result.message)


@unittest.skipUnless(sys.platform == "win32", "Shortcuts need Windows")
class RealShortcutTests(unittest.TestCase):
    def test_a_path_with_dollar_sign_and_apostrophe_survives(self):
        with tempfile.TemporaryDirectory() as folder:
            app_dir = os.path.join(folder, "App $Dir's")
            os.makedirs(app_dir)
            target = os.path.join(app_dir, "RAM.exe")
            open(target, "wb").close()
            shortcut = os.path.join(folder, "Test.lnk")
            details = {"target": target, "arguments": "", "working_directory": app_dir, "icon_path": ""}

            result = windows_startup._run_powershell(
                windows_startup._build_shortcut_script(shortcut, details, "Roblox Account Manager"),
                "Start Menu",
            )
            self.assertTrue(result, getattr(result, "detail", ""))

            read_back = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(New-Object -ComObject WScript.Shell).CreateShortcut($env:RAM_SHORTCUT).TargetPath"],
                env={**os.environ, "RAM_SHORTCUT": shortcut},
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(read_back.returncode, 0, read_back.stderr)
            self.assertTrue(
                os.path.samefile(read_back.stdout.strip(), target),
                f"Shortcut points to {read_back.stdout.strip()!r}, expected {target!r}",
            )


if __name__ == "__main__":
    unittest.main()
