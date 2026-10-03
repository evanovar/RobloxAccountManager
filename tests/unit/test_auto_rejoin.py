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


if __name__ == "__main__":
    unittest.main()
