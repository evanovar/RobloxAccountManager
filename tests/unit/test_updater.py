import os
import tempfile
import unittest
from unittest.mock import patch
from features import updater

class UpdaterTests(unittest.TestCase):
    def test_source_mode_has_no_automatic_target(self):
        with patch.object(updater.sys, "frozen", False, create=True):
            self.assertIsNone(updater.get_update_target())

    def test_custom_executable_name_is_preserved(self):
        with tempfile.TemporaryDirectory() as work_dir:
            target = os.path.join(work_dir, "My Roblox Manager.exe")
            with open(target, "wb") as handle:
                handle.write(b"test")
            with patch.object(updater.sys, "frozen", True, create=True):
                with patch.object(updater.sys, "executable", target):
                    self.assertEqual(updater.get_update_target(), target)

    def test_installer_has_bounded_waits_and_parameterized_destination(self):
        script = updater._build_installer_script()
        self.assertIn("$DestinationPath", script)
        self.assertIn(f"AddSeconds({updater.PROCESS_WAIT_SECONDS})", script)
        self.assertIn(f"AddSeconds({updater.REPLACE_WAIT_SECONDS})", script)
        self.assertNotIn("RobloxAccountManager.exe", script)

