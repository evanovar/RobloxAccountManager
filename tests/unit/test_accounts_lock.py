import tempfile
import threading
import time
import unittest
from unittest import mock

from classes import account_manager as am


class AccountsLockTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patch = mock.patch.object(am, "get_data_dir", return_value=self.folder.name)
        patch.start()
        self.addCleanup(patch.stop)
        self.manager = am.RobloxAccountManager()
        self.manager.accounts = {"alice": {"username": "alice", "cookie": "c", "note": ""}}

    def run_while_locked(self, action):
        started = threading.Event()
        worker = threading.Thread(target=lambda: (started.set(), action()))
        with self.manager._accounts_lock:
            worker.start()
            started.wait(2)
            time.sleep(0.2)
            state = {name: dict(data) for name, data in self.manager.accounts.items()}
        worker.join(5)
        self.assertFalse(worker.is_alive())
        return state

    def test_note_is_not_changed_while_another_thread_holds_the_lock(self):
        state = self.run_while_locked(lambda: self.manager.set_account_note("alice", "hello"))
        self.assertEqual(state["alice"]["note"], "")
        self.assertEqual(self.manager.get_account_note("alice"), "hello")

    def test_delete_waits_for_the_lock(self):
        state = self.run_while_locked(lambda: self.manager.delete_account("alice"))
        self.assertIn("alice", state)
        self.assertNotIn("alice", self.manager.accounts)

    def test_missing_accounts_still_report_failure(self):
        self.assertFalse(self.manager.set_account_note("nobody", "x"))
        self.assertFalse(self.manager.delete_account("nobody"))


if __name__ == "__main__":
    unittest.main()
