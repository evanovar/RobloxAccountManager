import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from utils import motion

STYLE = "QWidget { background: #151515; } QPushButton { background: #1A1A1A; color: #EDEDED; padding: 8px; }"


def brightness(widget):
    color = QColor(widget.grab().toImage().pixel(30, 8))
    return color.red() + color.green() + color.blue()


class MotionCase(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def make_window(self, animate=True):
        window = QWidget()
        window.setStyleSheet(STYLE)
        layout = QVBoxLayout(window)
        self.button = QPushButton("Button")
        layout.addWidget(self.button)
        self.filter = motion.MotionFilter("#EDEDED", animate=animate, parent=self.app)
        self.app.installEventFilter(self.filter)
        self.addCleanup(self.app.removeEventFilter, self.filter)
        window.resize(220, 90)
        window.show()
        QTest.qWait(60)
        self.addCleanup(window.close)
        self.window = window
        return window


class SettingsTests(unittest.TestCase):
    def test_animations_follow_the_setting_and_the_system(self):
        with patch.object(motion, "system_animations_enabled", return_value=True):
            self.assertTrue(motion.animations_enabled({}))
            self.assertTrue(motion.animations_enabled(None))
            self.assertFalse(motion.animations_enabled({"ui_animations": False}))
        with patch.object(motion, "system_animations_enabled", return_value=False):
            self.assertFalse(motion.animations_enabled({}))

    def test_the_system_check_never_raises(self):
        self.assertIsInstance(motion.system_animations_enabled(), bool)
        broken = type("U", (), {"SystemParametersInfoW": staticmethod(lambda *a: (_ for _ in ()).throw(OSError()))})()
        with patch.object(motion.ctypes, "windll", type("W", (), {"user32": broken})()):
            self.assertTrue(motion.system_animations_enabled())

    def test_install_does_nothing_when_turned_off(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNone(motion.install(app, "#FFFFFF", {"ui_animations": False}))
        installed = motion.install(app, "#FFFFFF", {})
        self.assertIsInstance(installed, motion.MotionFilter)
        app.removeEventFilter(installed)


class ButtonMotionTests(MotionCase):
    def test_a_button_gets_one_overlay_even_if_it_is_shown_again(self):
        window = self.make_window()
        window.hide()
        window.show()
        QTest.qWait(30)
        overlays = [child for child in self.button.children() if isinstance(child, motion._Overlay)]
        self.assertEqual(len(overlays), 1)

    def test_the_stylesheet_and_mouse_handling_are_untouched(self):
        clicks = []
        before = QPushButton("x")
        before_style = before.styleSheet()
        window = self.make_window()
        self.button.clicked.connect(lambda: clicks.append(1))
        QTest.mouseClick(self.button, Qt.MouseButton.LeftButton)
        self.assertEqual(clicks, [1])
        self.assertEqual(self.button.styleSheet(), before_style)
        overlay = next(c for c in self.button.children() if isinstance(c, motion._Overlay))
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertEqual(overlay.geometry(), self.button.rect())
        window.resize(300, 120)
        QTest.qWait(30)
        self.assertEqual(overlay.geometry(), self.button.rect())

    def test_hover_brightens_and_leaving_restores(self):
        self.make_window()
        idle = brightness(self.button)
        QApplication.sendEvent(self.button, QEvent(QEvent.Type.Enter))
        QTest.qWait(300)
        hovered = brightness(self.button)
        self.assertGreater(hovered, idle)
        QApplication.sendEvent(self.button, QEvent(QEvent.Type.Leave))
        QTest.qWait(300)
        self.assertEqual(brightness(self.button), idle)

    def test_pressing_is_brighter_than_hovering_and_releasing_goes_back(self):
        self.make_window()
        QApplication.sendEvent(self.button, QEvent(QEvent.Type.Enter))
        QTest.qWait(300)
        hovered = brightness(self.button)
        QTest.mousePress(self.button, Qt.MouseButton.LeftButton)
        QTest.qWait(250)
        pressed = brightness(self.button)
        self.assertGreater(pressed, hovered)
        QTest.mouseRelease(self.button, Qt.MouseButton.LeftButton)
        QTest.qWait(250)
        self.assertEqual(brightness(self.button), hovered)

    def test_the_change_is_gradual_not_instant(self):
        self.make_window()
        QApplication.sendEvent(self.button, QEvent(QEvent.Type.Enter))
        motion_object = next(c for c in self.button.children() if isinstance(c, motion.ButtonMotion))
        animation = motion_object._hover_animation
        self.assertEqual(animation.state(), animation.State.Running)
        animation.setCurrentTime(motion.HOVER_MS // 3)
        self.assertTrue(0.0 < motion_object.hover < 1.0)
        animation.setCurrentTime(motion.HOVER_MS)
        self.assertAlmostEqual(motion_object.hover, 1.0, places=2)

    def test_without_animation_the_change_is_immediate(self):
        self.make_window(animate=False)
        idle = brightness(self.button)
        QApplication.sendEvent(self.button, QEvent(QEvent.Type.Enter))
        self.app.processEvents()
        self.assertGreater(brightness(self.button), idle)

    def test_disabled_buttons_do_not_light_up(self):
        self.make_window()
        self.button.setEnabled(False)
        idle = brightness(self.button)
        QApplication.sendEvent(self.button, QEvent(QEvent.Type.Enter))
        QTest.qWait(250)
        self.assertEqual(brightness(self.button), idle)

    def test_tint_alpha_stays_in_range(self):
        self.make_window()
        motion_object = next(c for c in self.button.children() if isinstance(c, motion.ButtonMotion))
        for hover, press in ((0, 0), (1, 0), (1, 1), (5, 5)):
            motion_object.hover, motion_object.press = hover, press
            self.assertTrue(0 <= motion_object.current_alpha() <= 255)

    def test_other_widgets_are_left_alone(self):
        window = self.make_window()
        label = QLabel("text", window)
        label.show()
        QTest.qWait(30)
        self.assertEqual([c for c in label.children() if isinstance(c, motion.ButtonMotion)], [])


class FadeTests(MotionCase):
    def test_a_fade_starts_transparent_and_cleans_up_after_itself(self):
        window = self.make_window()
        animation = motion.fade_in(window, duration=80)
        self.assertIsNotNone(animation)
        self.assertIsNotNone(window.graphicsEffect())
        self.assertEqual(window.graphicsEffect().opacity(), 0.0)
        QTest.qWait(300)
        self.assertIsNone(window.graphicsEffect())

    def test_nothing_happens_when_disabled_or_hidden(self):
        window = self.make_window()
        self.assertIsNone(motion.fade_in(window, enabled=False))
        self.assertIsNone(window.graphicsEffect())
        window.hide()
        self.assertIsNone(motion.fade_in(window))
        self.assertIsNone(motion.fade_in(None))


if __name__ == "__main__":
    unittest.main()
