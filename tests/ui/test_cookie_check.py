import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from PySide6.QtWidgets import QApplication

from features import cookie_validator
from utils import ui


def make_window(accounts):
    QApplication.instance() or QApplication([])
    manager = SimpleNamespace(
        accounts={name: {"username": name, "cookie": "synthetic-" + name} for name in accounts},
        _accounts_lock=threading.RLock(),
        save_accounts=MagicMock(),
    )
    window = SimpleNamespace(
        manager=manager,
        _cv_mod=cookie_validator,
        _cv_validator=None,
        _cookie_checks={},
        _bridge=SimpleNamespace(cookie_validated=Mock(), cookie_check_done=Mock()),
    )
    for name in ("_cookie_check_status", "_cookie_status_tooltip"):
        method = getattr(ui.AccountManagerUIQt, name)
        setattr(window, name, lambda *args, m=method: m(window, *args))
    return window


class SelectedValidatorTests(unittest.TestCase):
    def test_only_selected_accounts_are_checked(self):
        window = make_window(["a", "b", "c"])
        checked = []

        def check(cookie, _session):
            checked.append(cookie)
            return cookie_validator.VALID, "", False

        worker = cookie_validator.CookieValidator(
            window.manager, on_result=Mock(), usernames=["c", "missing", "a"],
        )
        worker._stop_evt.wait = Mock(return_value=False)
        with patch.object(cookie_validator, "_check", side_effect=check):
            worker._run()
        self.assertEqual(checked, ["synthetic-c", "synthetic-a"])

    def test_is_alive_reflects_the_worker_thread(self):
        worker = cookie_validator.CookieValidator(make_window([]).manager, on_result=Mock())
        self.assertFalse(worker.is_alive())


class CheckCookiesActionTests(unittest.TestCase):
    def test_starts_a_validator_for_known_selected_accounts(self):
        window = make_window(["a", "b"])
        with patch.object(ui.actions, "load_ui_settings", return_value={}), \
                patch.object(ui.cookie_validator_mod, "CookieValidator") as validator:
            ui.AccountManagerUIQt._on_check_cookies(window, ["b", "gone"])
        self.assertEqual(validator.call_args.kwargs["usernames"], ["b"])
        validator.return_value.start.assert_called_once()

    def test_does_not_start_while_another_check_runs(self):
        window = make_window(["a"])
        window._cv_validator = Mock(is_alive=Mock(return_value=True))
        with patch.object(ui.QMessageBox, "information") as info, \
                patch.object(ui.cookie_validator_mod, "CookieValidator") as validator:
            ui.AccountManagerUIQt._on_check_cookies(window, ["a"])
        info.assert_called_once()
        validator.assert_not_called()

    def test_summary_ignores_results_from_before_the_run(self):
        window = make_window(["a", "b", "c"])
        window._cookie_checks = {
            "a": (cookie_validator.VALID, 200.0),
            "b": (cookie_validator.INVALID, 200.0),
            "c": (cookie_validator.VALID, 50.0),
        }
        with patch.object(ui.QMessageBox, "information") as info:
            ui.AccountManagerUIQt._on_cookie_check_done(window, (["a", "b", "c"], 100.0))
        text = info.call_args.args[2]
        self.assertIn("Valid: 1", text)
        self.assertIn("Invalid: 1", text)
        self.assertIn("Could not verify: 1", text)

    def test_single_account_summary_names_the_result(self):
        window = make_window(["a"])
        window._cookie_checks = {"a": (cookie_validator.VALID, 200.0)}
        with patch.object(ui.QMessageBox, "information") as info:
            ui.AccountManagerUIQt._on_cookie_check_done(window, (["a"], 100.0))
        self.assertEqual(info.call_args.args[2], "The cookie for a is valid.")


class CookieTooltipTests(unittest.TestCase):
    def test_unchecked_valid_account_has_no_tooltip(self):
        self.assertEqual(make_window(["a"])._cookie_status_tooltip("a", False), "")

    def test_tooltip_shows_flag_and_last_check(self):
        window = make_window(["a"])
        window._cookie_checks = {"a": (cookie_validator.UNKNOWN, 0.0)}
        tooltip = window._cookie_status_tooltip("a", True)
        self.assertIn("repeated unauthorized responses", tooltip)
        self.assertIn("could not verify", tooltip.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
