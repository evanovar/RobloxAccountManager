import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from utils import ui


def make_window(accounts, visible):
    QApplication.instance() or QApplication([])
    widget = QListWidget()
    for name in visible:
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, name)
        widget.addItem(item)
    manager = SimpleNamespace(
        accounts={name: {"username": name} for name in accounts},
        _accounts_lock=threading.RLock(),
        save_accounts=MagicMock(),
    )
    window = SimpleNamespace(
        _account_list=widget,
        manager=manager,
        _refresh_account_list=MagicMock(),
    )
    window._row_username = lambda row: ui.AccountManagerUIQt._row_username(window, row)
    return window, widget


def reorder(window, from_row, before_row):
    ui.AccountManagerUIQt._on_account_reorder(window, from_row, before_row)
    return list(window.manager.accounts)


class AccountReorderTests(unittest.TestCase):
    def test_full_list_reorders_by_row(self):
        window, _ = make_window(["a", "b", "c", "d"], ["a", "b", "c", "d"])
        self.assertEqual(reorder(window, 3, 1), ["a", "d", "b", "c"])
        window.manager.save_accounts.assert_called_once()
        window._refresh_account_list.assert_called_once()

    def test_group_view_moves_the_dragged_account_not_the_account_at_the_same_row(self):
        window, _ = make_window(["a", "b", "c", "d", "e"], ["b", "d", "e"])
        self.assertEqual(reorder(window, 2, 0), ["a", "e", "b", "c", "d"])

    def test_dropping_at_the_end_of_a_group_view_stays_after_the_last_visible_account(self):
        window, widget = make_window(["a", "b", "c", "d", "e"], ["b", "d"])
        self.assertEqual(reorder(window, 0, widget.count()), ["a", "c", "d", "b", "e"])

    def test_dropping_on_the_same_place_saves_nothing(self):
        window, _ = make_window(["a", "b", "c"], ["a", "b", "c"])
        self.assertEqual(reorder(window, 1, 2), ["a", "b", "c"])
        window.manager.save_accounts.assert_not_called()
        window._refresh_account_list.assert_not_called()

    def test_placeholder_rows_are_ignored(self):
        window, widget = make_window(["a"], ["a"])
        widget.addItem("No accounts, use 'Add Account' to add one.")
        self.assertEqual(reorder(window, 1, 0), ["a"])
        window.manager.save_accounts.assert_not_called()

    def test_a_failed_save_still_refreshes_the_list(self):
        window, _ = make_window(["a", "b", "c"], ["a", "b", "c"])
        window.manager.save_accounts.side_effect = OSError("disk full")
        self.assertEqual(reorder(window, 2, 0), ["c", "a", "b"])
        window._refresh_account_list.assert_called_once()


if __name__ == "__main__":
    unittest.main()
