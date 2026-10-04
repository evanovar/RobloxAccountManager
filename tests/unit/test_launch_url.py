import unittest
from unittest import mock

from classes.operation_result import OperationResult
from classes.roblox_api import RobloxAPI

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


if __name__ == "__main__":
    unittest.main()
