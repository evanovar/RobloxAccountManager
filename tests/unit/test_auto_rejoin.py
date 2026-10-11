import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import features.auto_rejoin as auto_rejoin


class AutoRejoinTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(auto_rejoin._PID_UID_CACHE, {}, clear=True))

    def test_scan_keeps_all_processes_for_each_user(self):
        first = (101, 10.0)
        second = (202, 20.0)
        processes = {
            101: (10.0, Mock()),
            202: (20.0, Mock()),
        }
        with patch.object(
            auto_rejoin,
            "_get_roblox_processes",
            return_value=processes,
        ), patch.object(
            auto_rejoin.presence_mod,
            "_get_user_id_from_pid",
            side_effect=lambda pid, used: "111" if pid == 101 else "222",
        ):
            result = auto_rejoin.scan_pid_uid_map({"111", "222"})

        self.assertEqual(result, {"111": {first}, "222": {second}})

    def test_termination_waits_for_process_to_exit(self):
        identity = (101, 10.0)
        alive = {101: (10.0, Mock())}
        with patch.object(
            auto_rejoin,
            "_get_roblox_processes",
            side_effect=[alive, {}],
        ), patch.object(
            auto_rejoin.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ) as run:
            closed, detail = auto_rejoin._terminate_process(identity, "test")

        self.assertTrue(closed, detail)
        self.assertEqual(
            run.call_args.args[0],
            ["taskkill", "/T", "/F", "/PID", "101"],
        )

    def test_launch_tracking_requires_matching_user_id(self):
        worker = auto_rejoin.AutoRejoinWorker(
            "test",
            {},
            SimpleNamespace(launch_roblox=Mock(return_value=True)),
            lambda *_: None,
        )
        worker._stop.wait = lambda _: False
        before = {101: (10.0, Mock())}
        after = {101: (10.0, Mock()), 303: (30.0, Mock())}
        with patch.object(
            auto_rejoin,
            "_get_roblox_processes",
            side_effect=[before, after],
        ), patch.object(
            auto_rejoin.presence_mod,
            "_get_user_id_from_pid",
            return_value="333",
        ), patch.object(
            auto_rejoin.settings_store,
            "load",
            return_value={},
        ), patch.object(
            auto_rejoin.time,
            "monotonic",
            side_effect=[0.0, 1.0],
        ):
            result = worker._launch_and_track("333", "123", "", "")

        self.assertTrue(result)
        self.assertEqual(worker._process_identity, (303, 30.0))

    def test_presence_states_distinguish_unavailable_and_disconnect(self):
        worker = auto_rejoin.AutoRejoinWorker(
            "test",
            {},
            SimpleNamespace(accounts={}),
            lambda *_: None,
        )
        worker._process_identity = (101, 10.0)
        with patch.object(
            auto_rejoin,
            "_identity_matches",
            return_value=True,
        ), patch.object(auto_rejoin, "_wait_presence_slot", return_value=True):
            with patch.object(
                auto_rejoin.RobloxAPI,
                "get_player_presence",
                return_value=None,
            ):
                self.assertEqual(
                    worker._is_in_game("333", "cookie", "123"),
                    ("unavailable", ""),
                )

            with patch.object(
                auto_rejoin.RobloxAPI,
                "get_player_presence",
                return_value={
                    "in_game": True,
                    "place_id": "123",
                    "game_id": "job",
                },
            ):
                self.assertEqual(
                    worker._is_in_game("333", "cookie", "123"),
                    ("in_game", "job"),
                )

            with patch.object(
                auto_rejoin.RobloxAPI,
                "get_player_presence",
                return_value={"in_game": False},
            ):
                self.assertEqual(
                    worker._is_in_game("333", "cookie", "123"),
                    ("disconnected", ""),
                )

    def test_presence_can_check_online_status_without_place_id(self):
        worker = auto_rejoin.AutoRejoinWorker(
            "test",
            {},
            SimpleNamespace(accounts={}),
            lambda *_: None,
        )
        worker._process_identity = (101, 10.0)
        with patch.object(
            auto_rejoin,
            "_identity_matches",
            return_value=True,
        ), patch.object(
            auto_rejoin,
            "_wait_presence_slot",
            return_value=True,
        ), patch.object(
            auto_rejoin.RobloxAPI,
            "get_player_presence",
            return_value={"status": 1, "in_game": False},
        ):
            self.assertEqual(
                worker._is_in_game("333", "cookie", "123", False),
                ("in_game", ""),
            )

    def test_presence_requires_the_tracked_process(self):
        worker = auto_rejoin.AutoRejoinWorker(
            "test",
            {},
            SimpleNamespace(accounts={}),
            lambda *_: None,
        )
        worker._process_identity = (101, 10.0)
        with patch.object(
            auto_rejoin,
            "_identity_matches",
            return_value=False,
        ), patch.object(
            auto_rejoin.RobloxAPI,
            "get_player_presence",
        ) as get_presence:
            self.assertEqual(
                worker._is_in_game("333", "cookie", "123", False),
                ("disconnected", ""),
            )
            get_presence.assert_not_called()

    def user_worker(self, target="TargetUser"):
        return auto_rejoin.AutoRejoinWorker(
            "test", {"join_mode": "user", "target_user": target, "max_retries": 1},
            SimpleNamespace(accounts={"test": {"user_id": "333", "cookie": "cookie"}}),
            Mock(),
        )

    def test_user_destination_refreshes_the_server_and_caches_only_the_user_id(self):
        worker = self.user_worker()
        with patch.object(auto_rejoin, "_wait_presence_slot", return_value=True), \
                patch.object(auto_rejoin.RobloxAPI, "get_user_id_from_username", return_value=123) as resolve, \
                patch.object(auto_rejoin.RobloxAPI, "get_player_presence", side_effect=[
                    {"in_game": True, "place_id": 10, "game_id": "first-server"},
                    {"in_game": True, "place_id": 20, "game_id": "second-server"},
                ]) as presence:
            self.assertEqual(worker._resolve_destination("cookie", "stale-server"), ("10", "", "first-server"))
            self.assertEqual(worker._resolve_destination("cookie", "stale-server"), ("20", "", "second-server"))
        resolve.assert_called_once_with("TargetUser", max_retries=1)
        self.assertEqual(presence.call_count, 2)
        presence.assert_called_with(123, "cookie")

    def test_numeric_target_does_not_use_a_username_lookup(self):
        worker = self.user_worker("123")
        with patch.object(auto_rejoin, "_wait_presence_slot", return_value=True), \
                patch.object(auto_rejoin.RobloxAPI, "get_user_id_from_username") as resolve, \
                patch.object(auto_rejoin.RobloxAPI, "get_player_presence", return_value={
                    "in_game": True, "place_id": 10, "game_id": "server",
                }):
            self.assertEqual(worker._resolve_destination("cookie"), ("10", "", "server"))
        resolve.assert_not_called()

    def test_user_server_check_distinguishes_two_servers_in_the_same_place(self):
        worker = self.user_worker("123")
        worker._process_identity = (101, 10.0)
        with patch.object(auto_rejoin, "_identity_matches", return_value=True), \
                patch.object(auto_rejoin, "_wait_presence_slot", return_value=True), \
                patch.object(auto_rejoin.RobloxAPI, "get_player_presence", return_value={
                    "in_game": True, "place_id": 10, "game_id": "other-server",
                }):
            self.assertEqual(worker._is_in_game("333", "cookie", "10", True, "target-server"),
                             ("disconnected", "other-server"))
            self.assertEqual(worker._is_in_game("333", "cookie", "10"), ("in_game", "other-server"))

    def test_offline_or_hidden_targets_do_not_fall_back_to_a_random_server(self):
        for presence in (None, {"in_game": False}, {"in_game": True, "place_id": 10},
                         {"in_game": True, "game_id": "server"}):
            with self.subTest(presence=presence), \
                    patch.object(auto_rejoin, "_wait_presence_slot", return_value=True), \
                    patch.object(auto_rejoin.RobloxAPI, "get_player_presence", return_value=presence):
                worker = self.user_worker("123")
                self.assertIsNone(worker._resolve_destination("cookie"))
                self.assertTrue(worker.on_status.call_args.args[1].startswith("Waiting:"))

    def test_stopping_during_target_lookup_prevents_a_launch_destination(self):
        worker = self.user_worker("123")

        def presence(*_args):
            worker._stop.set()
            return {"in_game": True, "place_id": 10, "game_id": "server"}

        with patch.object(auto_rejoin, "_wait_presence_slot", return_value=True), \
                patch.object(auto_rejoin.RobloxAPI, "get_player_presence", side_effect=presence):
            self.assertIsNone(worker._resolve_destination("cookie"))

    def test_old_place_configs_keep_private_links_and_previous_job_fallback(self):
        worker = self.user_worker()
        worker.config = {"place_id": "10", "private_server": "private"}
        self.assertEqual(worker._resolve_destination("cookie", "previous"), ("10", "private", "previous"))
        worker.config["job_id"] = "configured"
        self.assertEqual(worker._resolve_destination("cookie", "previous"), ("10", "private", "configured"))

    def test_user_mode_launches_without_a_place_config_and_rejoins_the_new_server(self):
        worker = self.user_worker("123")
        worker._stop.wait = lambda seconds: seconds == 10
        with patch.object(worker, "_can_launch", return_value=True), \
                patch.object(worker, "_wait", return_value=False), \
                patch.object(worker, "_launch_and_track", return_value=True) as launch, \
                patch.object(worker, "_is_in_game", return_value=("disconnected", "stale-server")), \
                patch.object(auto_rejoin, "find_running_processes_for_user", return_value=set()), \
                patch.object(auto_rejoin, "_wait_presence_slot", return_value=True), \
                patch.object(auto_rejoin.RobloxAPI, "get_player_presence", side_effect=[
                    {"in_game": True, "place_id": 10, "game_id": "first-server"},
                    {"in_game": True, "place_id": 20, "game_id": "second-server"},
                ]):
            worker._run()
        self.assertEqual([call.args for call in launch.call_args_list], [
            ("333", "10", "", "first-server"), ("333", "20", "", "second-server"),
        ])

    def test_waiting_for_the_target_does_not_use_launch_retries(self):
        worker = self.user_worker("123")
        worker._stop.wait = lambda _: False
        with patch.object(worker, "_can_launch", return_value=True), \
                patch.object(worker, "_wait", side_effect=[False, False, True]), \
                patch.object(worker, "_launch_and_track", return_value=True) as launch, \
                patch.object(worker, "_is_in_game", return_value=("in_game", "server")), \
                patch.object(auto_rejoin, "find_running_processes_for_user", return_value=set()), \
                patch.object(auto_rejoin, "_wait_presence_slot", return_value=True), \
                patch.object(auto_rejoin.RobloxAPI, "get_player_presence", side_effect=[
                    {"in_game": False}, {"in_game": True, "place_id": 10},
                    {"in_game": True, "place_id": 10, "game_id": "server"},
                ]):
            worker._run()
        launch.assert_called_once_with("333", "10", "", "server")
        self.assertFalse(any("STOPPED" in call.args[1] for call in worker.on_status.call_args_list))


if __name__ == "__main__":
    unittest.main()
