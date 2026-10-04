import unittest
from unittest.mock import patch

import shiboken6
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from utils import splash

SETTINGS = {"ui_animations": True}


class SplashCase(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        splash.dismiss()
        self.addCleanup(splash.dismiss)
        self.enabled = patch.object(splash, "_enabled", return_value=True)
        self.enabled.start()
        self.addCleanup(self.enabled.stop)
        self.settings = patch.object(splash.settings_store, "load", return_value=dict(SETTINGS))
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def start(self, animate=True):
        with patch.object(splash.motion, "animations_enabled", return_value=animate):
            self.assertTrue(splash.show("9.9.9", []))
        return splash._active


class LifecycleTests(SplashCase):
    def test_show_creates_one_visible_splash(self):
        window = self.start()
        self.assertTrue(splash.is_active())
        self.assertTrue(window.isVisible())
        self.assertFalse(splash.show("9.9.9", []))

    def test_disabled_setting_creates_nothing(self):
        with patch.object(splash, "_enabled", return_value=False):
            self.assertFalse(splash.show("9.9.9", []))
        self.assertFalse(splash.is_active())

    def test_status_without_a_splash_is_harmless(self):
        splash.status("Starting", 0.5)
        splash.pause()
        splash.resume()
        splash.dismiss()
        self.assertFalse(splash.is_active())

    def test_pause_hides_and_resume_shows_again(self):
        window = self.start()
        splash.pause()
        self.assertFalse(window.isVisible())
        splash.resume()
        self.assertTrue(window.isVisible())

    def test_dismiss_hides_and_clears(self):
        window = self.start()
        splash.dismiss()
        self.assertFalse(splash.is_active())
        self.assertFalse(window.isVisible())

    def test_it_is_centred_on_the_screen(self):
        window = self.start()
        area = self.app.primaryScreen().availableGeometry()
        self.assertLessEqual(abs(window.geometry().center().x() - area.center().x()), 1)
        self.assertLessEqual(abs(window.geometry().center().y() - area.center().y()), 1)


class ProgressTests(SplashCase):
    def test_progress_is_clamped(self):
        window = self.start(animate=False)
        splash.status("x", 5)
        self.assertEqual(window.progress, 1.0)
        splash.status("x", -3)
        self.assertEqual(window.progress, 0.0)

    def test_none_means_indeterminate(self):
        window = self.start(animate=False)
        splash.status("Waiting for password", None)
        self.assertIsNone(window.target)
        self.assertEqual(window.status_text, "Waiting for password")

    def test_progress_moves_gradually_when_animated(self):
        window = self.start()
        splash.status("Halfway", 1.0)
        animation = window._progress_animation
        animation.setCurrentTime(animation.duration() // 4)
        self.assertGreater(window.progress, 0.0)
        self.assertLess(window.progress, 1.0)
        animation.setCurrentTime(animation.duration())
        self.assertEqual(window.progress, 1.0)

    def test_bar_is_drawn_to_the_progress(self):
        window = self.start(animate=False)
        accent = QColor(window.colors["ACCENT"]).rgb()
        y = 151

        splash.status("x", 0.0)
        empty = window.grab().toImage()
        self.assertNotEqual(QColor(empty.pixel(60, y)).rgb(), accent)

        splash.status("x", 1.0)
        full = window.grab().toImage()
        self.assertEqual(QColor(full.pixel(60, y)).rgb(), accent)
        self.assertEqual(QColor(full.pixel(splash.WIDTH - 60, y)).rgb(), accent)

        splash.status("x", 0.5)
        half = window.grab().toImage()
        self.assertEqual(QColor(half.pixel(60, y)).rgb(), accent)
        self.assertNotEqual(QColor(half.pixel(splash.WIDTH - 60, y)).rgb(), accent)


class RevealTests(SplashCase):
    def test_reveal_without_animation_shows_the_window_at_once(self):
        window = self.start(animate=False)
        target = QWidget()
        self.addCleanup(target.close)
        splash.reveal(target)
        self.assertTrue(target.isVisible())
        self.assertEqual(target.windowOpacity(), 1.0)
        self.assertFalse(window.isVisible())
        self.assertFalse(splash.is_active())

    def test_reveal_fades_and_finishes_fully_opaque(self):
        window = self.start()
        target = QWidget()
        self.addCleanup(target.close)
        splash.reveal(target)
        self.assertTrue(target.isVisible())
        self.assertFalse(splash.is_active())
        QTest.qWait(splash.FADE_MS * 2)
        self.assertEqual(target.windowOpacity(), 1.0)
        self.assertTrue(not shiboken6.isValid(window) or not window.isVisible())

    def test_reveal_without_a_splash_just_shows_the_window(self):
        target = QWidget()
        self.addCleanup(target.close)
        splash.reveal(target)
        self.assertTrue(target.isVisible())


class ErrorDialogTests(SplashCase):
    def test_an_error_dialog_dismisses_the_splash_first(self):
        from utils import ui

        self.start()
        with patch.object(ui, "QMessageBox") as box:
            box.return_value.exec.return_value = 0
            ui._show_error(None, "Error", "Something broke")
        self.assertFalse(splash.is_active())


if __name__ == "__main__":
    unittest.main()
