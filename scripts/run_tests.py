from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITES = ("unit", "ui", "integration")


def iter_tests(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from iter_tests(test)
        else:
            yield test


def normalize_selector(value: str) -> str:
    value = value.strip().replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    if value.endswith(".py"):
        value = value[:-3]
    return value.replace("/", ".")


def matches(test_id: str, selector: str) -> bool:
    parts = test_id.split(".")
    return any(
        (suffix := ".".join(parts[start:])) == selector
        or suffix.startswith(selector + ".")
        for start in range(len(parts))
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run all tests, a suite, a module, a class, or an individual test.",
        epilog="Example: uv run python scripts/run_tests.py --test "
        "test_machine_id.StableMachineIdTests.test_result_is_cached",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true", help="run all tests (default)")
    selection.add_argument(
        "--test", nargs="+", metavar="SELECTOR",
        help="test IDs, module names, class names, method names, or relative test file paths",
    )
    parser.add_argument(
        "--suite", choices=SUITES, action="append",
        help="limit discovery to this suite; repeat to include more than one suite",
    )
    parser.add_argument("--list", action="store_true", help="list selected test IDs without running them")
    parser.add_argument("-v", "--verbose", action="store_true", help="show each test result")
    parser.add_argument("--failfast", action="store_true", help="stop after the first failure or error")
    args = parser.parse_args(argv)
    if args.all and args.suite:
        parser.error("--all cannot be combined with --suite")

    for folder in (PROJECT_ROOT, PROJECT_ROOT / "src"):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    from utils import app_paths

    with ExitStack() as stack:
        data_dir = stack.enter_context(tempfile.TemporaryDirectory(prefix="ram-tests-"))
        stack.enter_context(patch.object(app_paths, "get_data_dir", return_value=data_dir))
        stack.enter_context(patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}))
        loader = unittest.TestLoader()
        tests = []
        for name in dict.fromkeys(args.suite or SUITES):
            suite = loader.discover(
                str(PROJECT_ROOT / "tests" / name),
                pattern="test_*.py",
                top_level_dir=str(PROJECT_ROOT),
            )
            tests.extend(iter_tests(suite))
        if loader.errors:
            for error in loader.errors:
                print(error, file=sys.stderr)
            return 1
        if args.test:
            selected_ids = set()
            for value in args.test:
                selector = normalize_selector(value)
                found = [test.id() for test in tests if selector and matches(test.id(), selector)]
                if not found:
                    parser.error(f"no tests match {value!r}; use --list to see available IDs")
                selected_ids.update(found)
            tests = [test for test in tests if test.id() in selected_ids]
        if not tests:
            parser.error("no tests were discovered")
        if args.list:
            for test in tests:
                print(test.id())
            print(f"\n{len(tests)} test(s)")
            return 0
        result = unittest.TextTestRunner(
            verbosity=2 if args.verbose else 1,
            failfast=args.failfast,
        ).run(unittest.TestSuite(tests))
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
