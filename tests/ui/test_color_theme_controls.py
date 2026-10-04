import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton

from features import color_themes
from utils import ui


def pixel(widget, x, y):
    return QColor(widget.grab().toImage().pixel(x, y)).name().upper()


class ThemePreviewTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])

    def test_preview_paints_the_theme_colours(self):
        colors = color_themes.resolve_colors({"color_theme": "nord"})
        preview = ui._ThemePreview(colors)
        preview.resize(320, 76)
        self.assertEqual(pixel(preview, 300, 70), colors["BG"])
        self.assertEqual(pixel(preview, 4, 70), colors["PANEL"])
        self.assertEqual(pixel(preview, 230, 12), colors["ACCENT"])

    def test_preview_follows_set_colors(self):
        preview = ui._ThemePreview(color_themes.resolve_colors({}))
        preview.resize(320, 76)
        preview.set_colors(color_themes.resolve_colors({"color_theme": "amoled"}))
        self.assertEqual(pixel(preview, 300, 70), "#000000")


class ThemeControlsTests(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.settings = {}
        self.enterContext(patch.object(ui.actions, "load_ui_settings", side_effect=lambda: dict(self.settings)))
        self.saved = {}
        self.enterContext(patch.object(ui.actions, "save_ui_setting", side_effect=self.save))

        combo = QComboBox()
        for key, label in color_themes.theme_choices():
            combo.addItem(label, key)
        self.window = SimpleNamespace(
            _color_theme_combo=combo,
            _theme_preview=ui._ThemePreview(color_themes.resolve_colors({})),
            _accent_button=QPushButton(),
            _accent_reset_button=QPushButton(),
            _color_theme_hint=QLabel(),
        )
        for name in ("_selected_theme_colors", "_refresh_color_theme_controls", "_color_theme_pending",
                     "_on_color_theme_changed", "_reset_accent_color"):
            setattr(self.window, name, getattr(ui.AccountManagerUIQt, name).__get__(self.window))

    def save(self, key, value):
        self.saved[key] = value
        self.settings[key] = value

    def test_default_selection_matches_the_running_theme_and_needs_no_restart(self):
        with patch.object(ui, "_THEME", color_themes.resolve_colors({})):
            self.window._refresh_color_theme_controls()
        self.assertEqual(self.window._color_theme_hint.text(), "Color themes are applied when the application starts.")
        self.assertEqual(self.window._accent_button.text(), "#0078D7")
        self.assertFalse(self.window._accent_reset_button.isEnabled())

    def test_choosing_a_theme_saves_it_and_asks_for_a_restart(self):
        combo = self.window._color_theme_combo
        with patch.object(ui, "_THEME", color_themes.resolve_colors({})):
            combo.setCurrentIndex(combo.findData("nord"))
            self.window._on_color_theme_changed(combo.currentIndex())
        self.assertEqual(self.saved["color_theme"], "nord")
        self.assertEqual(self.window._color_theme_hint.text(), "Restart the application to use the new colors.")
        self.assertEqual(self.window._accent_button.text(), color_themes.PRESETS["nord"]["ACCENT"])

    def test_switching_back_to_the_running_theme_clears_the_restart_hint(self):
        combo = self.window._color_theme_combo
        with patch.object(ui, "_THEME", color_themes.resolve_colors({})):
            combo.setCurrentIndex(combo.findData("nord"))
            self.window._on_color_theme_changed(combo.currentIndex())
            combo.setCurrentIndex(combo.findData("default"))
            self.window._on_color_theme_changed(combo.currentIndex())
        self.assertEqual(self.window._color_theme_hint.text(), "Color themes are applied when the application starts.")

    def test_reset_accent_removes_the_custom_accent(self):
        self.settings["accent_color"] = "#FFD400"
        with patch.object(ui, "_THEME", color_themes.resolve_colors({})):
            self.window._refresh_color_theme_controls()
            self.assertTrue(self.window._accent_reset_button.isEnabled())
            self.assertEqual(self.window._accent_button.text(), "#FFD400")
            self.window._reset_accent_color()
        self.assertEqual(self.saved["accent_color"], "")
        self.assertEqual(self.window._accent_button.text(), "#0078D7")
        self.assertFalse(self.window._accent_reset_button.isEnabled())


class RunningThemeTests(unittest.TestCase):
    def test_module_colours_come_from_the_resolved_theme(self):
        theme = color_themes.resolve_colors(ui.actions.load_ui_settings())
        self.assertEqual(ui.BG, theme["BG"])
        self.assertEqual(ui.FG_ACCENT, theme["ACCENT"])
        self.assertEqual(ui.ACCENT_TEXT, theme["ACCENT_TEXT"])


if __name__ == "__main__":
    unittest.main()
