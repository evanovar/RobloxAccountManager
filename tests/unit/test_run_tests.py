from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_tests


RUNNER = run_tests.PROJECT_ROOT / "scripts" / "run_tests.py"
CASE = "test_machine_id.StableMachineIdTests.test_result_is_cached"


class TestRunnerTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(RUNNER), *args],
            cwd=cwd, capture_output=True, text=True, timeout=30,
        )

    def test_individual_test_can_run_outside_the_project_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli("--suite", "unit", "--test", CASE, "-v", cwd=directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ran 1 test", result.stderr)
        self.assertIn("test_result_is_cached", result.stderr)

    def test_list_filters_to_an_individual_test_without_running_it(self):
        result = self.run_cli("--suite", "unit", "--test", CASE, "--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tests.unit." + CASE, result.stdout)
        self.assertIn("1 test(s)", result.stdout)
        self.assertNotIn("Ran 1 test", result.stderr)

    def test_overlapping_file_and_method_selections_do_not_duplicate_tests(self):
        result = self.run_cli(
            "--suite", "unit", "--list", "--test",
            "tests/unit/test_machine_id.py", CASE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        ids = [line for line in result.stdout.splitlines() if line.startswith("tests.")]
        self.assertEqual(len(ids), 8)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(line.startswith("tests.unit.test_machine_id.") for line in ids))

    def test_unknown_selector_fails_even_when_another_selector_is_valid(self):
        result = self.run_cli("--suite", "unit", "--test", CASE, "missing_test")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("no tests match 'missing_test'", result.stderr)
        self.assertNotIn("Ran 1 test", result.stderr)

    def test_conflicting_selection_options_are_rejected(self):
        for args in (("--all", "--test", CASE), ("--all", "--suite", "unit")):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_failed_test_returns_exit_code_one(self):
        def fail():
            self.assertEqual(1, 2, "intentional runner fixture")

        suite = unittest.TestSuite([unittest.FunctionTestCase(fail)])
        output = io.StringIO()
        with patch.object(unittest.TestLoader, "discover", return_value=suite), redirect_stderr(output):
            self.assertEqual(run_tests.main(["--suite", "unit"]), 1)
        self.assertIn("FAILED (failures=1)", output.getvalue())

    def test_import_error_is_reported_instead_of_claiming_success(self):
        def discover(loader, *args, **kwargs):
            loader.errors.append("fixture: missing dependency")
            return unittest.TestSuite()

        output = io.StringIO()
        with patch.object(unittest.TestLoader, "discover", discover), redirect_stderr(output):
            self.assertEqual(run_tests.main(["--suite", "unit", "--list"]), 1)
        self.assertIn("fixture: missing dependency", output.getvalue())

    def test_suite_selection_limits_discovery_and_deduplicates_suites(self):
        output = io.StringIO()
        with patch.object(
            unittest.TestLoader, "discover",
            side_effect=lambda *a, **kw: unittest.TestSuite([unittest.FunctionTestCase(lambda: None)]),
        ) as discover, redirect_stdout(output):
            self.assertEqual(run_tests.main(["--suite", "unit", "--suite", "unit", "--list"]), 0)
        self.assertEqual(discover.call_count, 1)
        self.assertEqual(Path(discover.call_args.args[0]).name, "unit")
