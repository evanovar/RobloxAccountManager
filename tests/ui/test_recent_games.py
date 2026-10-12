import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QListWidget

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


if __name__ == "__main__":
    unittest.main()
