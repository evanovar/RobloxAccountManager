import unittest
import threading
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
