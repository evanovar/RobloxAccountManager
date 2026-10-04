import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from utils import app_paths


def default_dir():
    return os.path.join(app_paths.get_project_root(), "AccountManagerData")


class ResolveDataDirTests(unittest.TestCase):
    def setUp(self):
        self.env = self.enterContext(patch.dict(os.environ))
        os.environ.pop(app_paths.DATA_DIR_ENV, None)

    def test_default_folder_is_next_to_the_application(self):
        self.assertEqual(app_paths.resolve_data_dir(), default_dir())

    def test_blank_override_uses_the_default(self):
        for value in ("", "   "):
            with self.subTest(value=value):
                os.environ[app_paths.DATA_DIR_ENV] = value
                self.assertEqual(app_paths.resolve_data_dir(), default_dir())

    def test_absolute_override_is_used(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ[app_paths.DATA_DIR_ENV] = folder
            self.assertEqual(app_paths.resolve_data_dir(), os.path.abspath(folder))

    def test_relative_home_and_variable_paths_are_expanded(self):
        os.environ["RAM_TEST_BASE"] = os.path.join(tempfile.gettempdir(), "ram-base")
        os.environ[app_paths.DATA_DIR_ENV] = os.path.join("%RAM_TEST_BASE%", "profile")
        expanded = app_paths.resolve_data_dir()
        self.assertTrue(os.path.isabs(expanded))
        self.assertTrue(expanded.endswith(os.path.join("ram-base", "profile")))

        os.environ[app_paths.DATA_DIR_ENV] = os.path.join("~", "RamProfile")
        self.assertEqual(app_paths.resolve_data_dir(), os.path.join(os.path.expanduser("~"), "RamProfile"))

        os.environ[app_paths.DATA_DIR_ENV] = "relative-profile"
        self.assertEqual(app_paths.resolve_data_dir(), os.path.abspath("relative-profile"))


class DataDirArgumentTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ))
        os.environ.pop(app_paths.DATA_DIR_ENV, None)

    def test_separate_value_is_applied_and_removed(self):
        remaining = app_paths.apply_data_dir_argument(["ram.exe", "--data-dir", r"D:\Profiles\Alt", "--other"])
        self.assertEqual(os.environ[app_paths.DATA_DIR_ENV], r"D:\Profiles\Alt")
        self.assertEqual(remaining, ["ram.exe", "--other"])

    def test_equals_form_is_applied_and_removed(self):
        remaining = app_paths.apply_data_dir_argument(["ram.exe", r"--data-dir=D:\Profiles\Alt"])
        self.assertEqual(os.environ[app_paths.DATA_DIR_ENV], r"D:\Profiles\Alt")
        self.assertEqual(remaining, ["ram.exe"])

    def test_without_the_option_nothing_changes(self):
        argv = ["ram.exe", "--style", "fusion"]
        self.assertEqual(app_paths.apply_data_dir_argument(argv), argv)
        self.assertNotIn(app_paths.DATA_DIR_ENV, os.environ)

    def test_a_missing_value_is_ignored_with_a_warning(self):
        with patch.object(sys, "stderr") as stderr:
            remaining = app_paths.apply_data_dir_argument(["ram.exe", "--data-dir"])
        self.assertEqual(remaining, ["ram.exe"])
        self.assertNotIn(app_paths.DATA_DIR_ENV, os.environ)
        self.assertTrue(stderr.write.called)

    def test_the_last_value_wins(self):
        app_paths.apply_data_dir_argument(["ram.exe", "--data-dir", "one", "--data-dir=two"])
        self.assertEqual(os.environ[app_paths.DATA_DIR_ENV], "two")

    def test_the_value_feeds_resolve_data_dir(self):
        with tempfile.TemporaryDirectory() as folder:
            app_paths.apply_data_dir_argument(["ram.exe", "--data-dir", folder])
            self.assertEqual(app_paths.resolve_data_dir(), os.path.abspath(folder))


if __name__ == "__main__":
    unittest.main()
