from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import build
from utils import runtime_check


class FrozenBuildTests(unittest.TestCase):
    def test_python_dlls_are_selected_even_with_foreign_openssl_on_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "python" / "DLLs"
            foreign = root / "foreign"
            runtime.mkdir(parents=True)
            foreign.mkdir()
            names = ("libssl-3-x64.dll", "libcrypto-3-x64.dll")
            for name in names:
                (runtime / name).touch()
                (foreign / name).touch()
            extension = SimpleNamespace(__file__=str(runtime / "_ssl.pyd"))
            with patch.object(sys, "platform", "win32"), patch.dict(
                sys.modules, {"_ssl": extension}
            ), patch.dict(os.environ, {"PATH": str(foreign)}):
                selected = build.collect_ssl_binaries()
            self.assertEqual(selected, [(str((runtime / name).resolve()), ".") for name in names])

    def test_missing_python_dll_does_not_fall_back_to_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "libssl-3-x64.dll").touch()
            extension = SimpleNamespace(__file__=str(root / "_ssl.pyd"))
            with patch.object(sys, "platform", "win32"), patch.dict(
                sys.modules, {"_ssl": extension}
            ), self.assertRaisesRegex(RuntimeError, "Refusing to use DLLs from PATH"):
                build.collect_ssl_binaries()

    def test_frozen_validation_rejects_missing_ssl_and_different_openssl(self):
        reports = (
            {"ok": False, "error": "ImportError: DLL load failed"},
            {"ok": True, "openssl_version": "foreign OpenSSL"},
        )
        for report in reports:
            with self.subTest(report=report):
                def run(command, **kwargs):
                    Path(command[2]).write_text(json.dumps(report), encoding="utf-8")
                    return SimpleNamespace(returncode=0)

                with patch.object(build.subprocess, "run", side_effect=run), self.assertRaises(RuntimeError):
                    build.validate_frozen_runtime()

    def test_frozen_validation_requires_a_report(self):
        with patch.object(build.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
            with self.assertRaisesRegex(RuntimeError, "did not produce a runtime report"):
                build.validate_frozen_runtime()

    def test_failed_executable_check_prevents_release_asset_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "app.exe"
            output.touch()
            with patch.object(build, "OUTPUT_PATH", output), patch.object(
                build, "validate_build_files"
            ), patch.object(build, "read_app_version", return_value="1.2.3"), patch.object(
                build, "validate_release_tag", return_value=True
            ), patch.object(build, "generate_version_info"), patch.object(
                build.subprocess, "run", return_value=SimpleNamespace(returncode=0)
            ), patch.object(build, "validate_frozen_runtime", side_effect=RuntimeError("broken SSL")), patch.object(
                build, "create_release_asset"
            ) as release, redirect_stdout(io.StringIO()):
                self.assertEqual(build.main(), 1)
                release.assert_not_called()

    def test_runtime_check_reports_ssl_import_failure_without_starting_ui(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "runtime.json"
            with patch.dict(sys.modules, {"ssl": None}):
                self.assertEqual(runtime_check.helper_main([str(report)]), 1)
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(result["ok"])
            self.assertIn("ssl", result["error"])

    def test_entry_point_check_works_without_creating_account_data(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "runtime.json"
            result = subprocess.run(
                [sys.executable, str(build.SOURCE_ROOT / "main.py"), "--build-self-test", str(report)],
                cwd=directory, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")), {
                "ok": True, "openssl_version": ssl.OPENSSL_VERSION,
            })
            self.assertEqual(list(Path(directory).iterdir()), [report])


if __name__ == "__main__":
    unittest.main()
