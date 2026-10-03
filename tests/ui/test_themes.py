import os
import base64
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMainWindow, QWidget, QMenu, QLabel, QFrame, QDoubleSpinBox, QPushButton, QComboBox
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QVideoFrame

from features import themes
from utils.ui import _BackgroundController


class BackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, 'background.png')
        image = QImage(64, 64, QImage.Format.Format_RGB32)
        image.fill(QColor('#cc2244'))
        image.save(self.path)
        self.window = QMainWindow()
        self.window.setCentralWidget(QWidget())
        self.window.resize(400, 300)
        self.original = 'QMainWindow { background: #111111; } QWidget { color: white; }'
        self.window.setStyleSheet(self.original)
        self.input = QLineEdit(self.window.centralWidget())
        self.input.setStyleSheet('background: #333333; color: #ffffff;')
        self.window.show()
        self.controller = _BackgroundController(self.window)

    def tearDown(self):
        self.controller.stop()
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def test_background_visible_and_styles_restored(self):
        original_input = self.input.styleSheet()
        self.controller.configure(True, self.path, 0)
        QTest.qWait(60)
        pixel = self.window.grab().toImage().pixelColor(250, 220)
        self.assertEqual(pixel.name(), '#cc2244')
        self.assertIn('background: transparent', self.input.styleSheet())
        clear = self.window.grab().toImage().pixelColor(50, 12)
        self.controller.set_amount(100)
        QTest.qWait(60)
        self.assertNotEqual(self.window.grab().toImage().pixelColor(50, 12), clear)
        self.assertEqual(self.window.grab().toImage().pixelColor(250, 220).name(), '#cc2244')
        self.controller.stop()
        self.assertEqual(self.window.styleSheet(), self.original)
        self.assertEqual(self.input.styleSheet(), original_input)

    def test_dynamic_style_and_deleted_dialog(self):
        self.controller.configure(True, self.path, 50)
        QTest.qWait(30)
        self.input.setStyleSheet('background: #222222; color: red;')
        dialog = QDialog(self.window)
        dialog.setStyleSheet('background: #111111; color: white;')
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        QTest.qWait(30)
        self.assertIn(dialog, self.controller.canvases)
        dialog.close()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.controller.set_amount(25)
        QTest.qWait(30)
        self.controller.stop()
        self.assertEqual(self.input.styleSheet(), 'background: #222222; color: red;')

    def test_gif_decoding_and_video_frame_rendering(self):
        gif = os.path.join(self.temp.name, 'sample.gif')
        with open(gif, 'wb') as stream:
            stream.write(base64.b64decode(
                'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
            ))
        self.controller.configure(True, gif, 0)
        QTest.qWait(120)
        self.assertTrue(self.controller.active)
        self.assertFalse(self.controller.display_frame.isNull())
        self.controller.configure(True, self.path, 0)
        self.controller._video_frame(QVideoFrame(QImage(self.path)))
        QTest.qWait(80)
        self.assertEqual(self.controller.display_frame.pixelColor(0, 0).name(), '#cc2244')

    def test_invalid_media_restores_default(self):
        errors = []
        self.controller.failed.connect(errors.append)
        self.controller.configure(True, os.path.join(self.temp.name, 'missing.png'), 50)
        self.assertFalse(self.controller.active)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.window.styleSheet(), self.original)

    def test_menu_text_and_plain_controls(self):
        spin = QDoubleSpinBox(self.window.centralWidget())
        spin.setGeometry(10, 60, 120, 30)
        spin.show()
        button = QPushButton('Kill All Roblox', self.window.centralWidget())
        button.setGeometry(10, 100, 120, 30)
        button.show()
        panel = QFrame(self.window.centralWidget())
        panel.setGeometry(150, 60, 150, 100)
        panel.setStyleSheet('QFrame { background: #333333; border: 1px solid #242424; }')
        label = QLabel('Settings', panel)
        label.setGeometry(0, 0, 100, 25)
        panel.show()
        self.controller.configure(True, self.path, 100)
        QTest.qWait(60)
        image = self.window.grab().toImage()
        self.assertEqual(image.pixelColor(240, 80).name(), '#cc2244')
        self.assertNotEqual(image.pixelColor(100, 80).name(), '#cc2244')
        self.assertNotEqual(image.pixelColor(100, 120).name(), '#cc2244')
        menu = QMenu(self.window)
        menu.addAction('Open in New Window')
        menu.popup(self.window.pos())
        QTest.qWait(60)
        self.assertNotIn(menu, self.controller.canvases)
        pixels = menu.grab().toImage()
        bright = sum(pixels.pixelColor(x, y).lightness() > 180
                     for x in range(8, pixels.width() - 8)
                     for y in range(4, pixels.height() - 4))
        self.assertGreater(bright, 20)
        menu.close()

    def test_color_customization_preserves_originals(self):
        self.input.setStyleSheet('color: #EDEDED; border: 1px solid #242424; background: #1A1A1A;')
        original = self.input.styleSheet()
        self.controller.configure(True, self.path, 50)
        self.controller.colors.update(text='#00ff00', muted='#ff00ff', outline='#ffffff', tint='#002244')
        self.controller._refresh()
        self.assertIn('color: #00ff00', self.input.styleSheet())
        self.assertIn('solid #ffffff', self.input.styleSheet())
        self.controller.stop()
        self.assertEqual(self.input.styleSheet(), original)

    def test_validation_and_settings_normalization(self):
        self.assertTrue(themes.validate_background(self.path))
        self.assertEqual(themes.validate_background('missing').code, 'BACKGROUND_NOT_FOUND')
        with patch.object(themes, 'get_ui_setting', return_value={'blur': 'invalid'}):
            self.assertEqual(themes.load_background()['blur'], 50)

    def test_composite_inputs_do_not_inherit_outer_padding(self):
        self.window.setStyleSheet(
            'QLineEdit { padding: 4px 6px; min-height: 24px; border: 1px solid #242424; }'
            'QComboBox { padding: 4px 6px; min-height: 26px; border: 1px solid #242424; }'
        )
        combo = QComboBox(self.window.centralWidget())
        combo.setEditable(True)
        combo.setGeometry(10, 50, 220, 38)
        combo.setCurrentText('129827112113663')
        combo.show()
        spin = QDoubleSpinBox(self.window.centralWidget())
        spin.setGeometry(10, 100, 120, 38)
        spin.show()
        self.controller.configure(True, self.path, 70)
        QTest.qWait(80)
        for control in (combo, spin):
            editor = control.findChild(QLineEdit)
            self.assertIn('padding: 0', editor.styleSheet())
            self.assertIn('min-height: 0', editor.styleSheet())
            self.assertLessEqual(editor.geometry().bottom(), control.height())
            self.assertGreaterEqual(editor.geometry().top(), 0)

    def test_reset_persists_original_defaults(self):
        with patch.object(themes, 'save_ui_setting') as save:
            config = themes.reset_background()
        self.assertFalse(config['enabled'])
        self.assertEqual(config['path'], '')
        self.assertEqual(config['blur'], 50)
        self.assertEqual(config['text'], '#EDEDED')
        save.assert_called_once_with('custom_background', config)
