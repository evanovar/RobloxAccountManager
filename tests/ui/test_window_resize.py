import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QMouseEvent, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget

from features import settings_store
from utils import ui


class ResizeWindow(ui.AccountManagerUIQt):
    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self._init_window_size()
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        self._resize_handle = self.grip = ui._ResizeHandle(central)
        self._position_resize_handle()

    def closeEvent(self, event):
        self._save_window_size()
        QMainWindow.closeEvent(self, event)


class WindowResizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(settings_store, "_SETTINGS_PATH", str(Path(directory) / "ui_settings.json")))
        settings_store.invalidate()
        self.addCleanup(settings_store.invalidate)

    def window(self):
        window = ResizeWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    def test_original_size_is_the_minimum_and_expansion_is_allowed(self):
        window = self.window()
        self.assertEqual(window.size(), QSize(640, 520))
        window.resize(300, 200)
        self.assertEqual(window.size(), QSize(640, 520))
        window.resize(740, 620)
        self.assertEqual(window.size(), QSize(740, 620))

    def test_close_flushes_resize_and_the_next_window_restores_it(self):
        window = self.window()
        window.resize(700, 600)
        window.close()
        self.assertEqual(settings_store.get("main_window_size"), [700, 600])
        self.assertEqual(self.window().size(), QSize(700, 600))

    def test_bad_or_too_small_saved_sizes_cannot_break_startup(self):
        for value in (None, {}, [True, 600], ["700", 600], [700], [-1, 600], [320, 200]):
            with self.subTest(value=value):
                settings_store.save("main_window_size", value)
                self.assertEqual(self.window().size(), QSize(640, 520))

    def test_saved_size_fits_the_display_even_for_huge_json_integers(self):
        settings_store.save("main_window_size", [10**100, 10**100])
        window = self.window()
        available = window.screen().availableGeometry().size().expandedTo(QSize(640, 520))
        self.assertEqual(window.size(), available)

    def test_dragging_the_grip_resizes_and_cannot_go_below_minimum(self):
        window = self.window()
        window.move(0, 0)
        window.show()
        self.app.processEvents()
        grip = window.grip
        local = QPoint(14, 14)
        initial = grip.mapToGlobal(local)
        QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=local)
        moved = initial + QPoint(60, 60)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(local), QPointF(moved),
                            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(grip, event)
        QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=local)
        self.assertEqual(window.size(), QSize(700, 580))

        QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=local)
        initial = grip.mapToGlobal(local)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(local), QPointF(initial - QPoint(500, 500)),
                            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(grip, event)
        QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=local)
        self.assertEqual(window.size(), QSize(640, 520))

    def test_keyboard_resize_and_debounced_save(self):
        window = self.window()
        window.show()
        self.app.processEvents()
        window.grip.setFocus()
        with patch.object(ui.actions, "save_ui_setting") as save:
            for _ in range(3):
                QTest.keyClick(window.grip, Qt.Key.Key_Right)
            save.assert_not_called()
            QTest.qWait(500)
            save.assert_called_once_with("main_window_size", [670, 520])

    def test_maximizing_does_not_replace_the_saved_normal_size(self):
        window = self.window()
        window.resize(700, 600)
        window.showMaximized()
        self.app.processEvents()
        window._save_window_size()
        self.assertEqual(settings_store.get("main_window_size"), [700, 600])

    def test_main_layout_keeps_the_handle_clear_and_expands_the_account_list(self):
        manager = MagicMock()
        manager.accounts = {}
        manager.get_encryption_method.return_value = "none"
        manager.get_secure_setting.return_value = ""
        with patch.object(ui.QTimer, "singleShot"), \
                patch.object(ui.threading.Thread, "start"), \
                patch.object(ui.AccountManagerUIQt, "_setup_system_tray"), \
                patch.object(ui.EncryptionConfig, "is_setup_complete", return_value=True):
            window = ui.AccountManagerUIQt(manager)
            self.addCleanup(window.deleteLater)
            self.addCleanup(window.close)
            window.show()
            self.app.processEvents()
            self.assertEqual(window.size(), QSize(640, 520))
            before = window._account_list.size()
            window.resize(1000, 760)
            self.app.processEvents()
            self.assertGreater(window._account_list.width(), before.width())
            self.assertGreater(window._account_list.height(), before.height())
            grip = window._resize_handle
            self.assertEqual(grip.mapTo(window, grip.rect().bottomRight()), window.rect().bottomRight())
            self.assertEqual(window._page_stack.mapTo(window, window._page_stack.rect().bottomRight()).y(),
                             window.rect().bottom())
            hit_area = grip.mask().translated(grip.mapTo(window, QPoint()))
            for button in window.centralWidget().findChildren(QPushButton):
                if button.isVisible():
                    rect = button.rect().translated(button.mapTo(window, QPoint()))
                    self.assertTrue(hit_area.intersected(QRegion(rect)).isEmpty(), button.text())
