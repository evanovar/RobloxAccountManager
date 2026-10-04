import os
import tempfile
import unittest
from unittest.mock import patch

from features import diagnostics


class LogRetentionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.enterContext(patch.object(diagnostics, "_get_diagnostics_root", return_value=self.folder.name))
        os.makedirs(os.path.join(self.folder.name, "logs"))
        os.makedirs(os.path.join(self.folder.name, "crash_logs"))

    def make(self, folder, name, age):
        path = os.path.join(self.folder.name, folder, name)
        with open(path, "w") as handle:
            handle.write("x")
        os.utime(path, (1_000_000 - age, 1_000_000 - age))
        return path

    def names(self, folder):
        return sorted(os.listdir(os.path.join(self.folder.name, folder)))

    def test_only_the_newest_files_of_each_kind_are_kept(self):
        for number in range(6):
            self.make("logs", f"session-{number}.log", age=number)
            self.make("logs", f"hang-{number}.log", age=number)
            self.make("crash_logs", f"crash-{number}.log", age=number)
        removed = diagnostics.prune_old_logs(2)
        self.assertEqual(removed, 12)
        self.assertEqual(self.names("logs"), ["hang-0.log", "hang-1.log", "session-0.log", "session-1.log"])
        self.assertEqual(self.names("crash_logs"), ["crash-0.log", "crash-1.log"])

    def test_the_active_session_log_is_never_removed(self):
        active = self.make("logs", "session-old.log", age=500)
        for number in range(3):
            self.make("logs", f"session-{number}.log", age=number)
        diagnostics.prune_old_logs(1, protect=active)
        self.assertIn("session-old.log", self.names("logs"))

    def test_unrelated_files_are_left_alone(self):
        self.make("logs", "notes.txt", age=999)
        self.make("logs", "session-a.log", age=1)
        self.make("logs", "session-b.log", age=2)
        diagnostics.prune_old_logs(1)
        self.assertEqual(self.names("logs"), ["notes.txt", "session-a.log"])

    def test_zero_disables_cleanup(self):
        for number in range(5):
            self.make("logs", f"session-{number}.log", age=number)
        self.assertEqual(diagnostics.prune_old_logs(0), 0)
        self.assertEqual(len(self.names("logs")), 5)

    def test_missing_folders_are_fine(self):
        os.rmdir(os.path.join(self.folder.name, "crash_logs"))
        self.assertEqual(diagnostics.prune_old_logs(3), 0)

    def test_setting_is_read_with_a_safe_default(self):
        with patch.object(diagnostics.settings_store, "get", return_value="7"):
            self.assertEqual(diagnostics.get_log_retention(), 7)
        with patch.object(diagnostics.settings_store, "get", return_value="many"):
            self.assertEqual(diagnostics.get_log_retention(), diagnostics.DEFAULT_LOG_RETENTION)
        with patch.object(diagnostics.settings_store, "get", return_value=-4):
            self.assertEqual(diagnostics.get_log_retention(), 0)


if __name__ == "__main__":
    unittest.main()
