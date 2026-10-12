import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QListWidget, QWidget

from features import settings_store
from utils import ui


class RecentGamesSettingTests(unittest.TestCase):
    def test_lowering_the_setting_trims_the_file_and_refreshes_the_visible_list(self):
        QApplication.instance() or QApplication([])
        recent_list = QListWidget()
        self.addCleanup(recent_list.deleteLater)
        window = SimpleNamespace(_recent_list=recent_list)
        window._refresh_recent_games = lambda: ui.AccountManagerUIQt._refresh_recent_games(window)
        history = [{"place_id": str(n), "name": f"Game {n}"} for n in range(19, -1, -1)]
        with tempfile.TemporaryDirectory() as folder:
            history_path = os.path.join(folder, "recent_games.json")
            with open(history_path, "w", encoding="utf-8") as handle:
                json.dump(history, handle)
            with patch.object(ui.actions, "_RECENT_GAMES_FILE", history_path), \
                    patch.object(settings_store, "_SETTINGS_PATH", os.path.join(folder, "ui_settings.json")):
                settings_store.invalidate()
                try:
                    ui.AccountManagerUIQt._on_sett_max_recent_games(window, 5)
                    self.assertEqual(settings_store.get("max_recent_games"), 5)
                    self.assertEqual(recent_list.count(), 5)
                    self.assertEqual([recent_list.item(i).text() for i in range(5)],
                                     [f"Game {n}" for n in range(19, 14, -1)])
                    with open(history_path, encoding="utf-8") as handle:
                        self.assertEqual(json.load(handle), history[:5])
                finally:
                    settings_store.invalidate()


class RecentGamesContextMenuTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.window = QWidget()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)
        self.window._recent_list = QListWidget(self.window)
        self.window._refresh_recent_games = lambda: ui.AccountManagerUIQt._refresh_recent_games(self.window)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, "recent_games.json")
        self.history = [
            {"place_id": "1", "name": "Public", "private_server": ""},
            {"place_id": "1", "name": "Private", "private_server": "server-a"},
            {"place_id": "2", "name": "Other", "private_server": ""},
        ]
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self.history, handle)
        self.enterContext(patch.object(ui.actions, "_RECENT_GAMES_FILE", self.path))
        self.enterContext(patch.object(ui.actions, "get_recent_games_limit", return_value=10))
        self.menu = MagicMock()
        self.enterContext(patch.object(ui, "QMenu", return_value=self.menu))
        self.window._refresh_recent_games()
        self.window._recent_list.setCurrentRow(0)

    def click(self, index=1):
        item = self.window._recent_list.item(index)
        position = self.window._recent_list.visualItemRect(item).center()
        ui.AccountManagerUIQt._on_recent_game_context_menu(self.window, position)

    def read_history(self):
        with open(self.path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_delete_removes_the_right_clicked_entry_and_updates_the_list(self):
        self.menu.exec.return_value = self.menu.addAction.return_value
        self.click()
        self.menu.addAction.assert_called_once_with("Delete")
        self.assertEqual(self.read_history(), [self.history[0], self.history[2]])
        self.assertEqual(self.window._recent_list.count(), 2)
        self.assertEqual(self.window._recent_list.item(0).text(), "Public")

    def test_dismissing_the_menu_does_not_delete_anything(self):
        self.menu.exec.return_value = None
        self.click()
        self.assertEqual(self.read_history(), self.history)
        self.assertEqual(self.window._recent_list.count(), 3)

    def test_right_clicking_empty_space_does_not_open_a_menu(self):
        ui.AccountManagerUIQt._on_recent_game_context_menu(self.window, QPoint(-1, -1))
        self.menu.exec.assert_not_called()
        self.assertEqual(self.read_history(), self.history)

    def test_failed_deletion_shows_an_error_and_keeps_the_visible_entry(self):
        self.menu.exec.return_value = self.menu.addAction.return_value
        with patch.object(ui.actions, "remove_recent_game", side_effect=OSError("disk full")), \
                patch.object(ui, "_show_error") as error:
            self.click()
        error.assert_called_once()
        self.assertEqual(self.read_history(), self.history)
        self.assertEqual(self.window._recent_list.count(), 3)

    def test_history_can_refresh_while_the_delete_menu_is_open(self):
        def choose_delete(_position):
            self.window._refresh_recent_games()
            return self.menu.addAction.return_value

        self.menu.exec.side_effect = choose_delete
        self.click()
        self.assertEqual(self.read_history(), [self.history[0], self.history[2]])


if __name__ == "__main__":
    unittest.main()
