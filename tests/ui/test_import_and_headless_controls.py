import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from utils import ui


class HeadlessIntervalControlTests(unittest.TestCase):
    def call(self, window, value):
        with patch.object(ui.actions, "save_ui_setting") as save:
            ui.AccountManagerUIQt._on_sett_headless_interval(window, value)
        return save

    def test_the_value_is_saved_and_applied_to_a_running_manager(self):
        manager = MagicMock()
        save = self.call(SimpleNamespace(_headless_manager=manager), 30)
        save.assert_called_once_with("headless_scan_interval_seconds", 30)
        manager.set_scan_interval.assert_called_once_with(30)

    def test_the_value_is_saved_when_the_manager_is_not_running(self):
        save = self.call(SimpleNamespace(_headless_manager=None), 5)
        save.assert_called_once_with("headless_scan_interval_seconds", 5)

    def test_a_new_manager_starts_with_the_saved_interval(self):
        window = SimpleNamespace(_headless_manager=None, _bridge=SimpleNamespace(headless_update=MagicMock()))
        with patch.object(ui.actions, "load_ui_settings", return_value={"headless_scan_interval_seconds": 42}), \
                patch.object(ui.headless_manager_mod, "HeadlessManager") as manager_class:
            ui.AccountManagerUIQt._start_headless_manager(window)
        self.assertEqual(manager_class.call_args.kwargs["scan_interval"], 42.0)
        manager_class.return_value.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
