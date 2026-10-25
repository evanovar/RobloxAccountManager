import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QBuffer, QEvent, QIODevice, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QMovie, QPainter
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMainWindow, QWidget
from shiboken6 import isValid

from features.theme_model import Background
from utils.theme_background import BackgroundRenderer


def background(path='', enabled=True, blur=0, dim=0, tint='#181818'):
    return Background(enabled=enabled, path=str(path), blur=blur, dim=dim, tint=tint)


class UninitializedImage(QImage):
    def __init__(self, *args):
        super().__init__(*args)
        if not self.isNull():
            self.fill(QColor('#ff00ff'))


class CountedVideoFrame(QVideoFrame):
    def __init__(self, image):
        super().__init__(image)
        self.conversions = 0

    def toImage(self):
        self.conversions += 1
        return super().toImage()


def riff_chunk(name, payload):
    return name + struct.pack('<I', len(payload)) + payload + b'\0' * (len(payload) % 2)


def write_video(path):
    frames = []
    for color in ('#cc2244', '#2244cc') * 5:
        image = QImage(32, 32, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'JPEG')
        frames.append(bytes(buffer.data()))
    avih = struct.pack('<14I', 100000, 10000, 0, 16, len(frames), 0, 1, 4096, 32, 32, 0, 0, 0, 0)
    strh = struct.pack('<4s4sIHH8I4h', b'vids', b'MJPG', 0, 0, 0,
                       0, 1, 10, 0, len(frames), 4096, 0xffffffff, 0, 0, 0, 32, 32)
    strf = struct.pack('<IiiHH4sIiiII', 40, 32, 32, 1, 24, b'MJPG', 3072, 0, 0, 0, 0)
    stream = riff_chunk(b'LIST', b'strl' + riff_chunk(b'strh', strh) + riff_chunk(b'strf', strf))
    header = riff_chunk(b'LIST', b'hdrl' + riff_chunk(b'avih', avih) + stream)
    chunks = [riff_chunk(b'00dc', frame) for frame in frames]
    offset = 4
    indexes = []
    for frame, chunk in zip(frames, chunks):
        indexes.append(struct.pack('<4sIII', b'00dc', 16, offset, len(frame)))
        offset += len(chunk)
    payload = b'AVI ' + header + riff_chunk(b'LIST', b'movi' + b''.join(chunks))
    payload += riff_chunk(b'idx1', b''.join(indexes))
    path.write_bytes(riff_chunk(b'RIFF', payload))


class BackgroundRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'background.png'
        self.image = QImage(100, 100, QImage.Format.Format_RGB32)
        self.image.fill(QColor('#cc2244'))
        self.image.save(str(self.path))
        self.windows = []
        self.renderer = BackgroundRenderer()
        self.addCleanup(self.cleanup_renderer)

    def cleanup_renderer(self):
        self.renderer.close()
        for window in self.windows:
            if isValid(window):
                window.close()
                window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def window(self, kind=QWidget):
        window = kind()
        window.resize(100, 100)
        window.setStyleSheet('color: #ffffff;')
        window.show()
        self.windows.append(window)
        self.renderer.register(window)
        QTest.qWait(10)
        return window

    def pixel(self, window, x=50, y=50):
        self.app.processEvents()
        return window.grab().toImage().pixelColor(x, y)

    def wait_until(self, predicate, timeout=2000):
        for unused in range(timeout // 10):
            self.app.processEvents()
            if predicate():
                return True
            QTest.qWait(10)
        return bool(predicate())

    def test_explicit_windows_share_image_without_changing_styles(self):
        windows = [self.window(kind) for kind in (QMainWindow, QDialog, QWidget)]
        unregistered = QWidget()
        unregistered.resize(100, 100)
        unregistered.show()
        self.windows.append(unregistered)
        editor = QLineEdit(windows[0])
        editor.setStyleSheet('background: #123456; color: #eeeeee;')
        original = editor.styleSheet()
        self.renderer.configure(background(self.path))
        for window in windows:
            self.assertEqual(self.pixel(window).name(), '#cc2244')
            self.assertEqual(window.styleSheet(), 'color: #ffffff;')
        self.assertNotEqual(self.pixel(unregistered).name(), '#cc2244')
        self.assertEqual(editor.styleSheet(), original)
        self.renderer.register(windows[0])
        canvases = windows[0].findChildren(QWidget, 'themeBackgroundCanvas')
        self.assertEqual(len(canvases), 1)
        self.assertTrue(canvases[0].testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))

    def test_new_registration_and_resize_cover_entire_surface(self):
        self.renderer.configure(background(self.path))
        window = self.window()
        window.resize(250, 160)
        QTest.qWait(20)
        self.assertEqual(self.pixel(window, 249, 159).name(), '#cc2244')
        self.assertEqual(self.pixel(window, 0, 0).name(), '#cc2244')

    def test_dim_and_tint_are_independent_of_blur(self):
        window = self.window()
        self.renderer.configure(background(self.path, dim=50, tint='#000000'))
        pixel = self.pixel(window)
        self.assertAlmostEqual(pixel.red(), 102, delta=1)
        self.assertAlmostEqual(pixel.green(), 17, delta=1)
        self.renderer.configure(background(self.path, blur=100, dim=0))
        pixel = self.pixel(window)
        self.assertAlmostEqual(pixel.red(), 204, delta=2)
        self.assertAlmostEqual(pixel.green(), 34, delta=2)
        self.assertAlmostEqual(pixel.blue(), 68, delta=2)
        self.renderer.configure(background(self.path, dim=100, tint='#123456'))
        self.assertEqual(self.pixel(window).name(), '#123456')

    def test_blur_softens_whole_image_without_dimming(self):
        image = QImage(100, 100, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        for x in range(50):
            for y in range(100):
                image.setPixelColor(x, y, QColor('black'))
        image.save(str(self.path))
        window = self.window()
        self.renderer.configure(background(self.path))
        self.assertEqual(self.pixel(window, 45, 50).red(), 0)
        self.renderer.configure(background(self.path, blur=100))
        self.assertGreater(self.pixel(window, 45, 50).red(), 20)
        self.assertLess(self.pixel(window, 55, 50).red(), 235)

    def test_blur_preserves_transparent_image_background(self):
        window = self.window()
        original = self.pixel(window)
        image = QImage(100, 100, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        image.save(str(self.path))
        with patch('utils.theme_background.QImage', UninitializedImage):
            self.renderer.configure(background(self.path, blur=100))
        self.assertEqual(self.pixel(window), original)

    def test_failure_emits_once_and_keeps_existing_styles(self):
        window = self.window()
        failures = []
        self.renderer.failed.connect(failures.append)
        for filename, payload in [('missing.png', None), ('broken.png', b'broken'), ('bad.exe', b'MZ')]:
            path = Path(self.temp.name) / filename
            if payload:
                path.write_bytes(payload)
            self.renderer.configure(background(path))
            self.assertEqual(len(failures), 1)
            self.assertIn(filename, failures[0])
            self.assertEqual(window.styleSheet(), 'color: #ffffff;')
            self.assertNotEqual(self.pixel(window).name(), '#cc2244')
            failures.clear()

    def test_gif_pauses_when_all_windows_are_hidden_or_minimized(self):
        gif = Path(self.temp.name) / 'animated.gif'
        gif.write_bytes(bytes.fromhex(
            '47494638396101000100800000cc22442244cc'
            '21ff0b4e45545343415045322e300301000000'
            '21f904000a0000002c0000000001000100000202440100'
            '21f904000a0000002c00000000010001000002024c01003b'
        ))
        first, second = self.window(), self.window(QDialog)
        self.renderer.configure(background(gif))
        colors = set()
        for unused in range(12):
            QTest.qWait(40)
            colors.add(self.pixel(first).name())
        self.assertEqual(colors, {'#cc2244', '#2244cc'})
        movie = self.renderer.findChild(QMovie)
        first.hide()
        second.showMinimized()
        self.app.processEvents()
        self.assertNotEqual(movie.state(), QMovie.MovieState.Running)
        first.show()
        self.app.processEvents()
        self.assertEqual(movie.state(), QMovie.MovieState.Running)
        self.assertEqual(self.pixel(first), self.pixel(second))

    def test_video_decodes_loops_and_pauses_when_hidden(self):
        video = Path(self.temp.name) / 'sample.avi'
        write_video(video)
        window = self.window()
        failures = []
        self.renderer.failed.connect(failures.append)
        self.renderer.configure(background(video))
        self.assertTrue(self.wait_until(lambda: self.pixel(window).red() > 150), failures)
        self.assertTrue(self.wait_until(lambda: self.pixel(window).blue() > 150), failures)
        player = self.renderer.findChild(QMediaPlayer)
        positions = []
        player.positionChanged.connect(positions.append)
        self.assertTrue(self.wait_until(
            lambda: any(after < before for before, after in zip(positions, positions[1:])),
            timeout=2200,
        ))
        window.hide()
        self.app.processEvents()
        self.assertNotEqual(player.playbackState(), QMediaPlayer.PlaybackState.PlayingState)
        window.show()
        self.assertTrue(self.wait_until(lambda: player.playbackState() == QMediaPlayer.PlaybackState.PlayingState))
        self.assertEqual(failures, [])

    def test_media_preview_edits_preserve_running_decoder(self):
        video = Path(self.temp.name) / 'sample.avi'
        write_video(video)
        self.window()
        self.renderer.configure(background(video))
        player = self.renderer.findChild(QMediaPlayer)
        self.assertTrue(self.wait_until(lambda: player.position() > 100))
        position = player.position()
        self.renderer.configure(background(video, blur=40, dim=60, tint='#000000'))
        self.assertIs(self.renderer.findChild(QMediaPlayer), player)
        self.assertGreaterEqual(player.position(), position)

    def test_high_resolution_video_is_bounded_before_blur_and_keeps_cover_crop(self):
        window = self.window()
        self.renderer.configure(background(self.path, blur=100))
        sink = QVideoSink(self.renderer)
        self.renderer._sink = sink
        image = QImage(3840, 2160, QImage.Format.Format_RGB32)
        image.fill(QColor('#00ff00'))
        painter = QPainter(image)
        painter.fillRect(0, 0, 480, 2160, QColor('#ff0000'))
        painter.fillRect(3360, 0, 480, 2160, QColor('#0000ff'))
        painter.end()
        self.renderer._video_frame(sink, QVideoFrame(image))
        self.assertTrue(self.wait_until(lambda: self.pixel(window).green() > 230))
        self.assertEqual(self.renderer._frame.size().toTuple(), (1280, 720))
        self.assertEqual(self.renderer._display_frame.size().toTuple(), (1280, 720))
        self.assertGreater(self.pixel(window, 5, 50).green(), 230)
        self.assertGreater(self.pixel(window, 95, 50).green(), 230)
        window.resize(300, 100)
        self.assertGreater(self.pixel(window, 5, 50).red(), 230)
        self.assertGreater(self.pixel(window, 150, 50).green(), 230)
        self.assertGreater(self.pixel(window, 295, 50).blue(), 230)

    def test_video_converts_only_latest_pending_frame_without_restarting_deadline(self):
        window = self.window()
        self.renderer.configure(background(self.path))
        sink = QVideoSink(self.renderer)
        self.renderer._sink = sink
        frames = []
        for color in ('#ff0000', '#00ff00', '#0000ff'):
            image = QImage(100, 100, QImage.Format.Format_RGB32)
            image.fill(QColor(color))
            frames.append(CountedVideoFrame(image))
        self.renderer._video_frame(sink, frames[0])
        timer_id = self.renderer._frame_timer.timerId()
        for frame in frames[1:]:
            self.renderer._video_frame(sink, frame)
            self.assertEqual(self.renderer._frame_timer.timerId(), timer_id)
        self.assertEqual([frame.conversions for frame in frames], [0, 0, 0])
        self.assertTrue(self.wait_until(lambda: self.pixel(window).blue() > 230))
        self.assertEqual([frame.conversions for frame in frames], [0, 0, 1])
        self.renderer._video_frame(sink, frames[0])
        self.assertTrue(self.wait_until(lambda: self.pixel(window).red() > 230))
        self.assertEqual(frames[0].conversions, 1)

    def test_configured_disabled_video_path_does_not_open_decoder(self):
        video = Path(self.temp.name) / 'sample.avi'
        write_video(video)
        window = self.window()
        config = background(video, enabled=False)
        self.renderer.configure(config)
        self.assertFalse(self.renderer.findChildren(QMediaPlayer))
        self.assertFalse(self.renderer.findChildren(QVideoSink))
        self.assertFalse(self.renderer._frame_timer.isActive())
        self.assertFalse(window.findChild(QWidget, 'themeBackgroundCanvas').isVisible())
        self.assertEqual(config.path, str(video))

    def test_background_calls_from_worker_thread_are_rejected(self):
        self.window()
        failures = []

        def configure_from_worker():
            try:
                self.renderer.configure(background(self.path))
            except RuntimeError as error:
                failures.append(error)

        worker = threading.Thread(target=configure_from_worker)
        worker.start()
        worker.join()
        self.assertEqual(len(failures), 1)
        self.assertIn('Qt thread', str(failures[0]))

    def test_stop_removes_media_and_close_releases_canvases(self):
        window = self.window()
        self.renderer.configure(background(self.path))
        canvas = window.findChild(QWidget, 'themeBackgroundCanvas')
        self.renderer.stop()
        self.assertFalse(canvas.isVisible())
        self.assertNotEqual(self.pixel(window).name(), '#cc2244')
        self.renderer.configure(background(self.path))
        self.assertEqual(self.pixel(window).name(), '#cc2244')
        self.renderer.close()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(canvas))
        self.assertFalse(self.renderer.findChildren(QMediaPlayer))
        self.assertFalse(self.renderer.findChildren(QMovie))
        self.assertFalse(self.renderer.findChildren(QTimer))

    def test_corrupt_video_reports_once_and_stops_decoding(self):
        video = Path(self.temp.name) / 'broken.mp4'
        video.write_bytes(b'not a video')
        window = self.window()
        failures = []
        self.renderer.failed.connect(failures.append)
        self.renderer.configure(background(video))
        self.assertTrue(self.wait_until(lambda: bool(failures)))
        QTest.qWait(50)
        self.assertEqual(len(failures), 1)
        self.assertIn('broken.mp4', failures[0])
        self.assertEqual(window.styleSheet(), 'color: #ffffff;')
        self.assertFalse(self.renderer.findChildren(QMediaPlayer))

    def test_owner_destruction_cleans_external_window_canvas(self):
        owner = QObject()
        renderer = BackgroundRenderer(owner)
        window = self.window()
        existing = window.findChildren(QWidget, 'themeBackgroundCanvas')
        renderer.register(window)
        renderer.configure(background(self.path))
        canvases = window.findChildren(QWidget, 'themeBackgroundCanvas')
        self.assertEqual(len(canvases), 2)
        owned_canvas = next(canvas for canvas in canvases if canvas not in existing)
        owner.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(owned_canvas))

    def test_disabled_background_preserves_registration_for_next_preview(self):
        window = self.window()
        self.renderer.configure(background(self.path))
        self.renderer.configure(background(self.path, enabled=False))
        self.assertNotEqual(self.pixel(window).name(), '#cc2244')
        self.renderer.configure(background(self.path))
        self.assertEqual(self.pixel(window).name(), '#cc2244')

    def test_deleted_windows_unregister_without_stale_qt_access(self):
        window = self.window(QDialog)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.renderer.configure(background(self.path))
        canvas = window.findChild(QWidget, 'themeBackgroundCanvas')
        window.close()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(canvas))
        self.renderer.configure(background(self.path, dim=20))
        replacement = self.window(QDialog)
        self.assertNotEqual(self.pixel(replacement).name(), '#cc2244')


if __name__ == '__main__':
    unittest.main()
