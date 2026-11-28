import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog

from features import favorites, game_selector
from features.game_selector import Game
from utils import ui


class FavoritesStoreTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(favorites, "_FAVORITES_FILE", os.path.join(folder, "favorites.json")))

    def test_add_rejects_bad_place_ids_and_moves_repeats_to_the_top(self):
        self.assertFalse(favorites.add_favorite("abc"))
        self.assertFalse(favorites.add_favorite("0"))
        self.assertTrue(favorites.add_favorite("1", "One", "", "11"))
        self.assertTrue(favorites.add_favorite("2", "Two", "vip"))
        self.assertTrue(favorites.add_favorite("1"))
        saved = favorites.load_favorites()
        self.assertEqual([(f["place_id"], f["private_server"]) for f in saved], [("1", ""), ("2", "vip")])
        # a repeat keeps the name and universe it already had
        self.assertEqual((saved[0]["name"], saved[0]["universe_id"]), ("One", "11"))

    def test_same_place_with_and_without_private_server_are_separate(self):
        favorites.add_favorite("1", "Public")
        favorites.add_favorite("1", "Private", "vip")
        self.assertEqual(len(favorites.load_favorites()), 2)
        favorites.remove_favorite("1", "vip")
        self.assertEqual([f["name"] for f in favorites.load_favorites()], ["Public"])

    def test_details_from_roblox_fill_in_without_reordering(self):
        favorites.add_favorite("1")
        favorites.add_favorite("2")
        self.assertTrue(favorites.update_favorite_details("1", "", "Game One", "11"))
        self.assertFalse(favorites.update_favorite_details("1", "", "Game One", "11"))
        saved = favorites.load_favorites()
        self.assertEqual([f["place_id"] for f in saved], ["2", "1"])
        self.assertEqual((saved[1]["name"], saved[1]["universe_id"]), ("Game One", "11"))


class ResolveFavoritesTests(unittest.TestCase):
    def test_keeps_order_reuses_saved_universes_and_falls_back_to_saved_names(self):
        calls = []

        def get_json(url, params):
            calls.append(url)
            if "universes/v1/places/2/" in url:
                return {"universeId": 22}
            if "universes/v1/places/3/" in url:
                raise game_selector.requests.ConnectionError("offline")
            if url == game_selector.GAMES_URL:
                return {"data": [{"id": 11, "name": "Game One"}, {"id": 22, "name": "Game Two"}]}
            if url == game_selector.THUMBNAILS_URL:
                return {"data": [{"targetId": 22, "state": "Completed", "imageUrl": "https://t.rbxcdn.com/x"}]}
            raise AssertionError(url)

        entries = [
            {"place_id": "1", "universe_id": "11", "name": "1"},
            {"place_id": "2", "name": "Old name"},
            {"place_id": "3", "name": "Saved Three"},
        ]
        with patch.object(game_selector, "_get_json", side_effect=get_json):
            games = game_selector.resolve_favorites(entries)
        self.assertEqual([g.place_id for g in games], ["1", "2", "3"])
        self.assertEqual([g.title for g in games], ["Game One", "Game Two", "Saved Three"])
        self.assertEqual(games[1].thumbnail_url, "https://t.rbxcdn.com/x")
        self.assertEqual(games[2].universe_id, "place:3")
        self.assertFalse(any("places/1/" in url for url in calls))


class FavoritesTabTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.saved = [
            {"place_id": "20", "name": "Saved Game", "private_server": "", "universe_id": "10"},
            {"place_id": "30", "name": "VIP Game", "private_server": "vip-link", "universe_id": "40"},
        ]
        self.enterContext(patch.object(ui.favorites_mod, "load_favorites", side_effect=lambda: [dict(f) for f in self.saved]))
        self.enterContext(patch.object(ui.game_selector_mod, "start_load", side_effect=lambda *_: threading.Event()))
        self.enterContext(patch.object(ui.game_selector_mod, "start_thumbnails", side_effect=lambda *_: threading.Event()))
        self.start_favorites = self.enterContext(
            patch.object(ui.game_selector_mod, "start_favorites", side_effect=lambda *_: threading.Event()))
        with patch.object(ui.QTimer, "singleShot"):
            self.dialog = ui._GamesSelectorDialog()
        self.addCleanup(self.dialog.deleteLater)
        self.addCleanup(self.dialog.close)
        self.dialog.show()
        self.dialog.tabs.setCurrentIndex(1)
        self.app.processEvents()

    def test_saved_favorites_show_with_private_server_marker(self):
        favorites_list = self.dialog.favorites
        self.assertEqual(favorites_list.count(), 2)
        self.assertEqual(favorites_list.item(0).data(ui._PRIVATE_SERVER_ROLE), "")
        self.assertEqual(favorites_list.item(1).data(ui._PRIVATE_SERVER_ROLE), "vip-link")
        self.assertIn("Private server", favorites_list.item(1).toolTip())

    def test_applying_a_favorite_returns_its_place_and_private_server(self):
        self.dialog.favorites.setCurrentRow(1)
        self.assertTrue(self.dialog.apply.isEnabled())
        self.dialog.apply.click()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual((self.dialog.selected_place_id, self.dialog.selected_private_server), ("30", "vip-link"))

    def test_roblox_details_replace_saved_names_and_are_stored(self):
        self.dialog._load_favorites()
        on_done = self.start_favorites.call_args.args[1]
        with patch.object(ui.favorites_mod, "update_favorite_details") as update:
            on_done([Game("10", "20", "Fresh Name"), Game("40", "30", "VIP Fresh")])
            self.app.processEvents()
        self.assertEqual(self.dialog.favorites.item(0).data(ui.Qt.ItemDataRole.UserRole).title, "Fresh Name")
        update.assert_any_call("30", "vip-link", "VIP Fresh", "40")

    def test_right_click_copies_the_place_id(self):
        item = self.dialog.favorites.item(0)
        pos = self.dialog.favorites.visualItemRect(item).center()
        with patch.object(self.dialog, "_exec_menu",lambda menu, *_: menu.actions()[0]):
            self.dialog._on_game_context_menu(self.dialog.favorites, pos)
        self.assertEqual(QApplication.clipboard().text(), "20")

    def test_right_click_can_remove_a_favorite(self):
        item = self.dialog.favorites.item(1)
        pos = self.dialog.favorites.visualItemRect(item).center()
        with patch.object(self.dialog, "_exec_menu",lambda menu, *_: menu.actions()[-1]), \
                patch.object(ui.favorites_mod, "remove_favorite") as remove:
            self.dialog._on_game_context_menu(self.dialog.favorites, pos)
        remove.assert_called_once_with("30", "vip-link")

    def test_browse_results_can_be_copied_and_favorited(self):
        self.dialog.tabs.setCurrentIndex(0)
        self.dialog._pages = [{"games": [Game("50", "60", "Browse Game")], "next_page_token": ""}]
        self.dialog._render_page()
        self.app.processEvents()
        pos = self.dialog.games.visualItemRect(self.dialog.games.item(0)).center()
        with patch.object(self.dialog, "_exec_menu",lambda menu, *_: menu.actions()[0]):
            self.dialog._on_game_context_menu(self.dialog.games, pos)
        self.assertEqual(QApplication.clipboard().text(), "60")
        with patch.object(self.dialog, "_exec_menu",lambda menu, *_: menu.actions()[1]), \
                patch.object(ui.favorites_mod, "add_favorite") as add:
            self.dialog._on_game_context_menu(self.dialog.games, pos)
        add.assert_called_once_with("60", "Browse Game", "", "50")

    def test_add_favorite_button_saves_and_selects_it(self):
        def run(dialog):
            dialog._place.setText("70")
            dialog._private.setText(" link ")
            dialog._accept()
            return dialog.result()

        with patch.object(ui._AddFavoriteDialog, "exec", run), \
                patch.object(ui.favorites_mod, "add_favorite") as add:
            self.dialog.tabs.setCurrentIndex(0)
            self.dialog.add_favorite_button.click()
        add.assert_called_once_with("70", "", "link")
        self.assertEqual(self.dialog.tabs.currentIndex(), 1)


class AddFavoriteButtonTests(unittest.TestCase):
    def test_button_matches_add_account_and_keeps_no_focus_outline_after_a_click(self):
        app = QApplication.instance() or QApplication([])
        with patch.object(ui.favorites_mod, "load_favorites", return_value=[]), \
                patch.object(ui.QTimer, "singleShot"):
            dialog = ui._GamesSelectorDialog()
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        dialog.show()
        dialog.tabs.setCurrentIndex(1)
        app.processEvents()
        button = dialog.add_favorite_button
        self.assertIsInstance(button, ui.QToolButton)
        self.assertFalse(button.icon().isNull())
        self.assertIn("min-height: 28px", button.styleSheet())
        with patch.object(ui._AddFavoriteDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        self.assertFalse(button.hasFocus())


class AddFavoriteDialogTests(unittest.TestCase):
    def test_place_id_must_be_numeric(self):
        QApplication.instance() or QApplication([])
        dialog = ui._AddFavoriteDialog()
        self.addCleanup(dialog.deleteLater)
        dialog._place.setText("not a number")
        dialog._accept()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(dialog._error.isHidden())


class MainWindowFavoriteTests(unittest.TestCase):
    def test_selector_applies_the_favorite_private_server(self):
        QApplication.instance() or QApplication([])
        combo, private = QComboBox(), QComboBox()
        for box in (combo, private):
            box.setEditable(True)
            self.addCleanup(box.deleteLater)
        window = SimpleNamespace(_place_id_edit=combo, _private_server_edit=private)
        with patch.object(ui, "_GamesSelectorDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.selected_place_id = "30"
            dialog.return_value.selected_private_server = "vip-link"
            ui.AccountManagerUIQt._open_games_selector(window)
        self.assertEqual((combo.currentText(), private.currentText()), ("30", "vip-link"))

    def test_join_menu_no_longer_has_save_current_game(self):
        QApplication.instance() or QApplication([])
        manager = Mock()
        manager.accounts = {}
        manager.get_encryption_method.return_value = "none"
        with patch.object(ui.QTimer, "singleShot"), patch.object(ui.threading.Thread, "start"), \
                patch.object(ui.AccountManagerUIQt, "_setup_system_tray"), \
                patch.object(ui.EncryptionConfig, "is_setup_complete", return_value=True):
            window = ui.AccountManagerUIQt(manager)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        texts = [action.text() for menu in window.findChildren(ui.QMenu) for action in menu.actions()]
        self.assertIn("Small Server", texts)
        self.assertNotIn("Save Current Game", texts)
        self.assertEqual(window._place_id_edit.count(), 0)


if __name__ == "__main__":
    unittest.main()
