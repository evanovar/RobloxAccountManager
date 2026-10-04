import threading
import unittest
from unittest.mock import patch

from classes.operation_result import OperationResult
from features import account_actions as actions
from features import headless_manager as hm


class ImportBatchSizeTests(unittest.TestCase):
    def test_default_is_the_old_fixed_value(self):
        self.assertEqual(actions.get_import_batch_size({}), 5)
        self.assertEqual(actions.get_import_batch_size(None), 5)
        self.assertEqual(actions.IMPORT_BATCH_SIZE, 5)

    def test_values_are_clamped_to_one_through_five(self):
        for value, expected in ((1, 1), (3, 3), (5, 5), (0, 1), (-4, 1), (6, 5), (400, 5), ("2", 2), (2.9, 2)):
            with self.subTest(value=value):
                self.assertEqual(actions.get_import_batch_size({"import_browser_count": value}), expected)

    def test_invalid_values_fall_back_to_the_default(self):
        for value in (None, "many", [], {}):
            with self.subTest(value=value):
                self.assertEqual(actions.get_import_batch_size({"import_browser_count": value}), 5)


class FakeManager:
    def __init__(self):
        self.accounts = {}
        self.batches = []

    def add_account(self, amount, javascript_list, browser):
        self.batches.append(amount)
        for index in range(amount):
            self.accounts[f"user{len(self.accounts)}"] = {}
        return OperationResult.success()


class ImportUsesTheSettingTests(unittest.TestCase):
    def run_import(self, count, setting):
        manager = FakeManager()
        finished = threading.Event()
        outcome = []
        settings = {} if setting is None else {"import_browser_count": setting}
        pairs = [(f"name{i}", "pw") for i in range(count)]
        with patch.object(actions, "load_ui_settings", return_value=settings), \
                patch.object(actions, "get_browser_result", return_value=OperationResult.success(data={"browser": "chrome"})):
            actions.import_user_pass(manager, pairs, lambda ok, message: (outcome.append((ok, message)), finished.set()))
            self.assertTrue(finished.wait(10))
        return manager.batches, outcome[0]

    def test_default_opens_five_at_a_time(self):
        batches, (ok, _message) = self.run_import(7, None)
        self.assertEqual(batches, [5, 2])
        self.assertTrue(ok)

    def test_lower_setting_opens_fewer_browsers(self):
        self.assertEqual(self.run_import(5, 2)[0], [2, 2, 1])
        self.assertEqual(self.run_import(3, 1)[0], [1, 1, 1])

    def test_out_of_range_setting_is_clamped(self):
        self.assertEqual(self.run_import(7, 99)[0], [5, 2])
        self.assertEqual(self.run_import(2, 0)[0], [1, 1])


class ScanIntervalTests(unittest.TestCase):
    def test_default_is_the_old_fixed_value(self):
        self.assertEqual(hm.get_scan_interval({}), 10.0)
        self.assertEqual(hm.get_scan_interval(None), 10.0)

    def test_values_are_clamped_to_three_through_sixty_seconds(self):
        for value, expected in ((3, 3.0), (30, 30.0), (60, 60.0), (1, 3.0), (0, 3.0), (-5, 3.0), (600, 60.0), ("15", 15.0), (7.5, 7.5)):
            with self.subTest(value=value):
                self.assertEqual(hm.get_scan_interval({"headless_scan_interval_seconds": value}), expected)

    def test_invalid_values_fall_back_to_the_default(self):
        for value in (None, "slow", [], float("nan")):
            with self.subTest(value=value):
                self.assertEqual(hm.get_scan_interval({"headless_scan_interval_seconds": value}), 10.0)

    def test_manager_uses_the_interval_it_is_given(self):
        manager = hm.HeadlessManager(lambda rows: None, scan_interval=25)
        self.assertEqual(manager._scan_interval, 25)
        self.assertEqual(hm.HeadlessManager(lambda rows: None)._scan_interval, 10.0)

    def test_manager_never_scans_faster_than_the_minimum(self):
        self.assertEqual(hm.HeadlessManager(lambda rows: None, scan_interval=0.1)._scan_interval, 3.0)

    def test_interval_can_be_changed_while_running(self):
        manager = hm.HeadlessManager(lambda rows: None)
        manager.set_scan_interval(45)
        self.assertEqual(manager._scan_interval, 45.0)
        manager.set_scan_interval(1)
        self.assertEqual(manager._scan_interval, 3.0)
        manager.set_scan_interval(1000)
        self.assertEqual(manager._scan_interval, 60.0)


if __name__ == "__main__":
    unittest.main()
