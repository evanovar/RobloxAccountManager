import threading
import unittest
from unittest.mock import Mock, patch

from classes.account_manager import RobloxAccountManager
from classes.operation_result import OperationResult
from features import account_actions as actions, launch_monitor as monitor


class LaunchSlotTests(unittest.TestCase):
    def setUp(self):
        self.session = {"mode": "handle64"}
        self.now = 0.0
        self.key = (123, 100.0)
        self.enterContext(patch.object(actions, "_mr_handle", self.session))
        self.active = self.enterContext(patch.object(actions, "is_multi_roblox_running", return_value=True))
        self.handles = self.enterContext(patch.object(actions, "singleton_handles_ready", return_value=True))
        self.enterContext(patch.object(monitor, "_snapshot", return_value={self.key: Mock()}))
        self.enterContext(patch.object(monitor, "_TIMEOUT", 5.0))
        self.enterContext(patch.object(monitor.time, "monotonic", side_effect=lambda: self.now))
        self.enterContext(patch.object(monitor.time, "sleep", side_effect=self.sleep))

    def sleep(self, seconds):
        self.now += seconds

    def test_slot_blocks_until_all_live_handles_are_clear(self):
        self.handles.side_effect = lambda _: self.now >= 1.0
        self.assertTrue(monitor.wait_for_launch_slot(self.session))
        self.assertGreaterEqual(self.now, 1.0)
        self.handles.assert_called_with({self.key})

    def test_unready_slot_times_out_before_dispatch(self):
        self.handles.return_value = False
        self.assertEqual(monitor.wait_for_launch_slot(self.session).code, "MULTI_ROBLOX_NOT_READY")

    def test_default_mode_does_not_wait_for_handles(self):
        self.session["mode"] = "default"
        self.assertTrue(monitor.wait_for_launch_slot(self.session))
        self.handles.assert_not_called()

    def test_stopped_or_restarted_multi_roblox_sends_nothing(self):
        self.active.return_value = False
        self.assertEqual(monitor.wait_for_launch_slot(self.session).code, "MULTI_ROBLOX_STOPPED")
        self.active.return_value = True
        actions._mr_handle = {"mode": "handle64"}
        self.assertEqual(monitor.wait_for_launch_slot(self.session).code, "MULTI_ROBLOX_STOPPED")


class LaunchGateTests(unittest.TestCase):
    def setUp(self):
        self.manager = RobloxAccountManager.__new__(RobloxAccountManager)
        self.manager._launch_roblox = Mock(return_value=OperationResult.success(data={"browser_tracker_id": "987"}))
        self.session = {"mode": "handle64"}
        self.enterContext(patch.object(actions, "_mr_handle", self.session))
        self.active = self.enterContext(patch.object(actions, "is_multi_roblox_running", return_value=True))
        self.slot = self.enterContext(patch.object(monitor, "wait_for_launch_slot", return_value=OperationResult.success()))

    def test_successful_launch_command_is_returned_without_waiting_for_the_client(self):
        result = self.manager.launch_roblox("alice")
        self.assertIs(result, self.manager._launch_roblox.return_value)
        self.slot.assert_called_once_with(self.session)

    def test_failed_launch_does_not_block_the_next_account(self):
        self.manager._launch_roblox.side_effect = [
            OperationResult.failure("AUTH_FAILED", "Failed", "Rejected"),
            OperationResult.success(),
        ]
        self.assertFalse(self.manager.launch_roblox("alice"))
        self.assertTrue(self.manager.launch_roblox("bob"))
        self.assertEqual(self.manager._launch_roblox.call_count, 2)

    def test_unready_handles_skip_only_this_launch(self):
        failure = OperationResult.failure("MULTI_ROBLOX_NOT_READY", "Failed", "Busy")
        self.slot.side_effect = [failure, OperationResult.success()]
        self.assertIs(self.manager.launch_roblox("alice"), failure)
        self.assertTrue(self.manager.launch_roblox("bob"))
        self.manager._launch_roblox.assert_called_once()

    def test_disabled_multi_roblox_preserves_single_client_behavior(self):
        self.active.return_value = False
        self.assertIs(self.manager.launch_roblox("alice"), self.manager._launch_roblox.return_value)
        self.slot.assert_not_called()

    def test_overlapping_launches_run_one_at_a_time(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def launch(username, *_args):
            calls.append(username)
            if username == "alice":
                entered.set()
                release.wait(5)
            return OperationResult.success()

        self.manager._launch_roblox.side_effect = launch
        first = threading.Thread(target=self.manager.launch_roblox, args=("alice",))
        second = threading.Thread(target=self.manager.launch_roblox, args=("bob",))
        first.start()
        try:
            self.assertTrue(entered.wait(5))
            second.start()
            second.join(0.2)
            self.assertEqual(calls, ["alice"])
        finally:
            release.set()
            first.join(5)
            second.join(5)
        self.assertEqual(calls, ["alice", "bob"])


class BatchTests(unittest.TestCase):
    INVOCATIONS = (
        lambda manager, users, done: actions.join_place_all(manager, users, "1818", on_done=done),
        lambda manager, users, done: actions.launch_home(manager, users, on_done=done),
        lambda manager, users, done: actions.join_job_id(manager, users, "1818", "job", on_done=done),
        lambda manager, users, done: actions.join_user(manager, users, "target", on_done=done),
        lambda manager, users, done: actions.join_small_server(manager, users, "1818", on_done=done),
    )

    def run_batch(self, invoke, users, launch_results, delay=0):
        manager = Mock()
        manager.accounts = {name: {"cookie": "synthetic"} for name in users}
        manager.launch_roblox.side_effect = launch_results
        finished = threading.Event()
        results = []

        def done(ok, result):
            results.append(result)
            finished.set()

        response = Mock()
        response.json.return_value = {"data": [{"id": "job", "playing": 1, "maxPlayers": 10}]}
        with patch.object(actions, "load_ui_settings", return_value={"launch_delay_seconds": delay}), \
                patch.object(actions, "_wait_between_launches") as wait, \
                patch.object(actions.RobloxAPI, "get_user_id_from_username", return_value=42), \
                patch.object(actions.RobloxAPI, "get_player_presence", return_value={
                    "in_game": True, "place_id": 1818, "game_id": "job",
                }), patch.object(actions.requests, "get", return_value=response):
            invoke(manager, users, done)
            self.assertTrue(finished.wait(5))
        return manager, wait, results[0]

    def test_multi_roblox_failures_stop_every_batch_entry_point(self):
        for code in sorted(monitor.SESSION_FAILURE_CODES):
            for index, invoke in enumerate(self.INVOCATIONS):
                with self.subTest(code=code, entry_point=index):
                    failure = OperationResult.failure(code, "Not sent", "Restart Multi Roblox")
                    manager, wait, result = self.run_batch(invoke, ["alice", "bob"], [failure] * 2, delay=300)
                    manager.launch_roblox.assert_called_once()
                    wait.assert_not_called()
                    self.assertEqual(result.code, code)

    def test_one_failed_account_does_not_stop_the_rest(self):
        for index, invoke in enumerate(self.INVOCATIONS):
            with self.subTest(entry_point=index):
                manager, _wait, result = self.run_batch(invoke, ["alice", "bob"], [
                    OperationResult.failure("AUTH_FAILED", "Failed", "Rejected"),
                    OperationResult.success(),
                ])
                self.assertEqual(manager.launch_roblox.call_count, 2)
                self.assertFalse(result)
                self.assertIn("1/2", result.message)
                self.assertIn("alice: AUTH_FAILED", result.detail)

    def test_successful_launches_count_without_checking_the_clients(self):
        result = actions._batch_launch_result("Joined", 2, 2, [])
        self.assertTrue(result)
        self.assertEqual(result.message, "Joined 2/2 accounts.")


class HandleReadinessTests(unittest.TestCase):
    def test_only_verified_monitor_results_allow_next_launch(self):
        key = (123, 100.0)
        for outcome, expected in ((actions._MR_H64_CLOSED, True), (actions._MR_H64_ALREADY_CLEAR, True),
                                  (actions._MR_H64_RETRY, False), (actions._MR_H64_PROCESS_GONE, False)):
            with self.subTest(outcome=outcome):
                stop = threading.Event()

                def thread_factory(target, args, **kwargs):
                    worker = Mock()
                    worker.start.side_effect = lambda: target(*args)
                    return worker

                with patch.object(actions, "_mr_h64_ready", set()), \
                        patch.object(actions, "_mr_h64_worker_threads", set()), \
                        patch.object(actions, "_mr_h64_session_active", side_effect=lambda *_: not stop.is_set()), \
                        patch.object(actions.presence_mod, "get_roblox_processes", return_value={123: (100.0, Mock())}), \
                        patch.object(actions, "_mr_h64_process_worker", return_value=outcome), \
                        patch.object(actions.threading, "Thread", side_effect=thread_factory), \
                        patch.object(actions, "_mr_h64_wait", side_effect=lambda *_: stop.set()):
                    actions._mr_h64_monitor_worker(stop, 1, "test.exe")
                    self.assertEqual(actions.singleton_handles_ready({key}), expected)
                    self.assertFalse(actions.singleton_handles_ready({(123, 200.0)}))

    def test_late_result_from_stopped_session_is_not_published(self):
        stop = threading.Event()

        def finish(*args, **kwargs):
            stop.set()
            return actions._MR_H64_CLOSED

        def thread_factory(target, args, **kwargs):
            worker = Mock()
            worker.start.side_effect = lambda: target(*args)
            return worker

        with patch.object(actions, "_mr_h64_ready", set()), \
                patch.object(actions, "_mr_h64_worker_threads", set()), \
                patch.object(actions, "_mr_h64_session_active", side_effect=lambda *_: not stop.is_set()), \
                patch.object(actions.presence_mod, "get_roblox_processes", return_value={123: (100.0, Mock())}), \
                patch.object(actions, "_mr_h64_process_worker", side_effect=finish), \
                patch.object(actions.threading, "Thread", side_effect=thread_factory), \
                patch.object(actions, "_mr_h64_wait", return_value=False):
            actions._mr_h64_monitor_worker(stop, 1, "test.exe")
            self.assertFalse(actions.singleton_handles_ready({(123, 100.0)}))


if __name__ == "__main__":
    unittest.main()
