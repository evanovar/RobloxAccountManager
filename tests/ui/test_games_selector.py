import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QComboBox, QDialog, QListWidget

from classes.operation_result import OperationResult
from features.game_selector import Game
from utils import ui


class GamesSelectorTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.requests = []

        def load(query, session, page, done, thumbnail):
            cancel = threading.Event()
            self.requests.append((query, page, done, thumbnail, cancel))
            return cancel

        self.enterContext(patch.object(ui.game_selector_mod, "start_load", side_effect=load))
        self.enterContext(patch.object(ui.game_selector_mod, "start_thumbnails", side_effect=lambda *_: threading.Event()))
        with patch.object(ui.QTimer, "singleShot"):
            self.dialog = ui._GamesSelectorDialog()
        self.addCleanup(self.dialog.deleteLater)
        self.addCleanup(self.dialog.close)
        self.dialog.show()

    def respond(self, index=0, games=None, next_page="", remaining=None):
        self.requests[index][2](OperationResult.success(data={
            "games": games if games is not None else [Game("10", "20", "Test Game")],
            "next_page_token": next_page,
            "remaining_pages": remaining or [],
        }))
        self.app.processEvents()

    def test_popular_games_load_and_selection_enables_apply(self):
        self.dialog._load_games()
        self.assertEqual(self.requests[0][:2], ("", ""))
        self.assertFalse(self.dialog.apply.isEnabled())
        self.respond()
        self.assertEqual(self.dialog.games.count(), 1)
        self.dialog.games.setCurrentRow(0)
        self.assertTrue(self.dialog.apply.isEnabled())
        self.dialog.apply.click()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.dialog.selected_place_id, "20")
        self.assertTrue(self.requests[0][4].is_set())

    def test_clicking_a_thumbnail_selects_its_game(self):
        self.dialog._load_games()
        self.respond()
        self.app.processEvents()
        rect = self.dialog.games.visualItemRect(self.dialog.games.item(0))
        QTest.mouseClick(self.dialog.games.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        self.assertTrue(self.dialog.apply.isEnabled())

    def test_double_clicking_a_game_applies_its_root_place_id(self):
        self.dialog._load_games()
        self.respond()
        self.app.processEvents()
        pos = self.dialog.games.visualItemRect(self.dialog.games.item(0)).center()
        QTest.mouseClick(self.dialog.games.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        QTest.mouseDClick(self.dialog.games.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.dialog.selected_place_id, "20")

    def test_popular_games_support_next_and_previous_without_a_search(self):
        self.dialog._load_games()
        self.respond(remaining=[[Game("11", "21", "Second page")]])
        self.assertTrue(self.dialog.next.isEnabled())
        self.dialog.next.click()
        self.assertEqual(self.dialog.games.item(0).data(Qt.ItemDataRole.UserRole).place_id, "21")
        self.assertEqual(self.dialog.page_label.text(), "Page 2")
        self.assertTrue(self.dialog.previous.isEnabled())
        self.dialog.previous.click()
        self.assertEqual(self.dialog.games.item(0).data(Qt.ItemDataRole.UserRole).place_id, "20")
        self.assertEqual(len(self.requests), 1)

    def test_typing_debounces_search_and_ignores_old_results(self):
        self.dialog._load_games()
        self.dialog.search.setText("new")
        self.assertTrue(self.requests[0][4].is_set())
        self.respond()
        self.assertEqual(self.dialog.games.count(), 0)
        QTest.qWait(400)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[1][0], "new")
        self.respond(1, [Game("11", "21", "New Game")])
        self.assertEqual(self.dialog.games.count(), 1)

    def test_new_query_clears_the_old_selection_and_disables_apply(self):
        self.dialog._load_games()
        self.respond()
        self.dialog.games.setCurrentRow(0)
        self.dialog.search.setText("other")
        self.assertFalse(self.dialog.apply.isEnabled())
        self.assertEqual(self.dialog.games.count(), 0)

    def test_enter_searches_without_accepting_an_existing_selection(self):
        self.dialog._load_games()
        self.respond()
        self.dialog.games.setCurrentRow(0)
        self.dialog.search.setFocus()
        QTest.keyClick(self.dialog.search, Qt.Key.Key_Return)
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)
        self.assertEqual(self.dialog.selected_place_id, "")
        self.assertEqual(len(self.requests), 2)

    def test_pages_replace_results_and_previous_uses_the_cache(self):
        self.dialog.search.setText("game")
        self.dialog._load_games()
        self.respond(next_page="next")
        self.dialog.games.setCurrentRow(0)
        self.dialog.next.click()
        self.assertEqual(self.requests[1][:2], ("game", "next"))
        self.respond(1, [Game("11", "21", "Other")])
        self.assertEqual(self.dialog.games.count(), 1)
        self.assertEqual(self.dialog.games.item(0).data(Qt.ItemDataRole.UserRole).place_id, "21")
        self.assertFalse(self.dialog.apply.isEnabled())
        self.assertFalse(self.dialog.next.isEnabled())
        self.assertEqual(self.dialog.page_label.text(), "Page 2")
        self.dialog.previous.click()
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.dialog.games.item(0).data(Qt.ItemDataRole.UserRole).place_id, "20")
        self.dialog.next.click()
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.dialog.games.item(0).data(Qt.ItemDataRole.UserRole).place_id, "21")

    def test_failed_next_page_preserves_previous_page_and_can_be_retried(self):
        self.dialog._load_games()
        self.respond(next_page="next")
        self.dialog.games.setCurrentRow(0)
        self.dialog.next.click()
        self.assertFalse(self.dialog.apply.isEnabled())
        self.requests[1][2](OperationResult.failure("X", "Games", "Try again."))
        self.app.processEvents()
        self.assertEqual(self.dialog.page_label.text(), "Page 1")
        self.assertTrue(self.dialog.apply.isEnabled())
        self.assertTrue(self.dialog.next.isEnabled())
        self.dialog.next.click()
        self.assertEqual(self.requests[2][1], "next")

    def test_grid_is_default_and_list_view_preserves_selection_without_searching(self):
        self.dialog._load_games()
        self.respond()
        self.assertEqual(self.dialog.games.viewMode(), QListWidget.ViewMode.IconMode)
        self.dialog.games.setCurrentRow(0)
        self.dialog.list_view.click()
        self.assertEqual(self.dialog.games.viewMode(), QListWidget.ViewMode.ListMode)
        self.assertTrue(self.dialog.apply.isEnabled())
        self.assertEqual(len(self.requests), 1)
        self.dialog.list_view.click()
        self.assertTrue(self.dialog.apply.isEnabled())

    def test_wheel_scrolling_keeps_its_speed_after_list_to_grid_switches(self):
        self.dialog._load_games()
        self.respond(games=[Game(str(i), str(i + 100), f"Game {i}") for i in range(1, 41)])

        def wheel_distance():
            self.app.processEvents()
            bar = self.dialog.games.verticalScrollBar()
            bar.setValue(0)
            view = self.dialog.games.viewport()
            pos = QPointF(view.rect().center())
            event = QWheelEvent(pos, QPointF(view.mapToGlobal(pos.toPoint())), QPoint(), QPoint(0, -120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(view, event)
            return bar.value()

        initial = wheel_distance()
        self.assertGreater(initial, 1)
        for _ in range(3):
            self.dialog.list_view.setChecked(True)
            self.dialog.list_view.setChecked(False)
            self.assertEqual(self.dialog.games.verticalScrollMode(), QAbstractItemView.ScrollMode.ScrollPerPixel)
            self.assertEqual(wheel_distance(), initial)
        self.assertIsNone(self.dialog.games.itemWidget(self.dialog.games.item(0)))

    def test_new_search_resets_pages_and_ignores_pending_page_response(self):
        self.dialog._load_games()
        self.respond(next_page="next")
        self.dialog.next.click()
        self.dialog.search.setText("different")
        self.assertTrue(self.requests[1][4].is_set())
        self.respond(1)
        self.assertEqual(self.dialog.games.count(), 0)
        self.assertEqual(self.dialog.page_label.text(), "Page 1")
        self.assertFalse(self.dialog.next.isEnabled())

    def test_failed_search_is_retryable_and_empty_results_are_explained(self):
        self.dialog._load_games()
        self.requests[0][2](OperationResult.failure("X", "Games", "Check your connection."))
        self.app.processEvents()
        self.assertIn("connection", self.dialog.status.text())
        self.assertTrue(self.dialog.search_button.isEnabled())
        self.assertFalse(self.dialog.apply.isEnabled())
        self.dialog.search_button.click()
        self.respond(1, [])
        self.assertIn("No games found", self.dialog.status.text())

    def test_thumbnail_updates_and_close_discards_pending_updates(self):
        self.dialog._load_games()
        self.respond()
        image = QImage(150, 150, QImage.Format.Format_RGB32)
        image.fill(QColor("#ff0000"))
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        self.requests[0][3]("10", bytes(data))
        self.app.processEvents()
        self.assertEqual(self.dialog._images["10"].width(), 150)
        item_rect = self.dialog.games.visualItemRect(self.dialog.games.item(0))
        rendered = self.dialog.games.viewport().grab().toImage()
        red_x = [x for x in range(item_rect.left(), item_rect.right())
                 if rendered.pixelColor(x, item_rect.top() + 20).name() == "#ff0000"]
        self.assertEqual(red_x[0], item_rect.left() + 8)
        self.assertEqual(len(red_x), 128)
        self.dialog.close()
        self.assertTrue(self.requests[0][4].is_set())
        self.requests[0][2](OperationResult.success(data={"games": [Game("11", "21", "Late")], "next_page_token": ""}))
        self.app.processEvents()
        self.assertEqual(self.dialog.games.count(), 1)


class FieldIntegrationTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])

    def test_apply_sets_the_place_field_and_emits_its_existing_change_signal(self):
        combo = QComboBox()
        combo.setEditable(True)
        changed = Mock()
        combo.currentTextChanged.connect(changed)
        window = SimpleNamespace(_place_id_edit=combo)
        with patch.object(ui, "_GamesSelectorDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.selected_place_id = "12345678901234"
            ui.AccountManagerUIQt._open_games_selector(window)
        self.assertEqual(combo.currentText(), "12345678901234")
        changed.assert_called_once_with("12345678901234")

    def test_cancel_keeps_the_existing_place_field(self):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setCurrentText("123")
        with patch.object(ui, "_GamesSelectorDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            ui.AccountManagerUIQt._open_games_selector(SimpleNamespace(_place_id_edit=combo))
        self.assertEqual(combo.currentText(), "123")

    def test_main_window_search_button_is_to_the_right_of_place_id(self):
        manager = Mock()
        manager.accounts = {}
        manager.get_encryption_method.return_value = "none"
        with patch.object(ui.QTimer, "singleShot"), patch.object(ui.threading.Thread, "start"), \
                patch.object(ui.AccountManagerUIQt, "_setup_system_tray"), \
                patch.object(ui.EncryptionConfig, "is_setup_complete", return_value=True):
            window = ui.AccountManagerUIQt(manager)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.show()
        QApplication.processEvents()
        button = window._games_selector_btn
        self.assertEqual(button.accessibleName(), "Open Games Selector")
        self.assertFalse(button.icon().isNull())
        self.assertEqual(button.width(), 18)
        self.assertEqual(button.iconSize().width(), 14)
        self.assertEqual(button.mapTo(window, button.rect().topRight()).x(),
                         window._place_id_edit.mapTo(window, window._place_id_edit.rect().topRight()).x())
        for mode, color in ((QIcon.Mode.Normal, ui.MUTED), (QIcon.Mode.Active, ui.MUTED)):
            image = button.icon().pixmap(14, 14, mode).toImage()
            pixels = [image.pixelColor(x, y) for y in range(image.height()) for x in range(image.width())]
            self.assertTrue(any(pixel.alpha() > 0 and pixel.name() == QColor(color).name() for pixel in pixels))
        self.assertEqual(window.minimumSize().width(), 640)
        labels = [label for label in window.findChildren(ui.QLabel) if label.text() == "Place ID"]
        label = next(label for label in labels if label.isVisible())
        self.assertGreater(button.mapTo(window, button.rect().topLeft()).x(),
                           label.mapTo(window, label.rect().topRight()).x())
        with patch.object(ui, "_GamesSelectorDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            button.click()
        dialog.assert_called_once_with(window)


if __name__ == "__main__":
    unittest.main()
