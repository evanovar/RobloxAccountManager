import threading
import unittest
from unittest.mock import Mock, patch

import psutil

from classes.account_manager import RobloxAccountManager
from classes.operation_result import OperationResult
from features import account_actions as actions, launch_monitor as monitor


class LaunchConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.session = {"mode": "handle64"}
        self.now = 0.0
        self.process = Mock()
        self.process.cmdline.return_value = ["RobloxPlayerBeta.exe", "roblox-player:1+browsertrackerid:987+"]
        self.process.is_running.return_value = True
        self.key = (123, 100.0)
        self.result = OperationResult.success(data={"browser_tracker_id": "987", "launch_time": 99.0})
        self.enterContext(patch.object(actions, "_mr_handle", self.session))
        self.active = self.enterContext(patch.object(actions, "is_multi_roblox_running", return_value=True))
        self.handles = self.enterContext(patch.object(actions, "singleton_handles_ready", return_value=True))
        self.snapshot = self.enterContext(patch.object(monitor, "_snapshot", return_value={self.key: self.process}))
        self.window = self.enterContext(patch.object(monitor, "_has_main_window", return_value=True))
        self.enterContext(patch.object(monitor, "_TIMEOUT", 5.0))
        self.enterContext(patch.object(monitor.time, "monotonic", side_effect=lambda: self.now))
        self.enterContext(patch.object(monitor.time, "sleep", side_effect=self.sleep))

    def sleep(self, seconds):
        self.now += seconds

    def confirm(self, before=()):
        return monitor.confirm_launch(self.result, self.session, set(before), "alice")

    def test_window_and_handle_clearance_must_survive_the_stability_interval(self):
        self.window.side_effect = lambda _: self.now >= 1.0
        self.handles.side_effect = lambda _: self.now >= 2.0
        result = self.confirm()
        self.assertTrue(result)
        self.assertGreaterEqual(self.now, 4.0)
        self.assertEqual(result.data["process_identity"], self.key)
        self.assertEqual(result.data["browser_tracker_id"], "987")

    def test_handle_timeout_does_not_report_success(self):
        self.handles.return_value = False
        self.assertEqual(self.confirm().code, "ROBLOX_LAUNCH_UNCONFIRMED")

    def test_matching_process_without_window_is_not_success(self):
        self.window.return_value = False
        self.assertFalse(self.confirm())

    def test_unrelated_or_preexisting_client_cannot_confirm_launch(self):
        self.assertFalse(self.confirm(before=[self.key]))
        self.now = 0
        self.process.cmdline.return_value = ["browsertrackerid:1234"]
        self.assertFalse(self.confirm())

    def test_inaccessible_command_line_remains_unconfirmed(self):
        self.process.cmdline.side_effect = psutil.AccessDenied(123)
        self.assertEqual(self.confirm().code, "ROBLOX_LAUNCH_UNCONFIRMED")

    def test_duplicate_tracker_is_ambiguous(self):
        self.snapshot.return_value[(124, 101.0)] = self.process
        self.assertEqual(self.confirm().code, "LAUNCH_IDENTITY_AMBIGUOUS")

    def test_observed_client_exits_before_ready(self):
        self.window.return_value = False
        self.snapshot.side_effect = [{self.key: self.process}, {}]
        self.process.is_running.return_value = False
        self.assertEqual(self.confirm().code, "ROBLOX_CLIENT_EXITED")

    def test_replacement_process_must_complete_its_own_stability_interval(self):
        replacement = (124, 101.0)
        self.snapshot.side_effect = lambda: {
            self.key if self.now < 1.0 else replacement: self.process,
        }
        result = self.confirm()
        self.assertTrue(result)
        self.assertGreaterEqual(self.now, 3.0)
        self.assertEqual(result.data["process_identity"], replacement)

    def test_mode_stop_or_restart_interrupts_confirmation(self):
        self.active.return_value = False
        self.assertEqual(self.confirm().code, "MULTI_ROBLOX_STOPPED")
        self.active.return_value = True
        actions._mr_handle = {"mode": "handle64"}
        self.assertEqual(self.confirm().code, "MULTI_ROBLOX_STOPPED")

    def test_slot_blocks_until_all_live_handles_are_clear(self):
        self.handles.side_effect = lambda _: self.now >= 1.0
        self.assertTrue(monitor.wait_for_launch_slot(self.session))
        self.assertGreaterEqual(self.now, 1.0)
        self.handles.assert_called_with({self.key})

    def test_unready_slot_times_out_before_dispatch(self):
        self.handles.return_value = False
        self.assertEqual(monitor.wait_for_launch_slot(self.session).code, "MULTI_ROBLOX_NOT_READY")

    def test_default_mode_still_confirms_window_without_handle64(self):
        self.session["mode"] = "default"
        self.assertTrue(self.confirm())
        self.handles.assert_not_called()

    def test_thirteen_launches_require_their_own_clients(self):
        live = {}
        self.snapshot.side_effect = lambda: dict(live)
        confirmed = []
        for index in range(13):
            before = set(live)
            tracker = str(1000 + index)
            process = Mock()
            process.cmdline.return_value = [f"browsertrackerid:{tracker}"]
            key = (3000 + index, 100.0 + index)
            live[key] = process
            result = monitor.confirm_launch(OperationResult.success(data={
                "browser_tracker_id": tracker}), self.session, before, f"Account{index}")
            self.assertTrue(result)
            confirmed.append(result.data["process_identity"])
        self.assertEqual(len(set(confirmed)), 13)


class LaunchGateTests(unittest.TestCase):
    def setUp(self):
        self.manager = RobloxAccountManager.__new__(RobloxAccountManager)
        self.manager._launch_roblox = Mock(return_value=OperationResult.success(data={"browser_tracker_id": "987"}))
        self.session = {"mode": "handle64"}
        self.enterContext(patch.object(actions, "_mr_handle", self.session))
        self.active = self.enterContext(patch.object(actions, "is_multi_roblox_running", return_value=True))
        self.slot = self.enterContext(patch.object(monitor, "wait_for_launch_slot", return_value=OperationResult.success()))
        self.enterContext(patch.object(monitor, "_snapshot", return_value={}))
        self.confirm = self.enterContext(patch.object(monitor, "confirm_launch", return_value=OperationResult.success()))

    def test_unready_handles_prevent_another_url(self):
        failure = OperationResult.failure("MULTI_ROBLOX_NOT_READY", "Failed", "Busy")
        self.slot.return_value = failure
        self.assertIs(self.manager.launch_roblox("alice"), failure)
        self.manager._launch_roblox.assert_not_called()

    def test_failed_launch_is_not_confirmed(self):
        self.manager._launch_roblox.return_value = OperationResult.failure("AUTH_FAILED", "Failed", "Rejected")
        self.assertFalse(self.manager.launch_roblox("alice"))
        self.confirm.assert_not_called()

    def test_unconfirmed_launch_is_not_automatically_duplicated(self):
        self.confirm.return_value = OperationResult.failure("ROBLOX_LAUNCH_UNCONFIRMED", "Failed", "Unknown")
        self.assertFalse(self.manager.launch_roblox("alice"))
        self.manager._launch_roblox.assert_called_once()

    def test_disabled_multi_roblox_preserves_single_client_behavior(self):
        self.active.return_value = False
        self.assertIs(self.manager.launch_roblox("alice"), self.manager._launch_roblox.return_value)
        self.slot.assert_not_called()
        self.confirm.assert_not_called()

    def test_overlapping_launches_wait_for_previous_confirmation(self):
        entered = threading.Event()
        release = threading.Event()
        second_started = threading.Event()
        failures = []

        def confirm(*args):
            entered.set()
            if not release.wait(5):
                failures.append("confirmation never released")
            return OperationResult.success()

        def second():
            second_started.set()
            self.manager.launch_roblox("bob")

        self.confirm.side_effect = confirm
        first = threading.Thread(target=self.manager.launch_roblox, args=("alice",))
        other = threading.Thread(target=second)
        first.start()
        try:
            self.assertTrue(entered.wait(5))
            other.start()
            self.assertTrue(second_started.wait(5))
            self.assertEqual(self.manager._launch_roblox.call_count, 1)
        finally:
            release.set()
            first.join(5)
            if other.ident is not None:
                other.join(5)
        self.assertFalse(first.is_alive())
        self.assertFalse(other.is_alive())
        self.assertFalse(failures)
        self.assertEqual(self.manager._launch_roblox.call_count, 2)


class BatchSurvivalTests(unittest.TestCase):
    def test_exited_client_or_reused_pid_reduces_final_batch_count(self):
        result = OperationResult.success(data={"process_identity": (123, 100.0)})
        process = Mock()
        for running, created in ((False, 100.0), (True, 200.0)):
            with self.subTest(running=running, created=created):
                process.is_running.return_value = running
                process.create_time.return_value = created
                with patch.object(monitor.psutil, "Process", return_value=process):
                    batch = actions._batch_launch_result("Joined", 2, 2, [], [("alice", result)])
                self.assertFalse(batch)
                self.assertEqual(batch.message, "Joined 1/2 accounts.")
                self.assertIn("alice: ROBLOX_CLIENT_EXITED", batch.detail)

    def test_survivors_are_kept_in_final_batch_count(self):
        result = OperationResult.success(data={"process_identity": (123, 100.0)})
        process = Mock()
        process.is_running.return_value = True
        process.create_time.return_value = 100.0
        with patch.object(monitor.psutil, "Process", return_value=process):
            self.assertTrue(actions._batch_launch_result("Joined", 1, 1, [], [("alice", result)]))

    def test_every_batch_entry_point_rechecks_survivors(self):
        invocations = (
            lambda manager, done: actions.join_place_all(manager, ["alice", "bob"], "1818", on_done=done),
            lambda manager, done: actions.launch_home(manager, ["alice", "bob"], on_done=done),
            lambda manager, done: actions.join_job_id(manager, ["alice", "bob"], "1818", "job", on_done=done),
            lambda manager, done: actions.join_user(manager, ["alice", "bob"], "target", on_done=done),
            lambda manager, done: actions.join_small_server(manager, ["alice", "bob"], "1818", on_done=done),
        )
        for index, invoke in enumerate(invocations):
            with self.subTest(entry_point=index):
                manager = Mock()
                manager.accounts = {"alice": {"cookie": "TEST"}}
                manager.launch_roblox.side_effect = [
                    OperationResult.success(data={"process_identity": (123, 100.0)}),
                    OperationResult.success(data={"process_identity": (124, 100.0)}),
                ]
                finished = threading.Event()
                results = []

                def done(ok, result):
                    results.append(result)
                    finished.set()

                response = Mock()
                response.json.return_value = {"data": [{"id": "job", "playing": 1, "maxPlayers": 10}]}
                process = Mock()
                process.is_running.return_value = False
                survivor = Mock()
                survivor.is_running.return_value = True
                survivor.create_time.return_value = 100.0
                with patch.object(actions, "load_ui_settings", return_value={"launch_delay_seconds": 0}), \
                        patch.object(actions.RobloxAPI, "get_user_id_from_username", return_value=42), \
                        patch.object(actions.RobloxAPI, "get_player_presence", return_value={"in_game": True, "place_id": 1818, "game_id": "job"}), \
                        patch.object(actions.requests, "get", return_value=response), \
                        patch.object(monitor.psutil, "Process", side_effect=lambda pid: process if pid == 123 else survivor):
                    invoke(manager, done)
                    self.assertTrue(finished.wait(5))
                self.assertEqual(manager.launch_roblox.call_count, 2)
                self.assertEqual(len(results), 1)
                self.assertFalse(results[0])
                self.assertIn("1/2", results[0].message)
                self.assertIn("alice: ROBLOX_CLIENT_EXITED", results[0].detail)
                self.assertNotIn("bob:", results[0].detail)


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
