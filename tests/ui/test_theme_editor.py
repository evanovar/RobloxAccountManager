from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea
from shiboken6 import isValid

from features import settings_store
from features.theme_library import ThemeLibrary
from features.theme_model import ThemeError, builtin_theme
from tests.ui.test_theme_background import write_video
from utils.theme_editor import ThemeEditor
from utils.theme_runtime import ThemeManager


CUSTOM_ID = "9fe16da2-f67f-4db4-b42b-1bbaedcf239f"


class MemoryLibrary:
    def __init__(self):
        self.saved = {t.id: t for t in (builtin_theme("default"), builtin_theme("nord"))}
        self.active = "builtin:default"
        self.fail_save = False
        self.exported = None
        self.worker_threads = []
        self.discarded = []

    def list_themes(self):
        return [theme.clone() for theme in self.saved.values()]

    def load(self, theme_id):
        return self.saved[theme_id].clone()

    def activate(self, theme_id):
        self.active = theme_id

    def save(self, theme, name=None):
        self.worker_threads.append(threading.get_ident())
        if self.fail_save:
            raise ThemeError("Choose a writable theme folder and try again.")
        result = theme.clone()
        result.id = result.id if result.id and not result.id.startswith("builtin:") else CUSTOM_ID
        result.name = name or result.name
        self.saved[result.id] = result.clone()
        return result

    def import_theme(self, path):
        self.worker_threads.append(threading.get_ident())
        theme = builtin_theme("nord")
        theme.id = "foreign-id"
        return theme

    def export_theme(self, theme, path):
        self.worker_threads.append(threading.get_ident())
        self.exported = (theme.clone(), path)

    def discard_import(self, theme):
        self.discarded.append(theme)


class PreviewManager(QObject):
    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.library = MemoryLibrary()
        self.theme = self.library.load(self.library.active)
        self.colors = self.theme.colors

    def apply(self, theme):
        self.theme = theme.clone()
        self.colors = self.theme.colors
        self.changed.emit(self.theme)

    def activate(self, theme):
        self.library.active = theme.id
        self.apply(theme)


class ThemeEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.previous_font = cls.app.font()
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        cls.app.setFont(QFont("Segoe UI", 9))

    @classmethod
    def tearDownClass(cls):
        cls.app.setFont(cls.previous_font)

    def setUp(self):
        self.manager = PreviewManager()
        self.enterContext(patch("utils.theme_editor.bind_style"))
        self.editor = ThemeEditor(self.manager)
        self.addCleanup(self.editor.deleteLater)
        self.editor.show()
        self.app.processEvents()

    def wait(self):
        deadline = time.monotonic() + 3
        while self.editor.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertFalse(self.editor.busy)

    def test_builtin_accepts_colors_and_background_without_mutating_preset(self):
        original = self.manager.library.load("builtin:default")
        self.editor.set_color("ACCENT", "#FA4570")
        self.editor.set_background(enabled=True, path="wallpaper.png", blur=12, dim=73)
        self.assertTrue(self.editor.dirty)
        self.assertEqual(self.manager.theme.colors["ACCENT"], "#FA4570")
        self.assertEqual(self.manager.theme.background.dim, 73)
        self.assertEqual(self.manager.theme.background.blur, 12)
        self.assertEqual(self.editor.theme.id, "")
        self.assertEqual(self.manager.library.load(original.id), original)

    def test_save_creates_independent_custom_theme_on_worker(self):
        self.editor.set_color("ACCENT", "#FA4570")
        self.editor.save_theme("My colors")
        self.wait()
        self.assertFalse(self.editor.dirty)
        self.assertEqual(self.manager.library.active, CUSTOM_ID)
        self.assertEqual(self.manager.library.saved[CUSTOM_ID].name, "My colors")
        self.assertNotEqual(self.manager.library.worker_threads[-1], threading.get_ident())

    def test_revert_restores_saved_appearance(self):
        original = self.editor.theme.clone()
        self.editor.set_color("TEXT", "#CCCCCC")
        self.editor.set_background(blur=40, dim=80)
        self.editor.revert_changes()
        self.assertEqual(self.editor.theme, original)
        self.assertEqual(self.manager.theme, original)
        self.assertFalse(self.editor.dirty)

    def test_cancel_protects_dirty_selection_and_exit(self):
        self.editor.set_color("ACCENT", "#FA4570")
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.editor.select_theme("builtin:nord"))
            self.assertFalse(self.editor.confirm_discard())
        self.assertEqual(self.manager.library.active, "builtin:default")
        self.assertEqual(self.editor.theme.colors["ACCENT"], "#FA4570")

    def test_import_is_independent_dirty_draft_and_revert_restores_previous_theme(self):
        self.editor.import_theme("theme.ramtheme")
        self.wait()
        self.assertTrue(self.editor.dirty)
        self.assertEqual(self.editor.theme.id, "")
        self.assertEqual(self.manager.library.active, "builtin:default")
        self.editor.revert_changes()
        self.assertEqual(self.editor.theme.id, "builtin:default")
        self.assertEqual(len(self.manager.library.discarded), 1)

    def test_export_uses_current_draft_and_keeps_unsaved_status(self):
        self.editor.set_color("ACCENT", "#FA4570")
        self.editor.export_theme("variation.ramtheme")
        self.wait()
        self.assertEqual(self.manager.library.exported[0].colors["ACCENT"], "#FA4570")
        self.assertTrue(self.editor.dirty)

    def test_failed_save_keeps_draft_and_releases_busy_state(self):
        self.editor.set_color("ACCENT", "#FA4570")
        self.manager.library.fail_save = True
        with patch.object(QMessageBox, "warning") as warning:
            self.editor.save_theme("My colors")
            self.wait()
        warning.assert_called_once()
        self.assertTrue(self.editor.dirty)
        self.assertEqual(self.editor.theme.colors["ACCENT"], "#FA4570")
        self.assertTrue(self.editor.save_button.isEnabled())

    def test_controls_are_accessible_and_background_sliders_are_independent(self):
        self.assertEqual(self.editor.blur_slider.accessibleName(), "Background blur")
        self.assertEqual(self.editor.dim_slider.accessibleName(), "Background dim")
        self.editor.blur_slider.setValue(26)
        self.editor.dim_slider.setValue(62)
        self.assertEqual((self.editor.theme.background.blur, self.editor.theme.background.dim), (26, 62))
        for role, button in self.editor.color_buttons.items():
            self.assertTrue(button.accessibleName(), role)
            self.assertIn(self.editor.theme.colors[role], button.text())

    def test_library_contains_only_selectable_themes_and_no_duplicate_action(self):
        self.assertEqual([self.editor.selector.itemText(i) for i in range(self.editor.selector.count())],
                         ['Default', 'Nord'])
        self.assertTrue(all(self.editor.selector.itemData(i) for i in range(self.editor.selector.count())))
        self.assertNotIn('Duplicate', [button.text() for button in self.editor.findChildren(QPushButton)])

    def test_page_uses_flat_sections_without_surface_tint_control(self):
        self.assertEqual(self.editor.findChildren(QGroupBox), [])
        self.assertNotIn('Surface tint', [label.text() for label in self.editor.findChildren(QLabel)])

    def test_save_actions_stay_near_library_when_controls_scroll(self):
        self.editor.resize(420, 440)
        self.app.processEvents()
        preview_top = self.editor.preview.mapTo(self.editor, self.editor.preview.rect().topLeft()).y()
        save_top = self.editor.save_button.mapTo(self.editor, self.editor.save_button.rect().topLeft()).y()
        self.assertLess(save_top, preview_top)
        scroll = self.editor.findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        self.app.processEvents()
        self.assertEqual(self.editor.save_button.mapTo(self.editor, self.editor.save_button.rect().topLeft()).y(), save_top)
        self.assertTrue(self.editor.save_button.isVisible())

    def test_switching_presets_retains_enabled_background_and_new_palette(self):
        self.editor.set_background(enabled=True, path='wallpaper.png', blur=12, dim=25)
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Cancel) as warning:
            self.assertTrue(self.editor.select_theme('builtin:nord'))
        warning.assert_not_called()
        self.assertEqual(self.editor.theme.colors['BG'], '#2E3440')
        self.assertEqual(self.editor.theme.background.path, 'wallpaper.png')
        self.assertTrue(self.editor.theme.background.enabled)
        self.assertEqual(self.manager.theme.id, '')
        self.assertEqual(self.manager.theme.background.blur, 12)
        self.assertTrue(self.editor.dirty)
        self.assertFalse(self.manager.library.load('builtin:nord').background.enabled)

    def test_preview_shows_every_palette_role(self):
        theme = builtin_theme('nord')
        theme.colors = {role: '#{:02X}{:02X}{:02X}'.format(
            (index * 59 + 19) % 256, (index * 101 + 71) % 256, (index * 149 + 37) % 256
        ) for index, role in enumerate(theme.colors)}
        self.editor.preview.resize(400, 230)
        self.editor.preview.set_colors(theme.colors)
        image = self.editor.preview.grab().toImage()
        pixels = {image.pixelColor(x, y).name().upper()
                  for y in range(image.height()) for x in range(image.width())}
        for role, color in theme.colors.items():
            with self.subTest(role=role):
                self.assertIn(color, pixels)

    def test_busy_editor_rejects_mutations_until_worker_finishes(self):
        gate = threading.Event()
        original_save = self.manager.library.save

        def delayed_save(theme, name=None):
            gate.wait(2)
            return original_save(theme, name)

        self.manager.library.save = delayed_save
        self.editor.set_color("ACCENT", "#FA4570")
        self.editor.save_theme("My colors")
        self.editor.set_color("ACCENT", "#000000")
        self.assertFalse(self.editor.select_theme("builtin:nord"))
        self.assertEqual(self.editor.theme.colors["ACCENT"], "#FA4570")
        gate.set()
        self.wait()

    def test_existing_custom_save_updates_same_id_and_keeps_starting_palette(self):
        self.editor.set_color("ACCENT", "#FA4570")
        self.editor.save_theme("My colors")
        self.wait()
        starting = self.editor.theme.starting_colors.copy()
        self.editor.set_color("TEXT", "#CCCCCC")
        self.assertEqual(self.manager.library.load(CUSTOM_ID).colors["TEXT"], starting["TEXT"])
        self.editor.save_theme()
        self.wait()
        self.assertEqual(self.editor.theme.id, CUSTOM_ID)
        self.assertEqual(self.editor.theme.starting_colors, starting)
        self.assertEqual(self.manager.library.load(CUSTOM_ID).colors["TEXT"], "#CCCCCC")

    def test_starting_color_reset_clears_builtin_edit_when_appearance_matches(self):
        self.editor.set_color("ACCENT", "#FA4570")
        self.editor.reset_color("ACCENT")
        self.assertFalse(self.editor.dirty)
        self.assertEqual(self.editor.theme.id, "builtin:default")

    def test_worker_start_failure_is_actionable_and_keeps_editor_usable(self):
        self.editor.set_color("ACCENT", "#FA4570")
        with patch("utils.theme_editor.threading.Thread.start", side_effect=RuntimeError("Unable to start worker")), \
                patch.object(QMessageBox, "warning") as warning:
            self.assertFalse(self.editor.save_theme("My colors"))
        warning.assert_called_once()
        self.assertFalse(self.editor.busy)
        self.assertTrue(self.editor.dirty)
        self.assertTrue(self.editor.save_button.isEnabled())

    def test_discard_on_exit_restores_saved_theme(self):
        original = self.editor.theme
        self.editor.set_color("ACCENT", "#FA4570")
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.editor.confirm_discard())
        self.assertEqual(self.manager.theme, original)

    def test_save_on_exit_waits_for_worker_and_failed_save_keeps_exit_guard(self):
        self.editor.set_color("ACCENT", "#FA4570")
        self.manager.library.fail_save = True
        with patch("utils.theme_editor.QInputDialog.getText", return_value=("My colors", True)), \
                patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Save):
            self.assertFalse(self.editor.confirm_discard())
        self.assertTrue(self.editor.dirty)
        self.assertFalse(self.editor.busy)

    def test_new_draft_preview_failure_keeps_original_state(self):
        original = self.editor.theme
        with patch.object(self.manager, "apply", side_effect=RuntimeError("Preview unavailable")), \
                patch.object(QMessageBox, "warning") as warning:
            self.assertFalse(self.editor.new_theme())
        warning.assert_called_once()
        self.assertEqual(self.editor.theme, original)
        self.assertFalse(self.editor.dirty)

    def test_import_cleanup_failure_restores_draft_preview_when_revert_fails(self):
        self.editor.import_theme("theme.ramtheme")
        self.wait()
        imported = self.editor.theme
        with patch.object(self.manager.library, "discard_import", side_effect=ThemeError("File is in use")), \
                patch.object(QMessageBox, "warning"):
            self.assertFalse(self.editor.revert_changes())
        self.assertEqual(self.editor.theme, imported)
        self.assertEqual(self.manager.theme, imported)
        self.assertTrue(self.editor.dirty)

    def test_library_notices_are_visible_without_blocking_editor(self):
        self.manager.library.issues = ["A saved theme is unavailable: repair its theme.json file."]
        self.editor._reload_library()
        self.assertTrue(self.editor.library_notice.isVisible())
        self.assertIn("unavailable", self.editor.library_notice.text())
        self.assertEqual(self.editor.library_notice.accessibleName(), "Theme library notices")

    def test_compact_editor_does_not_require_horizontal_scrolling(self):
        self.editor.resize(420, 560)
        self.app.processEvents()
        scroll = self.editor.findChild(QScrollArea)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.assertTrue(self.editor.rect().contains(self.editor.save_button.geometry().bottomRight()))

    def test_colors_return_to_two_columns_after_widening_editor(self):
        self.editor.resize(420, 560)
        self.app.processEvents()
        self.editor.resize(690, 680)
        self.app.processEvents()
        accent = self.editor.color_buttons["ACCENT"]
        background = self.editor.color_buttons["BG"]
        self.assertEqual(accent.y(), background.y())
        self.assertLess(accent.x(), background.x())

    def test_import_cleanup_error_after_committed_save_keeps_saved_state(self):
        self.editor.import_theme("theme.ramtheme")
        self.wait()
        with patch.object(self.manager.library, "discard_import", side_effect=ThemeError("File is in use")), \
                patch.object(QMessageBox, "warning") as warning:
            self.editor.save_theme("Imported colors")
            self.wait()
        warning.assert_called_once()
        self.assertEqual(self.manager.library.active, CUSTOM_ID)
        self.assertEqual(self.editor.theme.id, CUSTOM_ID)
        self.assertFalse(self.editor.dirty)
        self.assertTrue(self.editor.confirm_discard())
        self.assertEqual(len(self.manager.library.discarded), 1)

    def test_new_captures_unsaved_live_appearance_without_prompt(self):
        original = self.manager.library.load("builtin:default")
        self.editor.set_color("ACCENT", "#FF0000")
        self.editor.set_color("ACCENT_SOFT", "#123456")
        self.editor.set_background(enabled=True, path="current.png", blur=24, dim=68)
        current = self.editor.theme
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Cancel) as warning:
            self.assertTrue(self.editor.new_theme())
        warning.assert_not_called()
        self.assertEqual(self.editor.theme.colors, current.colors)
        self.assertEqual(self.editor.theme.background, current.background)
        self.assertEqual(self.editor.theme.starting_colors, current.colors)
        self.assertEqual(self.editor.theme.starting_customized, current.customized)
        self.assertEqual(self.manager.library.load(original.id), original)

    def test_background_file_shows_basename_and_keeps_full_path_tooltip(self):
        path = str(Path("C:/Themes/owned-media/background-123456.png"))
        self.editor.set_background(path=path)
        self.assertEqual(self.editor.background_path.text(), "background-123456.png")
        self.assertEqual(self.editor.background_path.toolTip(), path)


class ThemeEditorMediaDeletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path_patch = patch.object(settings_store, "_SETTINGS_PATH", str(self.root / "ui_settings.json"))
        self.path_patch.start()
        settings_store.invalidate()
        self.library = ThemeLibrary(self.root)
        self.previous_manager = getattr(self.app, "_ram_theme_manager", None)
        self.manager = ThemeManager(self.app, self.library)
        self.app._ram_theme_manager = self.manager
        self.window = QMainWindow()
        self.window.resize(600, 600)
        self.manager.register(self.window)
        self.editor = ThemeEditor(self.manager, self.window)
        self.window.setCentralWidget(self.editor)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.manager.close()
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.app._ram_theme_manager = self.previous_manager
        settings_store.invalidate()
        self.path_patch.stop()
        self.temp.cleanup()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QTest.qWait(10)
        self.assertTrue(predicate())

    def select_saved(self, video=False):
        theme = builtin_theme("nord")
        if video:
            path = self.root / "source.avi"
            write_video(path)
            theme.background.enabled = True
            theme.background.path = str(path)
        saved = self.library.save(theme, "Saved appearance")
        self.editor._reload_library()
        self.assertTrue(self.editor.select_theme(saved.id))
        if video:
            self.wait_until(lambda: not self.manager.background._frame.isNull())
        return saved

    def delete_selected(self):
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.editor._delete_clicked()
        self.wait_until(lambda: not self.editor.busy)

    def test_active_owned_video_deletes_after_decoder_objects_are_released(self):
        saved = self.select_saved(video=True)
        player, sink = self.manager.background._player, self.manager.background._sink
        with patch.object(QMessageBox, "warning") as warning:
            self.delete_selected()
        warning.assert_not_called()
        self.assertFalse((self.root / "themes" / saved.id).exists())
        self.assertEqual(self.manager.theme.id, "builtin:default")
        self.assertEqual(settings_store.get("active_theme"), "builtin:default")
        self.assertFalse(isValid(player))
        self.assertFalse(isValid(sink))

    def test_failed_delete_restores_existing_saved_selection_and_preview(self):
        saved = self.select_saved()
        with patch("features.theme_library.shutil.rmtree", side_effect=OSError("Folder is in use")), \
                patch.object(QMessageBox, "warning") as warning:
            self.delete_selected()
        warning.assert_called_once()
        self.assertEqual(self.manager.theme, saved)
        self.assertEqual(self.editor.theme, saved)
        self.assertEqual(settings_store.get("active_theme"), saved.id)
        self.assertTrue((self.root / "themes" / saved.id).exists())

    def test_partial_delete_failure_keeps_usable_default_selection(self):
        saved = self.select_saved()
        remove = shutil.rmtree

        def remove_then_fail(path):
            remove(path)
            raise OSError("Removal interrupted after deleting the directory")

        with patch("features.theme_library.shutil.rmtree", side_effect=remove_then_fail), \
                patch.object(QMessageBox, "warning") as warning:
            self.delete_selected()
        warning.assert_called_once()
        self.assertIn("Default", str(warning.call_args))
        self.assertEqual(self.manager.theme.id, "builtin:default")
        self.assertEqual(self.editor.theme.id, "builtin:default")
        self.assertEqual(settings_store.get("active_theme"), "builtin:default")
        self.assertFalse((self.root / "themes" / saved.id).exists())

    def test_delete_worker_start_failure_restores_video_preview(self):
        saved = self.select_saved(video=True)
        with patch("utils.theme_editor.threading.Thread.start", side_effect=RuntimeError("Worker unavailable")), \
                patch.object(QMessageBox, "warning") as warning:
            self.delete_selected()
        warning.assert_called_once()
        self.assertEqual(self.manager.theme, saved)
        self.assertEqual(settings_store.get("active_theme"), saved.id)
        self.wait_until(lambda: not self.manager.background._frame.isNull())

    def test_new_retains_imported_staging_until_save_or_revert(self):
        path = self.root / "source.png"
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        image.fill(QColor("#556677"))
        image.save(str(path))
        theme = builtin_theme("nord")
        theme.background.enabled = True
        theme.background.path = str(path)
        package = self.root / "example.ramtheme"
        self.library.export_theme(theme, package)
        self.editor.import_theme(package)
        self.wait_until(lambda: not self.editor.busy)
        staged = Path(self.editor.theme.background.path)
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Cancel) as warning:
            self.assertTrue(self.editor.new_theme())
        warning.assert_not_called()
        self.assertTrue(staged.exists())
        self.assertEqual(self.editor.theme.background.path, str(staged))
        self.editor.save_theme("Captured import")
        self.wait_until(lambda: not self.editor.busy)
        self.assertTrue(Path(self.editor.theme.background.path).exists())
        self.assertFalse(staged.exists())

    def test_save_uses_shared_selection_style(self):
        style = self.editor.save_button.styleSheet()
        self.assertIn(self.manager.colors["SELECT"], style)
        self.assertIn("QPushButton:disabled", style)
        self.assertIn(self.manager.colors["MUTED"], style)
