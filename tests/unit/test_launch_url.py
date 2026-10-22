import unittest
import threading
import contextlib
import io
from unittest import mock

from classes.operation_result import OperationResult
from classes.roblox_api import RobloxAPI
from classes.account_manager import RobloxAccountManager

JOB_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def launch(**kwargs):
    with mock.patch.object(RobloxAPI, "get_auth_ticket", return_value=OperationResult.success(data="TICKET")), \
            mock.patch.object(RobloxAPI, "_execute_launch", return_value=OperationResult.success()) as run:
        result = RobloxAPI.launch_roblox("alice", "cookie", **kwargs)
    return result, run


class LaunchUrlTests(unittest.TestCase):
    def test_valid_place_and_job_id(self):
        result, run = launch(game_id="1818", job_id=JOB_ID)
        self.assertTrue(result)
        url = run.call_args.args[0]
        self.assertIn("&placeId=1818&", url)
        self.assertIn("&gameId=" + JOB_ID + "+", url)

    def test_whitespace_around_place_id_is_ignored(self):
        result, run = launch(game_id=" 1818 ")
        self.assertTrue(result)
        self.assertIn("&placeId=1818&", run.call_args.args[0])

    def test_numeric_private_server_code(self):
        result, run = launch(game_id="1818", private_server_id="123456789")
        self.assertTrue(result)
        self.assertIn("&linkCode=123456789+", run.call_args.args[0])

    def test_rejects_place_id_with_url_syntax(self):
        for bad in ("123&isPlayTogetherGame=true", "123+launchmode:x", "12 3", "²"):
            with self.subTest(place_id=bad):
                result, run = launch(game_id=bad)
                self.assertFalse(result)
                self.assertEqual(result.code, "PLACE_ID_INVALID")
                run.assert_not_called()

    def test_rejects_job_id_with_url_syntax(self):
        for bad in ("abc+placelauncherurl:https://example.com/x", "abc&x=1", "a b"):
            with self.subTest(job_id=bad):
                result, run = launch(game_id="1818", job_id=bad)
                self.assertFalse(result)
                self.assertEqual(result.code, "JOB_ID_INVALID")
                run.assert_not_called()

    def test_rejects_link_code_from_unexpected_source(self):
        with mock.patch.object(RobloxAPI, "resolve_share_url", return_value=("1818", "bad+code")):
            result, run = launch(private_server_id="https://www.roblox.com/share?code=x&type=Server")
        self.assertFalse(result)
        self.assertEqual(result.code, "PRIVATE_SERVER_INVALID")
        run.assert_not_called()

    def test_home_launch_needs_no_ids(self):
        result, run = launch()
        self.assertTrue(result)
        self.assertIn("launchmode:play+gameinfo:TICKET", run.call_args.args[0])

    def test_success_preserves_sent_tracker_and_launch_time_for_home_and_game(self):
        for game_id in ("", "1818"):
            with self.subTest(game_id=game_id), \
                    mock.patch("classes.roblox_api.secrets.randbelow", return_value=123), \
                    mock.patch("classes.roblox_api.time.time", return_value=100.5):
                result, run = launch(game_id=game_id)
            self.assertEqual(result.data, {
                "browser_tracker_id": "1000000000000123", "launch_time": 100.5})
            self.assertIn("+browsertrackerid:1000000000000123+", run.call_args.args[0])
            self.assertIn("+launchtime:100500+", run.call_args.args[0])

    def test_failed_execution_does_not_supply_launch_evidence(self):
        failure = OperationResult.failure("LAUNCH_FAILED", "Failed", "Test failure")
        with mock.patch.object(RobloxAPI, "get_auth_ticket", return_value=OperationResult.success(data="TICKET")), \
                mock.patch.object(RobloxAPI, "_execute_launch", return_value=failure):
            result = RobloxAPI.launch_roblox("alice", "cookie", game_id="1818")
        self.assertIs(result, failure)
        self.assertIsNone(result.data)


class ExecuteLaunchTests(unittest.TestCase):
    URL = "roblox-player:1+launchmode:play+gameinfo:SYNTHETIC-TICKET+placelauncherurl:https://example.com/?linkCode=PRIVATE-CODE"

    def execute_error(self, error):
        output = io.StringIO()
        with mock.patch("classes.roblox_api.os.startfile", side_effect=error), \
                mock.patch("classes.roblox_api.subprocess.Popen") as process, \
                contextlib.redirect_stdout(output):
            result = RobloxAPI._execute_launch(self.URL, "default")
        process.assert_not_called()
        for text in (result.detail, result.message, output.getvalue()):
            self.assertNotIn("SYNTHETIC-TICKET", text)
            self.assertNotIn("PRIVATE-CODE", text)
        return result

    def test_missing_protocol_errors_explain_how_to_choose_an_installed_launcher(self):
        for code in (-2147221003, 0x800401F5, 1155, 0x80070483):
            with self.subTest(code=code):
                error = OSError(0, "Application not found", self.URL)
                error.winerror = code
                result = self.execute_error(error)
                self.assertEqual(result.code, "ROBLOX_PROTOCOL_UNAVAILABLE")
                self.assertIn("Roblox Client (direct .exe)", result.message)
                self.assertIn("Settings > Roblox", result.message)
                self.assertIn(str(code), result.detail)

    def test_other_failures_keep_their_existing_error_categories_without_leaking_the_url(self):
        cases = (
            (PermissionError(13, "Denied", self.URL), "LAUNCH_PERMISSION_DENIED"),
            (FileNotFoundError(2, "Missing", self.URL), "LAUNCHER_NOT_FOUND"),
            (OSError(123, "Other failure", self.URL), "ROBLOX_LAUNCH_FAILED"),
            (RuntimeError(f"Unexpected failure: {self.URL}"), "UNEXPECTED_ERROR"),
        )
        for error, code in cases:
            with self.subTest(code=code):
                self.assertEqual(self.execute_error(error).code, code)

    def test_default_launch_still_passes_the_original_url_to_windows(self):
        with mock.patch("classes.roblox_api.os.startfile") as start:
            self.assertTrue(RobloxAPI._execute_launch(self.URL, "default"))
        start.assert_called_once_with(self.URL)

    def test_protocol_error_does_not_change_explicit_custom_launcher_behavior(self):
        with mock.patch("classes.roblox_api.Path.exists", return_value=True), \
                mock.patch("classes.roblox_api.subprocess.Popen", side_effect=OSError(0, "Application not found", self.URL, -2147221003)), \
                mock.patch("classes.roblox_api.os.startfile") as start, \
                contextlib.redirect_stdout(io.StringIO()):
            result = RobloxAPI._execute_launch(self.URL, "custom", "C:/Example/Launcher.exe")
        self.assertEqual(result.code, "ROBLOX_LAUNCH_FAILED")
        self.assertNotIn("SYNTHETIC-TICKET", result.detail)
        start.assert_not_called()


class LaunchRecordTests(unittest.TestCase):
    def setUp(self):
        self.manager = RobloxAccountManager.__new__(RobloxAccountManager)
        self.manager._accounts_lock = threading.RLock()
        self.manager._launch_records = {}
        self.manager._pre_launch_hook = None
        self.manager.accounts = {"alice": {
            "cookie": "TEST_COOKIE", "user_id": "42", "cookie_valid": True}}
        self.manager.save_accounts = mock.Mock()
        self.launcher = self.enterContext(mock.patch.object(RobloxAPI, "launch_roblox"))

    def test_successful_launch_records_only_identity_and_time(self):
        self.launcher.return_value = OperationResult.success(data={
            "browser_tracker_id": "987", "launch_time": 100.0})
        self.manager.launch_roblox("alice", "1818")
        self.assertEqual(self.manager.get_launch_records(), {"987": ("42", 100.0)})
        self.manager.save_accounts.assert_not_called()

    def test_failed_launch_records_nothing(self):
        self.launcher.return_value = OperationResult.failure("FAILED", "Failed", "Test failure")
        self.assertFalse(self.manager.launch_roblox("alice", "1818"))
        self.assertFalse(self.manager.get_launch_records())

    def test_successful_launch_does_not_clear_saved_invalid_status(self):
        self.manager.accounts["alice"]["cookie_valid"] = False
        self.launcher.return_value = OperationResult.success()
        self.assertTrue(self.manager.launch_roblox("alice", "1818"))
        self.assertFalse(self.manager.accounts["alice"]["cookie_valid"])
        self.manager.save_accounts.assert_not_called()

    def test_launch_without_account_id_records_nothing(self):
        self.manager.accounts["alice"].pop("user_id")
        self.launcher.return_value = OperationResult.success(data={
            "browser_tracker_id": "987", "launch_time": 100.0})
        self.manager.launch_roblox("alice", "1818")
        self.assertFalse(self.manager.get_launch_records())

    def test_record_snapshot_cannot_mutate_shared_state(self):
        self.manager._launch_records["987"] = ("42", 100.0)
        self.manager.get_launch_records().clear()
        self.assertEqual(self.manager.get_launch_records(), {"987": ("42", 100.0)})

    def test_records_are_bounded_when_renamer_is_disabled(self):
        self.manager._launch_records = {str(index): ("42", 100.0) for index in range(256)}
        self.launcher.return_value = OperationResult.success(data={
            "browser_tracker_id": "987", "launch_time": 200.0})
        self.manager.launch_roblox("alice", "1818")
        self.assertEqual(len(self.manager.get_launch_records()), 256)
        self.assertNotIn("0", self.manager.get_launch_records())
        self.assertEqual(self.manager.get_launch_records()["987"], ("42", 200.0))


if __name__ == "__main__":
    unittest.main()
