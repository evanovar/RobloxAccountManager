import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from features import headless_manager as hm
from utils import ui


def tracker_process(tracker=""):
    args = ["RobloxPlayerBeta.exe"]
    if tracker:
        args.append(f"roblox-player:1+browsertrackerid:{tracker}")
    return Mock(cmdline=Mock(return_value=args))


class AutoHideSettingTests(unittest.TestCase):
    def test_reads_only_a_list_of_names(self):
        self.assertEqual(hm.get_auto_hide({hm.AUTO_HIDE_SETTING: ["a", "", 3, "b"]}), {"a", "b"})
        for value in (None, "a", {"a": 1}):
            with self.subTest(value=value):
                self.assertEqual(hm.get_auto_hide({hm.AUTO_HIDE_SETTING: value}), set())
        self.assertEqual(hm.get_auto_hide(None), set())

    def test_toggle_adds_and_removes_names(self):
        self.assertEqual(hm.set_auto_hide_value({"b"}, ["A", "c"], True), ["A", "b", "c"])
        self.assertEqual(hm.set_auto_hide_value({"a", "b"}, ["a", "x"], False), ["b"])


class AutoHideScanTests(unittest.TestCase):
    def setUp(self):
        self.hide = self.enterContext(patch.object(hm, "hide_roblox_window", return_value=True))
        self.enterContext(patch.object(hm.presence_mod, "_get_user_id_from_pid", return_value=None))
        self.lookup = self.enterContext(patch.object(hm.RobloxAPI, "get_username_from_user_id", return_value=None))
        self.manager = SimpleNamespace(
            accounts={"Alice": {"user_id": 1, "note": "farm 1"}, "bob": {"user_id": 2}},
            get_launch_records=Mock(return_value={"777": ("1", 1.0), "888": ("2", 2.0)}),
        )
        self.updates = []

    def make(self, auto_hide):
        return hm.HeadlessManager(self.updates.append, manager=self.manager, auto_hide=auto_hide)

    def scan(self, headless, processes):
        with patch.object(hm, "_get_roblox_processes", return_value=processes):
            headless._do_scan()
        return self.updates[-1] if self.updates else []

    def test_auto_hide_accounts_are_hidden_when_their_client_appears(self):
        headless = self.make({"alice"})
        rows = self.scan(headless, {
            101: (1.0, tracker_process("777")),
            202: (2.0, tracker_process("888")),
        })
        self.assertEqual(headless.get_hidden_pids(), {101})
        self.hide.assert_called_once_with(101, "Alice", {"farm 1"})
        by_pid = {row["pid"]: row for row in rows}
        self.assertTrue(by_pid[101]["hidden"] and by_pid[101]["auto_hide"])
        self.assertFalse(by_pid[202]["hidden"] or by_pid[202]["auto_hide"])
        self.lookup.assert_not_called()

    def test_relaunched_client_with_a_new_pid_is_hidden_again(self):
        headless = self.make({"alice"})
        self.scan(headless, {101: (1.0, tracker_process("777"))})
        self.scan(headless, {})
        self.scan(headless, {303: (3.0, tracker_process("777"))})
        self.assertEqual(headless.get_hidden_pids(), {303})

    def test_a_window_shown_by_hand_stays_shown_until_it_closes(self):
        headless = self.make({"alice"})
        self.scan(headless, {101: (1.0, tracker_process("777"))})
        with patch.object(hm, "show_roblox_window"):
            headless.set_hidden(101, False)
        self.scan(headless, {101: (1.0, tracker_process("777"))})
        self.assertEqual(headless.get_hidden_pids(), set())
        self.scan(headless, {})
        self.scan(headless, {101: (5.0, tracker_process("777"))})
        self.assertEqual(headless.get_hidden_pids(), {101})

    def test_turning_auto_hide_on_later_applies_on_the_next_scan(self):
        headless = self.make(set())
        self.scan(headless, {202: (2.0, tracker_process("888"))})
        self.assertEqual(headless.get_hidden_pids(), set())
        headless.set_auto_hide(["BOB"])
        self.scan(headless, {202: (2.0, tracker_process("888"))})
        self.assertEqual(headless.get_hidden_pids(), {202})

    def test_unknown_clients_fall_back_to_logs_and_are_skipped_without_a_user(self):
        headless = self.make({"alice"})
        rows = self.scan(headless, {404: (4.0, tracker_process())})
        self.assertEqual(rows, [])
        self.assertEqual(headless.get_hidden_pids(), set())

    def test_note_titles_are_used_when_restoring(self):
        headless = self.make({"alice"})
        self.scan(headless, {101: (1.0, tracker_process("777"))})
        with patch.object(hm, "show_roblox_window") as show:
            headless.restore_all()
        show.assert_called_once_with(101, "Alice", {"farm 1"})


class AutoHideUiTests(unittest.TestCase):
    def test_toggle_saves_and_updates_a_running_manager(self):
        running = MagicMock()
        window = SimpleNamespace(
            _headless_manager=running, _headless_latest_rows=[], _refresh_headless_list=MagicMock(),
        )
        window._headless_list = object()
        with patch.object(ui.actions, "load_ui_settings", return_value={hm.AUTO_HIDE_SETTING: ["bob"]}), \
                patch.object(ui.actions, "save_ui_setting") as save:
            ui.AccountManagerUIQt._set_headless_auto_hide(window, ["alice"], True)
        save.assert_called_once_with(hm.AUTO_HIDE_SETTING, ["alice", "bob"])
        running.set_auto_hide.assert_called_once_with(["alice", "bob"])
        running.rescan_now.assert_called_once()

    def test_manager_off_saves_and_explains(self):
        window = SimpleNamespace(_headless_manager=None)
        with patch.object(ui.actions, "load_ui_settings", return_value={}), \
                patch.object(ui.actions, "save_ui_setting") as save, \
                patch.object(ui.QMessageBox, "information") as info:
            ui.AccountManagerUIQt._set_headless_auto_hide(window, ["alice"], True)
        save.assert_called_once_with(hm.AUTO_HIDE_SETTING, ["alice"])
        info.assert_called_once()

    def test_started_manager_gets_the_saved_accounts_and_account_manager(self):
        window = SimpleNamespace(
            _headless_manager=None, manager=object(),
            _bridge=SimpleNamespace(headless_update=MagicMock()),
        )
        with patch.object(ui.actions, "load_ui_settings", return_value={hm.AUTO_HIDE_SETTING: ["alice"]}), \
                patch.object(ui.headless_manager_mod, "HeadlessManager") as manager_class:
            ui.AccountManagerUIQt._start_headless_manager(window)
        kwargs = manager_class.call_args.kwargs
        self.assertEqual(kwargs["auto_hide"], {"alice"})
        self.assertIs(kwargs["manager"], window.manager)


if __name__ == "__main__":
    unittest.main()
