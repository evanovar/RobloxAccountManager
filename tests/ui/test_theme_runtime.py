import os
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor, QImage, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton

from features.theme_model import ThemeError, builtin_theme
from utils import theme_runtime


class MemoryLibrary:
    def __init__(self):
        self.selected = ''

    def startup(self, settings):
        return builtin_theme('default')

    def activate(self, theme_id):
        self.selected = theme_id


class ThemeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.previous = getattr(self.app, '_ram_theme_manager', None)
        self.manager = theme_runtime.ThemeManager(self.app, MemoryLibrary())
        self.app._ram_theme_manager = self.manager
        self.window = QMainWindow()
        self.manager.register(self.window)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.manager.close()
        self.app._ram_theme_manager = self.previous

    def test_live_styles_follow_roles_without_replacing_literal_colors(self):
        label = QLabel('Live', self.window)
        theme_runtime.bind_style(label, 'color: @RAM_TEXT@; border: 1px solid #112233;')
        changed = builtin_theme('nord')
        changed.colors['TEXT'] = '#FEDCBA'
        self.manager.apply(changed)
        self.assertIn('#FEDCBA', label.styleSheet())
        self.assertIn('#112233', label.styleSheet())

    def test_new_widget_uses_current_theme_and_palette(self):
        self.manager.apply(builtin_theme('forest'))
        label = QLabel('New', self.window)
        theme_runtime.bind_style(label, 'color: @RAM_TEXT@;')
        self.assertIn('#E4EFE8', label.styleSheet())
        self.assertEqual(self.app.palette().color(QPalette.ColorRole.Window).name(), '#0d1411')

    def test_preview_clones_draft_and_does_not_persist_selection(self):
        draft = builtin_theme('rose')
        self.manager.apply(draft)
        draft.colors['TEXT'] = '#000000'
        self.assertEqual(self.manager.colors['TEXT'], '#F3E8EE')
        self.assertEqual(self.manager.library.selected, '')
        self.manager.activate(builtin_theme('nord'))
        self.assertEqual(self.manager.library.selected, 'builtin:nord')

    def test_icons_refresh_and_destroyed_bindings_are_released(self):
        button = QPushButton('Test', self.window)
        theme_runtime.bind_icon(button, 'plus')
        old = button.icon().cacheKey()
        self.manager.apply(builtin_theme('rose'))
        self.assertNotEqual(old, button.icon().cacheKey())
        button.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.manager.apply(builtin_theme('nord'))

    def test_declared_surfaces_become_translucent_with_media(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = os.path.join(directory, 'background.png')
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        image.fill(QColor('#123456'))
        self.assertTrue(image.save(path))
        label = QLabel('Surface', self.window)
        theme_runtime.bind_style(label, 'background: @RAM_PANEL@; color: @RAM_TEXT@;')
        media = builtin_theme('default')
        media.background.enabled = True
        media.background.path = path
        self.manager.apply(media)
        self.assertIn('rgba(', label.styleSheet())
        self.assertIn('#EDEDED', label.styleSheet())

    def test_popup_surface_tokens_stay_opaque_under_media(self):
        media = builtin_theme('nord')
        media.background.enabled = True
        media.background.path = 'missing.png'
        self.manager.apply(media)
        style = self.manager.render('QMenu { background: @RAM_OPAQUE_PANEL@; }')
        self.assertIn('#343B49', style)
        self.assertNotIn('@RAM_', style)

    def test_list_item_foreground_tracks_theme_and_survives_deletion(self):
        listing = QListWidget(self.window)
        item = QListWidgetItem('Placeholder', listing)
        theme_runtime.bind_foreground(item, 'MUTED')
        self.manager.apply(builtin_theme('rose'))
        self.assertEqual(item.foreground().color().name(), '#b79aa8')
        listing.clear()
        self.manager.apply(builtin_theme('nord'))

    def test_invalid_preview_keeps_last_usable_theme(self):
        broken = builtin_theme('rose')
        broken.colors['TEXT'] = 'invalid'
        with self.assertRaises(ThemeError):
            self.manager.apply(broken)
        self.assertEqual(self.manager.theme.id, 'builtin:default')

    def test_avatar_placeholders_update_without_overwriting_loaded_photos(self):
        label = QLabel(self.window)
        theme_runtime.bind_placeholder(label, 24)
        self.manager.apply(builtin_theme('forest'))
        self.assertEqual(label.pixmap().toImage().pixelColor(12, 12).name(), '#263a2f')
        photo = QPixmap(24, 24)
        photo.fill(QColor('#ee1122'))
        label.setPixmap(photo)
        self.manager.apply(builtin_theme('rose'))
        self.assertEqual(label.pixmap().toImage().pixelColor(12, 12).name(), '#ee1122')


if __name__ == '__main__':
    unittest.main()
