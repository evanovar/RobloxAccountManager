import base64
import os
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from features import updater


def response(status=200, payload=None, raises=False):
    result = MagicMock(status_code=status)
    if raises:
        result.json.side_effect = ValueError("not json")
    else:
        result.json.return_value = payload
    return result


class LatestReleaseTests(unittest.TestCase):
    def fetch(self, reply):
        with patch.object(updater.requests, "get", return_value=reply):
            return updater.get_latest_release()

    def test_version_notes_and_link_are_returned(self):
        result = self.fetch(response(payload={
            "tag_name": "v2.8.0", "body": "  ## New\n- search  ", "html_url": "https://github.com/x/y/releases/tag/v2.8.0",
        }))
        self.assertTrue(result)
        self.assertEqual(result.data, {
            "version": "2.8.0", "notes": "## New\n- search", "url": "https://github.com/x/y/releases/tag/v2.8.0",
        })

    def test_missing_notes_and_link_get_defaults(self):
        result = self.fetch(response(payload={"tag_name": "2.8.0", "body": None}))
        self.assertEqual(result.data["notes"], "")
        self.assertEqual(result.data["url"], updater.RELEASES_PAGE)

    def test_very_long_notes_are_cut(self):
        result = self.fetch(response(payload={"tag_name": "v1", "body": "x" * 50000}))
        self.assertEqual(len(result.data["notes"]), updater.MAX_NOTES_LENGTH)

    def test_http_errors_are_reported_with_the_status(self):
        for status, retryable in ((404, False), (403, False), (429, True), (503, True)):
            with self.subTest(status=status):
                result = self.fetch(response(status=status))
                self.assertFalse(result)
                self.assertEqual(result.code, "UPDATE_CHECK_FAILED")
                self.assertIn(str(status), result.detail)
                self.assertEqual(result.retryable, retryable)

    def test_network_errors_are_reported_as_retryable(self):
        with patch.object(updater.requests, "get", side_effect=requests.ConnectionError("offline")):
            result = updater.get_latest_release()
        self.assertFalse(result)
        self.assertTrue(result.retryable)
        self.assertIn("ConnectionError", result.detail)

    def test_unusable_replies_are_reported(self):
        for reply in (response(raises=True), response(payload={}), response(payload={"tag_name": "  "}), response(payload=[])):
            with self.subTest(reply=reply.json.return_value if not reply.json.side_effect else "bad json"):
                self.assertEqual(self.fetch(reply).code, "UPDATE_CHECK_FAILED")

    def test_the_old_helper_still_returns_just_the_version(self):
        with patch.object(updater.requests, "get", return_value=response(payload={"tag_name": "v2.8.0"})):
            self.assertEqual(updater.check_latest_version(), "2.8.0")
        with patch.object(updater.requests, "get", return_value=response(status=500)):
            self.assertIsNone(updater.check_latest_version())


class LaunchInstallerTests(unittest.TestCase):
    def launch(self, **kwargs):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(updater, "_build_update_log_path", return_value=os.path.join(folder, "update.log")), \
                patch.object(updater.subprocess, "Popen") as popen:
            updater._launch_installer("C:/tmp/update.exe", "C:/App Dir/RAM.exe", folder, **kwargs)
        return popen.call_args.args[0]

    def value_after(self, command, flag):
        return command[command.index(flag) + 1]

    def test_powershell_is_started_by_its_full_system_path(self):
        command = self.launch()
        self.assertTrue(os.path.isabs(command[0]))
        self.assertTrue(command[0].lower().endswith(os.path.join("windowspowershell", "v1.0", "powershell.exe")))
        self.assertNotEqual(command[0].lower(), "powershell.exe")

    def test_the_checksum_is_passed_to_the_script(self):
        self.assertEqual(self.value_after(self.launch(expected_sha256="ABCD"), "-ExpectedSha256"), "ABCD")
        self.assertEqual(self.value_after(self.launch(), "-ExpectedSha256"), "")

    def test_launch_arguments_survive_spaces_and_quotes(self):
        arguments = ["--data-dir", "D:/My Profiles/Alt", 'say "hi"']
        encoded = self.value_after(self.launch(launch_arguments=arguments), "-LaunchArgumentsBase64")
        self.assertEqual(base64.b64decode(encoded).decode("utf-8"), subprocess.list2cmdline(arguments))

    def test_no_arguments_means_nothing_is_passed(self):
        self.assertEqual(self.value_after(self.launch(), "-LaunchArgumentsBase64"), "")
        self.assertEqual(self.value_after(self.launch(launch_arguments=[]), "-LaunchArgumentsBase64"), "")

    def test_the_destination_and_this_process_are_passed(self):
        command = self.launch()
        self.assertEqual(self.value_after(command, "-DestinationPath"), "C:/App Dir/RAM.exe")
        self.assertEqual(self.value_after(command, "-TargetProcessId"), str(os.getpid()))


class DownloadHandsOverDigestTests(unittest.TestCase):
    def test_the_published_digest_and_the_original_arguments_reach_the_installer(self):
        import threading
        content = b"MZ" + b"\x00" * 600
        import hashlib
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        asset = {
            "url": "https://github.com/evanovar/RobloxAccountManager/releases/download/v1/EvanovarRAM-v1.0.0.exe",
            "name": "EvanovarRAM-v1.0.0.exe", "size": len(content), "digest": digest,
        }
        reply = MagicMock(headers={"content-length": str(len(content))})
        reply.iter_content.return_value = [content]
        finished = threading.Event()
        with patch.object(updater, "get_update_target", return_value="C:/app/RAM.exe"), \
                patch.object(updater, "get_exe_asset", return_value=asset), \
                patch.object(updater.requests, "get", return_value=reply), \
                patch.object(updater.sys, "argv", ["RAM.exe", "--data-dir", "D:/x"]), \
                patch.object(updater, "_launch_installer") as launch:
            updater.download_update(lambda _: None, lambda ok, message: finished.set())
            self.assertTrue(finished.wait(10))
        launch.assert_called_once()
        self.assertEqual(launch.call_args.kwargs["expected_sha256"], digest.split(":")[1].upper())
        self.assertEqual(launch.call_args.kwargs["launch_arguments"], ["--data-dir", "D:/x"])


if __name__ == "__main__":
    unittest.main()
