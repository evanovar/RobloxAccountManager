from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from features import account_status as status, headless_manager as hm, presence
from features.window_log_probe import ProbeResult


def client(state="game", pid=123, visible=True):
    return {"pid": pid, "created": 100.0, "client_state": state,
            "window_visible": visible, "reason": state}


class ClientLogTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(folder) / "client.log"
        self.log = status.ClientLog(100)

    def append(self, text):
        with self.path.open("ab") as handle:
            handle.write(text.encode())
        self.log.read(str(self.path))

    def test_connected_without_ids_then_disconnect_does_not_assert_home(self):
        self.append("[FLog::Network] Replicator created: server\n")
        self.assertEqual(self.log.state, "game")
        self.assertEqual((self.log.place_id, self.log.job_id), ("", ""))
        self.append("[FLog::Network] Time to disconnect replication data: 1\n")
        self.assertEqual(self.log.state, "game")

    def test_home_requires_signed_in_desktop_evidence(self):
        self.append("[FLog::SingleSurfaceApp] setStage: (stage:LuaApp)\n")
        self.assertIsNone(self.log.state)
        self.append("[FLog::SingleSurfaceApp] userDidLogin\n")
        self.assertEqual(self.log.state, "home")
        self.append("[FLog::SingleSurfaceApp] launchUGCGameInternal\n")
        self.assertEqual(self.log.state, "home")
        self.append("[FLog::Network] Replicator created: server\n")
        self.append("[FLog::SingleSurfaceApp] userDidLogin\n")
        self.assertEqual(self.log.state, "game")
        self.append("[FLog::SingleSurfaceApp] returnToLuaApp: (stage:UGCGame).\n")
        self.assertEqual(self.log.state, "game")
        self.append("[FLog::SingleSurfaceApp] setStage: (stage:LuaApp)\n")
        self.assertEqual(self.log.state, "home")

    def test_teleport_clears_old_server_until_new_connection(self):
        self.append("[FLog::Output] ! Joining game 'first-job' place 42 at server\n"
                    "[FLog::Network] Replicator created: server\n")
        self.assertEqual((self.log.state, self.log.place_id, self.log.job_id), ("game", "42", "first-job"))
        self.append("[FLog::UgcExperienceController] doTeleport: joinScriptUrl\n")
        self.assertEqual((self.log.state, self.log.place_id), ("game", ""))
        self.append("[FLog::Network] Replicator created: server\n")
        self.assertEqual(self.log.state, "game")

    def test_partial_line_is_not_used_before_it_is_complete(self):
        self.append("[FLog::Network] Replicator crea")
        self.assertIsNone(self.log.state)
        self.assertFalse(self.log.available)
        self.append("ted: server\n")
        self.assertEqual(self.log.state, "game")

    def test_truncation_and_replacement_reset_old_game_state(self):
        self.append("[FLog::Network] Replicator created: server\n")
        self.path.write_text("reset\n")
        self.log.read(str(self.path))
        self.assertIsNone(self.log.state)
        self.append("[FLog::Network] Replicator created: server\n")
        replacement = self.path.with_suffix(".new")
        replacement.write_text("new log without connection evidence\n")
        replacement.replace(self.path)
        self.log.read(str(self.path))
        self.assertIsNone(self.log.state)

    def test_unreadable_log_invalidates_connection_evidence(self):
        self.append("[FLog::Network] Replicator created: server\n")
        self.path.unlink()
        self.log.read(str(self.path))
        self.assertFalse(self.log.available)

    def test_ignored_transitions_preserve_last_color(self):
        for marker in ("[FLog::SingleSurfaceApp] userDidLogout", "challengedByGcs",
                       "[FLog::SingleSurfaceApp] shutDown: (stage:LuaApp).",
                       "[FLog::SingleSurfaceApp] destroyLuaApp:",
                       "[FLog::SingleSurfaceApp] launchUGCGameInternal",
                       "[FLog::SingleSurfaceApp] returnToLuaApp:"):
            self.append("[FLog::SingleSurfaceApp] initializeLuaAppWithLoggedInUser:\n"
                        "[FLog::SingleSurfaceApp] setStage: (stage:LuaApp)\n")
            self.append(marker + "\n")
            self.assertEqual(self.log.state, "home")

    def test_joining_does_not_clear_red_until_a_confirmed_state_arrives(self):
        self.append("[FLog::Output] Session Transition FSM: Error Occurred.\n")
        self.append("[FLog::Network] Time to disconnect replication data: 1\n")
        self.append("[FLog::Output] ! Joining game 'next' place 42 at server\n")
        self.assertEqual(self.log.state, "error")
        self.append("[FLog::Network] Replicator created: server\n")
        self.assertEqual(self.log.state, "game")

    def test_fatal_crash_marker_is_red_and_home_can_clear_session_error(self):
        self.append("2026-10-16T00:00:00Z,1,1,6 [LOGCHANNELS + 1] RBXCRASH: HardAssert (Out of job nodes)\n")
        self.assertEqual(self.log.state, "error")
        self.append("[FLog::SingleSurfaceApp] initializeLuaAppWithLoggedInUser:\n"
                    "[FLog::SingleSurfaceApp] setStage: (stage:LuaApp)\n")
        self.assertEqual(self.log.state, "home")

    def test_routine_log_errors_do_not_change_color(self):
        self.append("[FLog::Network] Replicator created: server\n")
        for line in ("[FLog::Error] Asset (Image) load failed: Invalid image or texture.",
                     "[FLog::CreatorError] Script error: attempt to index nil",
                     "[DFLog::HttpTraceError] HttpResponse status:500",
                     "[FLog::CreatorOutput] Session Transition FSM: Error Occurred.",
                     "[FLog::CreatorOutput] RBXCRASH: HardAssert (script output)"):
            self.append(line + "\n")
            self.assertEqual(self.log.state, "game")


class StatusAggregationTests(unittest.TestCase):
    def test_hard_error_is_red_even_if_main_window_is_absent(self):
        self.assertEqual(status.summarize_processes([client("error", visible=False)], set())["state"], "error")

    def test_background_overrides_game_and_retains_connection_in_tooltip(self):
        row = client(visible=False)
        row["reason"] = "Connected to a game server."
        result = status.summarize_processes([row], set())
        self.assertEqual(result["state"], "background")
        self.assertIn("Connected to a game server", result["tooltip"])

    def test_headless_home_and_game_keep_their_color_and_outline(self):
        for state in ("home", "game", "error"):
            result = status.summarize_processes([client(state, visible=False)], {(123, 100.0)})
            self.assertEqual(result["state"], state)
            self.assertTrue(result["hollow"])

    def test_multiple_clients_follow_priority_and_mixed_mode_is_solid(self):
        rows = [client("home", pid=1), client("error", pid=2), client("game", pid=3, visible=False)]
        result = status.summarize_processes(rows, {(1, 100.0)})
        self.assertEqual(result["state"], "home")
        self.assertFalse(result["hollow"])
        self.assertIn("Mixed headless", result["tooltip"])
        rows.append(client("game", pid=4))
        self.assertEqual(status.summarize_processes(rows, set())["state"], "game")

    def test_pid_reuse_does_not_inherit_headless(self):
        result = status.summarize_processes([client()], {(123, 99.0)})
        self.assertFalse(result["hollow"])

    def test_window_inspection_failure_does_not_override_last_connection(self):
        self.assertEqual(status.summarize_processes([client(visible=None)], set())["state"], "game")


class StatusTrackerTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict("os.environ", {"LOCALAPPDATA": str(root)}))
        folder = root / "Roblox" / "logs"
        folder.mkdir(parents=True)
        self.path = folder / "0.742_19700101T000140Z_Player_ABC_last.log"
        self.path.write_text("web launch, websiteBTId is 987\n"
                             "[FLog::SingleSurfaceApp] initializeLuaAppWithLoggedInUser:\n"
                             "[FLog::SingleSurfaceApp] setStage: (stage:LuaApp)\n")
        self.process = MagicMock(pid=123)
        self.process.cmdline.return_value = ["roblox-player:1+browsertrackerid:987"]
        self.processes = {123: (100.0, self.process)}
        self.tracker = status.ClientStatusTracker(threading.Event())
        self.addCleanup(self.stop_tracker)
        self.probe = self.enterContext(patch.object(status, "probe_open_log_paths", return_value=ProbeResult("timeout")))
        self.enterContext(patch.object(status, "client_window_visible", return_value=True))

    def stop_tracker(self):
        self.tracker._stop.set()
        if self.tracker._probe_thread:
            self.tracker._probe_thread.join(timeout=4)

    def scan(self, records=None):
        return self.tracker.scan(self.processes, {"42": "Account"},
                                 {"987": ("42", 99.0)} if records is None else records, {})

    def test_home_without_user_id_uses_recorded_launch_and_exact_log_tracker(self):
        row = self.scan()[(123, 100.0)]
        self.assertEqual((row["username"], row["client_state"]), ("Account", "home"))
        self.probe.assert_not_called()

    def test_external_process_uses_exact_open_log_and_authenticated_identity(self):
        self.process.cmdline.return_value = []
        with self.path.open("a") as handle:
            handle.write("[FLog::GameJoinLoadTime] Report game_join_loadtime: userid:42, \n"
                         "[FLog::Network] Replicator created: server\n")
        self.probe.return_value = ProbeResult("ok", frozenset({str(self.path).lower()}))
        self.scan({})
        self.tracker._probe_thread.join(timeout=1)
        self.assertEqual(self.scan({})[(123, 100.0)]["client_state"], "game")

    def test_slow_identity_probe_does_not_block_known_client_updates(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def slow_probe(*args):
            entered.set()
            release.wait(2)
            return ProbeResult("timeout")
        self.process.cmdline.return_value = []
        self.probe.side_effect = slow_probe
        self.assertEqual(self.scan({}), {})
        self.assertTrue(entered.wait(1))
        self.assertTrue(self.tracker._probe_thread.is_alive())
        release.set()

    def test_duplicate_tracker_does_not_guess_identity_from_launch_record(self):
        self.processes[124] = (100.0, self.process)
        self.assertEqual(self.scan(), {})

    def test_missing_log_does_not_request_a_color_change_and_exit_removes_it(self):
        self.scan()
        self.path.unlink()
        self.assertIsNone(self.scan()[(123, 100.0)]["client_state"])
        self.processes.clear()
        self.assertEqual(self.scan(), {})
        self.assertFalse(self.tracker._bindings)

    def test_reused_pid_does_not_keep_old_log_binding(self):
        self.scan()
        self.processes[123] = (500.0, self.process)
        self.assertEqual(self.scan({}), {})
        self.assertNotIn((123, 100.0), self.tracker._bindings)

    def test_read_failure_does_not_request_a_color_change(self):
        self.scan()
        with patch("builtins.open", side_effect=PermissionError):
            self.assertIsNone(self.scan()[(123, 100.0)]["client_state"])

    def test_incomplete_log_does_not_request_a_color_change(self):
        self.scan()
        with self.path.open("a") as handle:
            handle.write("[FLog::Network] Replicator crea")
        self.assertIsNone(self.scan()[(123, 100.0)]["client_state"])
        with self.path.open("a") as handle:
            handle.write("ted: server\n")
        self.assertEqual(self.scan()[(123, 100.0)]["client_state"], "game")

    def test_error_dialog_can_turn_red_even_without_readable_logs(self):
        self.scan()
        self.path.unlink()
        with patch.object(status, "has_error_dialog", return_value=True):
            row = self.scan()[(123, 100.0)]
        self.assertEqual(row["client_state"], "error")
        self.assertIn("dialog", row["reason"])

    def test_failed_window_observation_keeps_previous_background_state(self):
        with patch.object(status, "client_window_visible", return_value=False), \
                patch.object(status.time, "monotonic", return_value=10):
            self.scan()
        with patch.object(status, "client_window_visible", return_value=False), \
                patch.object(status.time, "monotonic", return_value=12):
            self.scan()
        with patch.object(status, "client_window_visible", return_value=None):
            self.assertFalse(self.scan()[(123, 100.0)]["window_visible"])

    def test_background_requires_a_stable_missing_window(self):
        with patch.object(status, "client_window_visible", return_value=False), \
                patch.object(status.time, "monotonic", return_value=10):
            self.assertIsNone(self.scan()[(123, 100.0)]["window_visible"])
        with patch.object(status, "client_window_visible", return_value=False), \
                patch.object(status.time, "monotonic", return_value=12):
            self.assertFalse(self.scan()[(123, 100.0)]["window_visible"])


class WindowStatusTests(unittest.TestCase):
    def test_native_error_dialog_requires_visible_dialog_class_and_error_title(self):
        with patch.object(status.win32gui, "IsWindowVisible", return_value=True) as visible, \
                patch.object(status.win32gui, "GetClassName", return_value="#32770") as window_class, \
                patch.object(status.win32gui, "GetWindowText", return_value="Roblox Crash") as title:
            self.assertTrue(status.has_error_dialog([123]))
            visible.return_value = False
            self.assertFalse(status.has_error_dialog([123]))
            visible.return_value = True
            title.return_value = "Roblox"
            self.assertFalse(status.has_error_dialog([123]))
            title.return_value = "Error"
            window_class.return_value = "RobloxGameWindow"
            self.assertFalse(status.has_error_dialog([123]))

    def test_minimized_or_note_renamed_window_counts_as_a_client_window(self):
        with patch.object(status.win32gui, "GetWindow", return_value=0), \
                patch.object(status.win32gui, "GetWindowRect", return_value=(0, 0, 800, 600)), \
                patch.object(status.win32gui, "GetWindowText", return_value="My account note"), \
                patch.object(status.win32gui, "IsWindowVisible", return_value=False), \
                patch.object(status.win32gui, "IsIconic", return_value=True):
            self.assertTrue(status.client_window_visible([123]))
            self.assertEqual(hm._get_roblox_hwnds_for_pid(1, [123]), [123])


class HeadlessIntentTests(unittest.TestCase):
    def test_antiafk_pause_preserves_outline_but_explicit_show_clears_it(self):
        manager = hm.HeadlessManager(lambda rows: None)
        with patch.object(hm.presence_mod, "get_roblox_processes", return_value={123: (100.0, None)}), \
                patch.object(hm, "hide_roblox_window"), patch.object(hm, "show_roblox_window"):
            manager.set_hidden(123, True)
            self.assertTrue(manager.pause_hidden(123))
            self.assertEqual(manager.get_hidden_pids(), set())
            self.assertEqual(manager.get_headless_identities(), {(123, 100.0)})
            manager.resume_hidden(123)
            self.assertEqual(manager.get_hidden_pids(), {123})
            manager.set_hidden(123, False)
            manager.resume_hidden(123)
            self.assertFalse(manager.get_headless_identities())
            self.assertFalse(manager.get_hidden_pids())

    def test_reused_pid_is_not_hidden_when_antiafk_finishes(self):
        manager = hm.HeadlessManager(lambda rows: None)
        with patch.object(hm.presence_mod, "get_roblox_processes", return_value={123: (100.0, None)}), \
                patch.object(hm, "hide_roblox_window"):
            manager.set_hidden(123, True)
            manager.pause_hidden(123)
        with patch.object(hm.presence_mod, "get_roblox_processes", return_value={123: (200.0, None)}), \
                patch.object(hm, "hide_roblox_window") as hide:
            manager.resume_hidden(123)
            hide.assert_not_called()


class ActivityScannerTests(unittest.TestCase):
    def test_failed_first_scan_does_not_add_a_dot_state(self):
        updates = []
        scanner = presence.PresenceScanner(SimpleNamespace(accounts={"Account": {"user_id": "42"}}), updates.append)
        with patch.object(presence, "get_roblox_processes", side_effect=PermissionError):
            scanner._do_scan()
        self.assertEqual(updates[-1], {})

    def test_unidentified_client_does_not_add_dot_states_to_unmatched_accounts(self):
        updates = []
        scanner = presence.PresenceScanner(SimpleNamespace(accounts={"Account": {"user_id": "42"}}), updates.append)
        with patch.object(presence, "get_roblox_processes", return_value={123: (100.0, MagicMock())}), \
                patch.object(presence, "get_windows_by_pid", return_value={}), \
                patch.object(scanner._status_tracker, "scan", return_value={}), \
                patch.object(hm, "get_active_manager", return_value=None):
            scanner._do_scan()
        self.assertEqual(updates[-1], {})

    def test_scan_failure_keeps_previous_color(self):
        updates = []
        scanner = presence.PresenceScanner(SimpleNamespace(accounts={}), updates.append)
        scanner.latest_snapshot = {"Account": {"clients": [client()], "state": "game"}}
        with patch.object(presence, "get_roblox_processes", side_effect=PermissionError):
            scanner._do_scan()
        self.assertEqual(updates[-1]["Account"]["state"], "game")
        self.assertTrue(updates[-1]["Account"]["clients"][0]["window_visible"])

    def test_metrics_aggregate_while_status_prefers_connected_client(self):
        updates = []
        scanner = presence.PresenceScanner(SimpleNamespace(accounts={"Account": {"user_id": "42"}}), updates.append)
        proc = MagicMock(pid=123)
        proc.memory_info.return_value.rss = 100 * 1024 * 1024
        proc.cpu_percent.return_value = 10
        second = MagicMock(pid=124)
        second.memory_info.return_value.rss = 200 * 1024 * 1024
        second.cpu_percent.return_value = 20
        with patch.object(presence, "get_roblox_processes", return_value={123: (100.0, proc), 124: (100.0, second)}), \
                patch.object(presence, "get_windows_by_pid", return_value={}), \
                patch.object(scanner._status_tracker, "scan", return_value={
                    (123, 100.0): {**client("home"), "username": "Account"},
                    (124, 100.0): {**client("game", pid=124), "username": "Account"},
                }), patch.object(hm, "get_active_manager", return_value=None):
            scanner._do_scan()
        self.assertEqual(updates[-1]["Account"]["ram_mb"], 300)
        self.assertEqual(updates[-1]["Account"]["state"], "game")
