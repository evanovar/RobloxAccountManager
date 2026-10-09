from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from features import presence, window_log_probe, window_renamer as renamer


class WindowRenamerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.renamer = renamer.RobloxWindowRenamer(SimpleNamespace(accounts={}))
        self.key = (123, 100.0)
        self.process = MagicMock()
        self.process.cmdline.return_value = ["RobloxPlayerBeta.exe", "browsertrackerid=987"]
        self.entry = presence.RobloxLogEntry(
            datetime.fromtimestamp(100, tz=timezone.utc).replace(tzinfo=None),
            renamer.os.path.abspath("player_last.log"), "42", "987")
        self.saved = {"42": "Account"}
        self.probe = self.enterContext(patch.object(renamer, "probe_open_log_paths"))

    def collect(self, processes=None, entries=None):
        return self.renamer._collect_direct_evidence(
            processes or {self.key: self.process},
            [self.entry] if entries is None else entries, self.saved)

    def test_unique_tracker_is_resolved_without_file_scan(self):
        self.collect()
        self.probe.assert_not_called()
        self.process.open_files.assert_not_called()
        self.assertEqual(self.renamer._identities[self.key].evidence, renamer._EVIDENCE_TRACKER)

    def test_recorded_launch_resolves_thirteen_clients_when_logs_replace_trackers(self):
        processes = {}
        records = {}
        entries = []
        saved = {}
        for index in range(13):
            tracker = str(1000 + index)
            user_id = str(2000 + index)
            key = (3000 + index, 100.0 + index)
            process = MagicMock()
            process.cmdline.return_value = [
                "RobloxPlayerBeta.exe",
                f"roblox-player:1+browsertrackerid:{tracker}+robloxLocale:en_us",
            ]
            processes[key] = process
            records[tracker] = (user_id, key[1] - 1)
            saved[user_id] = f"Account{index}"
            entries.append(presence.RobloxLogEntry(
                self.entry.timestamp, renamer.os.path.abspath(f"{index}_last.log"),
                user_id, str(9000 + index)))
        self.renamer._manager.get_launch_records = lambda: dict(records)
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        self.renamer._collect_direct_evidence(processes, entries, saved)
        self.assertEqual(len(self.renamer._identities), 13)
        for key, process in processes.items():
            tracker = self.renamer._extract_process_tracker(process)
            identity = self.renamer._identities[key]
            self.assertEqual(identity.user_id, records[tracker][0])
            self.assertEqual(identity.evidence, renamer._EVIDENCE_LAUNCH)
        self.probe.assert_not_called()
        self.assertFalse(self.renamer._claimed_logs)

    def test_recorded_launch_waits_for_successful_launch_evidence(self):
        records = {}
        self.renamer._manager.get_launch_records = lambda: dict(records)
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        self.collect(entries=[])
        self.assertFalse(self.renamer._identities)
        records["987"] = ("42", 99.0)
        self.collect(entries=[])
        self.assertEqual(self.renamer._identities[self.key].evidence, renamer._EVIDENCE_LAUNCH)
        self.probe.assert_called_once()

    def test_duplicate_process_trackers_reject_recorded_launch(self):
        self.renamer._manager.get_launch_records = lambda: {"987": ("42", 99.0)}
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        self.collect({self.key: self.process, (124, 101.0): self.process}, [])
        self.assertFalse(self.renamer._identities)

    def test_recorded_launch_outside_startup_window_cannot_identify_reused_pid(self):
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        for launch_time in (103.0, -201.0):
            with self.subTest(launch_time=launch_time):
                self.renamer._manager.get_launch_records = lambda: {"987": ("42", launch_time)}
                self.collect(entries=[])
                self.assertFalse(self.renamer._identities)

    def test_removed_account_launch_is_not_used(self):
        self.renamer._manager.get_launch_records = lambda: {"987": ("999", 99.0)}
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        self.collect(entries=[])
        self.assertFalse(self.renamer._identities)

    def test_recorded_launch_identity_uses_current_account_note(self):
        self.renamer._manager.get_launch_records = lambda: {"987": ("42", 99.0)}
        self.collect(entries=[])
        self.renamer.set_title_mode("note")
        identity = self.renamer._identities[self.key]
        self.assertEqual(self.renamer._get_title_target(identity, {
            "42": {"username": "Account", "note": "New note"}}), "New note")

    def test_resolved_recorded_launch_counts_toward_duplicate_detection(self):
        self.renamer._manager.get_launch_records = lambda: {"987": ("42", 99.0)}
        self.collect(entries=[])
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        self.collect({self.key: self.process, (124, 101.0): self.process}, [])
        self.assertNotIn((124, 101.0), self.renamer._identities)

    def test_recorded_launch_log_cannot_be_given_to_another_pid_by_timestamp(self):
        other_key = (124, 101.0)
        other_process = MagicMock()
        other_process.cmdline.return_value = []
        self.renamer._manager.get_launch_records = lambda: {"987": ("42", 99.0)}
        self.probe.return_value = window_log_probe.ProbeResult("ok")
        processes = {self.key: self.process, other_key: other_process}
        trackers, paths = self.collect(processes)
        self.renamer._apply_safe_timestamp_fallback(
            processes, [self.entry], self.saved, trackers, paths)
        self.assertIn(self.key, self.renamer._identities)
        self.assertNotIn(other_key, self.renamer._identities)

    def test_recorded_launch_does_not_block_unrelated_timestamp_match(self):
        other_key = (124, 101.0)
        other_process = MagicMock()
        other_process.cmdline.return_value = []
        self.renamer._manager.get_launch_records = lambda: {"987": ("42", 99.0)}
        self.saved["43"] = "OtherAccount"
        other_entry = presence.RobloxLogEntry(
            self.entry.timestamp, renamer.os.path.abspath("other_last.log"), "43", "")
        self.probe.return_value = window_log_probe.ProbeResult("ok")
        processes = {self.key: self.process, other_key: other_process}
        entries = [self.entry, other_entry]
        trackers, paths = self.collect(processes, entries)
        self.renamer._apply_safe_timestamp_fallback(
            processes, entries, self.saved, trackers, paths)
        self.assertEqual(self.renamer._identities[other_key].user_id, "43")

    def test_exact_open_file_resolves_account_without_parent_scan(self):
        self.process.cmdline.return_value = []
        self.probe.return_value = window_log_probe.ProbeResult("ok", frozenset({
            self.renamer._normalized_path(self.entry.path)}))
        self.collect()
        self.assertEqual(self.renamer._identities[self.key].username, "Account")
        self.assertEqual(self.renamer._identities[self.key].evidence, renamer._EVIDENCE_OPEN_FILE)
        self.process.open_files.assert_not_called()
        self.collect()
        self.probe.assert_called_once()

    def test_timeout_is_unknown_and_cannot_trigger_timestamp_guess(self):
        self.process.cmdline.return_value = []
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        trackers, paths = self.collect()
        self.renamer._apply_safe_timestamp_fallback({self.key: self.process},
                                                   [self.entry], self.saved, trackers, paths)
        self.assertNotIn(self.key, self.renamer._identities)
        self.collect()
        self.probe.assert_called_once()

    def test_verified_empty_scan_allows_single_unambiguous_timestamp(self):
        self.process.cmdline.return_value = []
        self.probe.return_value = window_log_probe.ProbeResult("ok")
        trackers, paths = self.collect()
        self.renamer._apply_safe_timestamp_fallback({self.key: self.process},
                                                   [self.entry], self.saved, trackers, paths)
        self.assertEqual(self.renamer._identities[self.key].evidence, renamer._EVIDENCE_TIMESTAMP)

    def test_unknown_second_process_still_prevents_timestamp_guess(self):
        second_key = (124, 101.0)
        processes = {self.key: self.process, second_key: self.process}
        self.renamer._apply_safe_timestamp_fallback(processes, [self.entry], self.saved,
                                                   {}, {self.key: set()})
        self.assertFalse(self.renamer._identities)

    def test_duplicate_tracker_never_assigns_same_log_to_two_processes(self):
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        self.collect({self.key: self.process, (124, 101.0): self.process})
        self.assertFalse(self.renamer._identities)

    def test_resolved_tracker_counts_toward_duplicate_detection(self):
        self.collect()
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        self.collect({self.key: self.process, (124, 101.0): self.process})
        self.assertNotIn((124, 101.0), self.renamer._identities)

    def test_helpers_per_pass_are_bounded(self):
        self.process.cmdline.return_value = []
        self.probe.return_value = window_log_probe.ProbeResult("timeout")
        processes = {(pid, 100.0): self.process for pid in range(1, 14)}
        self.collect(processes, [])
        self.assertEqual(self.probe.call_count, renamer._MAX_PROBES_PER_SCAN)
        self.collect(processes, [])
        self.assertEqual(self.probe.call_count, 2 * renamer._MAX_PROBES_PER_SCAN)

    def test_exit_and_pid_reuse_clear_cached_evidence(self):
        self.renamer._open_log_cache[self.key] = {self.entry.path}
        self.renamer._probe_retry_at[self.key] = 999999
        self.renamer._probe_failures[self.key] = 2
        self.renamer._remove_exited_state({(123, 200.0)})
        self.assertFalse(self.renamer._open_log_cache)
        self.assertFalse(self.renamer._probe_retry_at)
        self.assertFalse(self.renamer._probe_failures)

    def test_empty_scan_retries_do_not_starve_unprobed_clients(self):
        self.process.cmdline.return_value = []
        self.probe.return_value = window_log_probe.ProbeResult("ok")
        processes = {(pid, 100.0): self.process for pid in range(1, 6)}
        with patch.object(renamer.time, "monotonic", return_value=100.0):
            self.collect(processes, [])
        with patch.object(renamer.time, "monotonic", return_value=200.0):
            self.collect(processes, [])
        self.assertEqual([call.args[0][0] for call in self.probe.call_args_list], [1, 2, 3, 4])

    def test_stop_does_not_clear_state_of_a_still_running_scan(self):
        thread = MagicMock()
        thread.is_alive.return_value = True
        self.renamer._thread = thread
        self.renamer._probe_retry_at[self.key] = 1
        self.renamer.stop(join_timeout=0)
        self.assertTrue(self.renamer._stop_evt.is_set())
        self.assertIs(self.renamer._thread, thread)
        self.assertIn(self.key, self.renamer._probe_retry_at)
