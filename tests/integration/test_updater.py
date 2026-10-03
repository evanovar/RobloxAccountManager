import subprocess
import sys
import os
import tempfile
import unittest
from features import updater


@unittest.skipUnless(sys.platform == "win32", "Requires Windows PowerShell")
class UpdaterPowerShellTests(unittest.TestCase):
    def test_installer_script_has_valid_powershell_syntax(self):
        with tempfile.TemporaryDirectory() as work_dir:
            script_path = os.path.join(work_dir, "install_update.ps1")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(updater._build_installer_script())
            escaped_path = script_path.replace("'", "''")
            parse_command = (
                "$errors=$null; "
                "[void][System.Management.Automation.Language.Parser]::"
                f"ParseFile('{escaped_path}',[ref]$null,[ref]$errors); "
                "if($errors.Count){$errors | Out-String | Write-Error; exit 1}"
            )
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    parse_command,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
