import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import requests

from features import roblox_plus


def response(status=200, details=None):
    return Mock(status_code=status, json=Mock(return_value={"profileDetails": details or []}))


def make_manager(accounts):
    return SimpleNamespace(
        accounts=accounts,
        _accounts_lock=threading.RLock(),
        save_accounts=MagicMock(),
    )


class FetchTests(unittest.TestCase):
    def test_batches_ids_and_reads_the_subscription_flag(self):
        session = Mock()
        session.post.side_effect = [
            response(details=[{"userId": n, "hasRobloxSubscription": n == 1} for n in range(1, 101)]),
            response(details=[{"userId": 101, "hasRobloxSubscription": True}]),
        ]
        ids = [str(n) for n in range(1, 102)] + ["1", "0", "", "abc"]
        result = roblox_plus.fetch_plus_status(ids, session=session)
        self.assertEqual(session.post.call_count, 2)
        first_body = session.post.call_args_list[0].kwargs["json"]
        self.assertEqual(len(first_body["userIds"]), 100)
        self.assertEqual(first_body["fields"], ["hasRobloxSubscription"])
        self.assertTrue(result["1"])
        self.assertFalse(result["2"])
        self.assertTrue(result["101"])
        self.assertEqual(len(result), 101)

    def test_failures_return_nothing_for_that_batch(self):
        for failure in (response(status=429), requests.ConnectionError("offline")):
            with self.subTest(failure=failure):
                session = Mock()
                session.post.side_effect = [failure]
                self.assertEqual(roblox_plus.fetch_plus_status(["1"], session=session), {})

    def test_missing_or_odd_values_are_skipped(self):
        session = Mock()
        session.post.return_value = response(details=[
            {"userId": 1}, {"userId": 2, "hasRobloxSubscription": "yes"}, {"hasRobloxSubscription": True},
        ])
        self.assertEqual(roblox_plus.fetch_plus_status(["1", "2"], session=session), {})


class SyncTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("_RUNNING", False), ("_SYNCED_THIS_SESSION", False), ("_LAST_FAILED", None)):
            self.enterContext(patch.object(roblox_plus, name, value))
        thread = self.enterContext(patch.object(roblox_plus.threading, "Thread"))
        thread.side_effect = lambda target, **_kw: Mock(start=target)

    def test_first_run_checks_everyone_and_saves_changes(self):
        manager = make_manager({
            "a": {"user_id": 1, roblox_plus.FIELD: False},
            "b": {"user_id": "2"},
            "c": {"user_id": 0},
        })
        done = Mock()
        with patch.object(roblox_plus, "fetch_plus_status", return_value={"1": True, "2": False}) as fetch:
            self.assertTrue(roblox_plus.sync_plus_status(manager, on_done=done))
        self.assertEqual(sorted(fetch.call_args.args[0]), ["1", "2"])
        self.assertTrue(manager.accounts["a"][roblox_plus.FIELD])
        self.assertFalse(manager.accounts["b"][roblox_plus.FIELD])
        self.assertNotIn(roblox_plus.FIELD, manager.accounts["c"])
        manager.save_accounts.assert_called_once()
        self.assertEqual(sorted(done.call_args.args[0]), ["a", "b"])

    def test_later_runs_only_check_accounts_never_checked(self):
        manager = make_manager({"a": {"user_id": 1, roblox_plus.FIELD: True}, "b": {"user_id": 2}})
        with patch.object(roblox_plus, "fetch_plus_status", return_value={"1": True, "2": True}):
            roblox_plus.sync_plus_status(manager)
        manager.accounts["c"] = {"user_id": 3}
        with patch.object(roblox_plus, "fetch_plus_status", return_value={"3": False}) as fetch:
            roblox_plus.sync_plus_status(manager)
        self.assertEqual(fetch.call_args.args[0], ["3"])

    def test_unchanged_results_do_not_save(self):
        manager = make_manager({"a": {"user_id": 1, roblox_plus.FIELD: True}})
        with patch.object(roblox_plus, "fetch_plus_status", return_value={"1": True}):
            roblox_plus.sync_plus_status(manager)
        manager.save_accounts.assert_not_called()

    def test_failed_run_waits_before_retrying(self):
        manager = make_manager({"a": {"user_id": 1}})
        with patch.object(roblox_plus, "fetch_plus_status", return_value={}) as fetch:
            self.assertTrue(roblox_plus.sync_plus_status(manager))
            self.assertFalse(roblox_plus.sync_plus_status(manager))
        fetch.assert_called_once()
        self.assertNotIn(roblox_plus.FIELD, manager.accounts["a"])

    def test_replaced_account_does_not_get_a_stale_result(self):
        manager = make_manager({"a": {"user_id": 1}})

        def fetch(_ids):
            manager.accounts["a"] = {"user_id": 9}
            return {"1": True}

        with patch.object(roblox_plus, "fetch_plus_status", side_effect=fetch):
            roblox_plus.sync_plus_status(manager)
        self.assertNotIn(roblox_plus.FIELD, manager.accounts["a"])

    def test_has_plus_only_for_true(self):
        self.assertTrue(roblox_plus.has_plus({roblox_plus.FIELD: True}))
        for data in ({}, {roblox_plus.FIELD: False}, None, "x"):
            self.assertFalse(roblox_plus.has_plus(data))


if __name__ == "__main__":
    unittest.main()
