import unittest
from unittest.mock import patch

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QColor, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QPushButton

from features import color_themes
from utils import icons


def painted_colors(pixmap):
    image = pixmap.toImage()
    found = set()
    for y in range(image.height()):
        for x in range(image.width()):
            color = QColor(image.pixelColor(x, y))
            if color.alpha() > 200:
                found.add(color.name().upper())
    return found


class IconTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        icons._cache.clear()

    def test_every_icon_is_valid_svg(self):
        for name in icons.PATHS:
            with self.subTest(icon=name):
                self.assertTrue(QSvgRenderer(QByteArray(icons._svg(name, "#FFFFFF"))).isValid())

    def test_every_icon_draws_something_in_the_requested_color(self):
        for name in icons.PATHS:
            with self.subTest(icon=name):
                self.assertIn("#FF8800", painted_colors(icons.pixmap(name, "#FF8800")))

    def test_every_icon_leaves_room_around_the_edges(self):
        for name in icons.PATHS:
            with self.subTest(icon=name):
                image = icons.pixmap(name, "#FFFFFF").toImage()
                self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
                self.assertEqual(image.pixelColor(image.width() - 1, image.height() - 1).alpha(), 0)

    def test_the_size_is_respected_and_results_are_cached(self):
        small, large = icons.pixmap("plus", "#FFFFFF", 16), icons.pixmap("plus", "#FFFFFF", 32)
        self.assertEqual(small.width(), 16)
        self.assertEqual(large.width(), 32)
        self.assertIs(icons.pixmap("plus", "#FFFFFF", 16), small)
        self.assertIsNot(icons.pixmap("plus", "#000000", 16), small)

    def test_unknown_icons_are_an_error(self):
        with self.assertRaises(KeyError):
            icons.pixmap("no-such-icon", "#FFFFFF")

    def test_high_dpi_screens_get_sharper_pixmaps(self):
        screen = type("Screen", (), {"devicePixelRatio": lambda self: 2.0})()
        with patch.object(icons.QGuiApplication, "primaryScreen", return_value=screen):
            pixmap = icons.pixmap("plus", "#FFFFFF", 16)
        self.assertEqual(pixmap.width(), 32)
        self.assertEqual(pixmap.devicePixelRatio(), 2.0)

    def test_the_icon_has_a_color_for_each_button_state(self):
        icon = icons.make_icon("plus", normal="#111111", active="#222222", checked="#333333", disabled="#444444")
        size = QSize(16, 16)
        expected = {
            (QIcon.Mode.Normal, QIcon.State.Off): "#111111",
            (QIcon.Mode.Active, QIcon.State.Off): "#222222",
            (QIcon.Mode.Normal, QIcon.State.On): "#333333",
            (QIcon.Mode.Active, QIcon.State.On): "#333333",
            (QIcon.Mode.Disabled, QIcon.State.Off): "#444444",
        }
        for (mode, state), color in expected.items():
            with self.subTest(mode=mode, state=state):
                self.assertIn(color, painted_colors(icon.pixmap(size, mode, state)))

    def test_missing_state_colors_fall_back_sensibly(self):
        icon = icons.make_icon("plus", normal="#111111")
        self.assertIn("#111111", painted_colors(icon.pixmap(QSize(16, 16), QIcon.Mode.Active, QIcon.State.On)))

    def test_buttons_get_the_theme_colors(self):
        colors = color_themes.resolve_colors({"color_theme": "nord"})
        button = QPushButton("Accounts")
        button.setCheckable(True)
        icons.set_button_icon(button, "accounts", colors)
        self.assertFalse(button.icon().isNull())
        self.assertEqual(button.iconSize(), QSize(icons.ICON_SIZE, icons.ICON_SIZE))
        size = button.iconSize()
        self.assertIn(colors["MUTED"], painted_colors(button.icon().pixmap(size, QIcon.Mode.Normal, QIcon.State.Off)))
        self.assertIn(colors["ACCENT_TEXT"], painted_colors(button.icon().pixmap(size, QIcon.Mode.Normal, QIcon.State.On)))


if __name__ == "__main__":
    unittest.main()
