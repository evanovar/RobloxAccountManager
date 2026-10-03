import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile
from classes.operation_result import OperationResult
from features import chromium

class ChromiumTests(unittest.TestCase):
    def test_safe_extract_rejects_parent_directory_entry(self):
        with tempfile.TemporaryDirectory() as work_dir:
            archive_path = os.path.join(work_dir, "unsafe.zip")
            output_dir = os.path.join(work_dir, "output")
            os.makedirs(output_dir)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")

            with self.assertRaises(ValueError):
                chromium._safe_extract(archive_path, output_dir)

    def test_validation_does_not_launch_chromium(self):
        with tempfile.TemporaryDirectory() as work_dir:
            browser_path = os.path.join(work_dir, "chrome.exe")
            driver_path = os.path.join(work_dir, "chromedriver.exe")
            build_path = os.path.join(work_dir, "snapshot_build.txt")
            executable_data = b"MZ" + (b"\0" * 8192)
            with open(browser_path, "wb") as handle:
                handle.write(executable_data)
            with open(driver_path, "wb") as handle:
                handle.write(executable_data)
            with open(build_path, "w", encoding="utf-8") as handle:
                handle.write("1234567")

            completed = Mock(
                stdout="ChromeDriver 130.0.1.0",
                stderr="",
            )
            with patch.object(chromium, "_CHROMIUM_EXE", browser_path), \
                    patch.object(chromium, "_CHROMEDRIVER_EXE", driver_path), \
                    patch.object(chromium, "_SNAPSHOT_BUILD_FILE", build_path), \
                    patch.object(
                        chromium,
                        "_get_file_version",
                        return_value="130.0.1.0",
                    ), \
                    patch.object(
                        chromium.subprocess,
                        "run",
                        return_value=completed,
                    ) as run:
                result = chromium.validate_chromium(
                    verify_executables=True
                )

            self.assertTrue(result)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], driver_path)
            self.assertNotEqual(run.call_args.args[0][0], browser_path)

    def test_status_marks_older_snapshot_as_outdated(self):
        completed = threading.Event()
        results = []

        def on_done(result):
            results.append(result)
            completed.set()

        with patch.object(
            chromium,
            "validate_chromium",
            return_value=OperationResult.success(),
        ), patch.object(
            chromium,
            "get_installed_build",
            return_value="1234567",
        ), patch.object(
            chromium,
            "_fetch_latest_build",
            return_value="1234568",
        ):
            chromium.check_chromium_status(on_done)
            self.assertTrue(completed.wait(2))

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0])
        self.assertTrue(results[0].data["outdated"])

    def test_failed_reinstall_restores_previous_install(self):
        completed = threading.Event()
        results = []

        def fake_download(
            url,
            destination,
            start_percent,
            end_percent,
            label,
            on_progress,
            timeout,
        ):
            with zipfile.ZipFile(destination, "w") as archive:
                if destination.endswith("chromium.zip"):
                    archive.writestr(
                        "chrome-win/chrome.exe",
                        b"MZ" + (b"\0" * 8192),
                    )
                else:
                    archive.writestr(
                        "chromedriver.exe",
                        b"MZ" + (b"\0" * 8192),
                    )
            on_progress(end_percent, label)

        def on_done(result):
            results.append(result)
            completed.set()

        with tempfile.TemporaryDirectory() as work_dir:
            chromium_root = os.path.join(work_dir, "Chromium")
            chromium_dir = os.path.join(chromium_root, "chrome-win64")
            os.makedirs(chromium_dir)
            previous_file = os.path.join(chromium_dir, "previous.txt")
            with open(previous_file, "w", encoding="utf-8") as handle:
                handle.write("previous installation")

            validation_failure = OperationResult.failure(
                "CHROMIUM_INVALID",
                "Chromium Installation Invalid",
                "Chromium validation failed.",
            )
            with patch.object(
                chromium,
                "_CHROMIUM_ROOT",
                chromium_root,
            ), patch.object(
                chromium,
                "_CHROMIUM_DIR",
                chromium_dir,
            ), patch.object(
                chromium,
                "_fetch_latest_build",
                return_value="1234568",
            ), patch.object(
                chromium,
                "_download_file",
                side_effect=fake_download,
            ), patch.object(
                chromium,
                "validate_chromium",
                return_value=validation_failure,
            ):
                chromium.download_chromium(
                    lambda *_: None,
                    on_done,
                )
                self.assertTrue(completed.wait(5))

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].code, "CHROMIUM_INVALID")
            self.assertTrue(os.path.isfile(previous_file))
