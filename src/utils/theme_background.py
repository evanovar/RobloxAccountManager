from __future__ import annotations

from math import ceil
from pathlib import Path
import weakref

from PySide6.QtCore import QEvent, QObject, QRectF, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QMovie, QPainter, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene, QWidget
from shiboken6 import isValid

from features.theme_model import Background


_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff', '.ico'}
_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.avi', '.mov', '.mkv', '.m4v', '.wmv'}


class _BackgroundCanvas(QWidget):
    def __init__(self, renderer, window):
        super().__init__(window)
        self.renderer = renderer
        self.setObjectName('themeBackgroundCanvas')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setGeometry(window.rect())
        self.lower()

    def paintEvent(self, event):
        image = self.renderer._display_frame
        if image.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        source = QRectF(image.rect())
        ratio = max(self.width() / source.width(), self.height() / source.height())
        if ratio <= 0:
            return
        source.setWidth(self.width() / ratio)
        source.setHeight(self.height() / ratio)
        source.moveCenter(QRectF(image.rect()).center())
        painter.drawImage(QRectF(self.rect()), image, source)
        tint = QColor(self.renderer._tint)
        tint.setAlpha(round(self.renderer._dim * 255 / 100))
        painter.fillRect(self.rect(), tint)


class BackgroundRenderer(QObject):
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._windows = {}
        self._destroy_connections = {}
        self._active = False
        self._closed = False
        self._path = ''
        self._blur = 0
        self._dim = 0
        self._tint = '#181818'
        self._frame = QImage()
        self._display_frame = QImage()
        self._movie = None
        self._player = None
        self._sink = None
        self._pending_video_frame = None
        self._scene = None
        self._blur_item = None
        self._blur_effect = None
        self._frame_timer = QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.setInterval(33)
        self._frame_timer.timeout.connect(self._render_frame)
        if parent is not None:
            parent.destroyed.connect(self.close)

    def _check_thread(self):
        if QThread.currentThread() != self.thread():
            raise RuntimeError('Background rendering must run on its Qt thread.')

    def register(self, window):
        self._check_thread()
        if self._closed:
            return
        key = id(window)
        if key in self._windows:
            return
        canvas = _BackgroundCanvas(self, window)
        self._windows[key] = (weakref.ref(window), canvas)
        window.installEventFilter(self)
        connection = window.destroyed.connect(lambda unused=None, key=key: self._window_destroyed(key))
        self._destroy_connections[key] = connection
        if self._active:
            canvas.show()
            canvas.lower()
        self._sync_playback()

    def configure(self, background: Background):
        self._check_thread()
        if self._closed:
            return
        if not background.enabled or not background.path:
            self.stop()
            return
        path = str(Path(background.path).absolute())
        self._blur = max(0, min(100, int(background.blur)))
        self._dim = max(0, min(100, int(background.dim)))
        self._tint = background.tint
        if self._active and self._path == path:
            self._render_frame()
            return
        self.stop()
        self._path = path
        self._active = True
        if not Path(path).is_file():
            self._fail('The file does not exist. Choose another background file.')
            return
        suffix = Path(path).suffix.lower()
        if suffix not in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS | {'.gif'}:
            self._fail('This media format is unsupported. Choose an image, GIF, or video.')
            return
        for window_ref, canvas in self._windows.values():
            if isValid(canvas):
                canvas.show()
                canvas.lower()
        if suffix == '.gif':
            self._load_movie(path)
        elif suffix in _VIDEO_EXTENSIONS:
            self._load_video(path)
        else:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.width() > 1920 or size.height() > 1080:
                reader.setScaledSize(size.scaled(1920, 1080, Qt.AspectRatioMode.KeepAspectRatio))
            self._frame = reader.read()
            if self._frame.isNull():
                self._fail(f'The image could not be decoded: {reader.errorString()}')
                return
            self._render_frame()
        self._sync_playback()

    def _load_movie(self, path):
        movie = QMovie(self)
        self._movie = movie
        movie.setFileName(path)
        size = QImageReader(path).size()
        if size.width() > 1280 or size.height() > 720:
            movie.setScaledSize(size.scaled(1280, 720, Qt.AspectRatioMode.KeepAspectRatio))
        movie.frameChanged.connect(lambda unused: self._movie_frame(movie))
        movie.finished.connect(lambda: self._restart_movie(movie))
        movie.error.connect(lambda unused: self._media_error(movie, movie.lastErrorString()))
        if not movie.isValid() or not movie.jumpToFrame(0):
            self._fail('The GIF could not be decoded. Choose another background file.')

    def _load_video(self, path):
        player = QMediaPlayer(self)
        sink = QVideoSink(self)
        self._player, self._sink = player, sink
        player.setVideoSink(sink)
        player.setLoops(QMediaPlayer.Loops.Infinite)
        sink.videoFrameChanged.connect(lambda frame: self._video_frame(sink, frame))
        player.errorOccurred.connect(lambda unused, message: self._media_error(player, message))
        player.setSource(QUrl.fromLocalFile(path))

    def _media_error(self, source, message):
        if source is self._player or source is self._movie:
            self._fail(f'The media could not be decoded: {message}')

    def _fail(self, message):
        if not self._active:
            return
        path = self._path
        self.stop()
        self.failed.emit(f'Background "{Path(path).name}": {message}')

    def _movie_frame(self, movie):
        if self._active and movie is self._movie:
            self._queue_frame(movie.currentImage())

    def _restart_movie(self, movie):
        if self._active and movie is self._movie and self._has_visible_window():
            movie.start()

    def _video_frame(self, sink, frame):
        if self._active and sink is self._sink and frame.isValid():
            self._pending_video_frame = frame
            if self._display_frame.isNull():
                self._render_frame()
            elif not self._frame_timer.isActive():
                self._frame_timer.start()

    def _bounded_animation_image(self, image):
        if image.width() > 1280 or image.height() > 720:
            return image.scaled(1280, 720, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        return image

    def _queue_frame(self, image):
        if image.isNull():
            return
        self._frame = self._bounded_animation_image(image)
        if self._display_frame.isNull():
            self._render_frame()
        elif not self._frame_timer.isActive():
            self._frame_timer.start()

    def _render_frame(self):
        if not self._active:
            return
        if self._pending_video_frame is not None:
            frame = self._pending_video_frame
            self._pending_video_frame = None
            image = frame.toImage()
            if not image.isNull():
                self._frame = self._bounded_animation_image(image)
        if self._frame.isNull():
            return
        image = self._frame
        if self._blur:
            if self._scene is None:
                self._scene = QGraphicsScene(self)
                self._blur_item = QGraphicsPixmapItem()
                self._blur_effect = QGraphicsBlurEffect()
                self._blur_item.setGraphicsEffect(self._blur_effect)
                self._scene.addItem(self._blur_item)
            self._blur_effect.setBlurRadius(self._blur * 0.3)
            bounds = self._blur_effect.boundingRectFor(QRectF(image.rect()))
            # Extend edge pixels so the blur never fades into an artificial black border.
            padding = ceil(max(-bounds.left(), -bounds.top())) * 2
            padded = QImage(image.width() + padding * 2, image.height() + padding * 2,
                            QImage.Format.Format_ARGB32_Premultiplied)
            padded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(padded)
            width, height = image.width(), image.height()
            painter.drawImage(padding, padding, image)
            painter.drawImage(QRectF(padding, 0, width, padding), image, QRectF(0, 0, width, 1))
            painter.drawImage(QRectF(padding, height + padding, width, padding), image,
                              QRectF(0, height - 1, width, 1))
            painter.drawImage(QRectF(0, padding, padding, height), image, QRectF(0, 0, 1, height))
            painter.drawImage(QRectF(width + padding, padding, padding, height), image,
                              QRectF(width - 1, 0, 1, height))
            for x, y, source_x, source_y in (
                    (0, 0, 0, 0), (width + padding, 0, width - 1, 0),
                    (0, height + padding, 0, height - 1),
                    (width + padding, height + padding, width - 1, height - 1)):
                painter.fillRect(x, y, padding, padding, image.pixelColor(source_x, source_y))
            painter.end()
            self._blur_item.setPixmap(QPixmap.fromImage(padded))
            self._scene.setSceneRect(QRectF(padded.rect()))
            result = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            painter = QPainter(result)
            self._scene.render(painter, QRectF(result.rect()), QRectF(padding, padding, width, height))
            painter.end()
            self._display_frame = result
        else:
            self._display_frame = image
        for window_ref, canvas in self._windows.values():
            if isValid(canvas):
                canvas.update()

    def _has_visible_window(self):
        for window_ref, canvas in self._windows.values():
            window = window_ref()
            if window is not None and isValid(window) and window.isVisible() and not window.isMinimized():
                return True
        return False

    def _sync_playback(self):
        if not self._active:
            return
        visible = self._has_visible_window()
        if self._movie is not None:
            if visible:
                if self._movie.state() == QMovie.MovieState.NotRunning:
                    self._movie.start()
                else:
                    self._movie.setPaused(False)
            elif self._movie.state() == QMovie.MovieState.Running:
                self._movie.setPaused(True)
        if self._player is not None:
            if visible:
                self._player.play()
            else:
                self._player.pause()
        if not visible:
            self._frame_timer.stop()

    def _window_destroyed(self, key):
        self._windows.pop(key, None)
        self._destroy_connections.pop(key, None)
        self._sync_playback()

    def eventFilter(self, watched, event):
        entry = self._windows.get(id(watched))
        if entry is not None:
            canvas = entry[1]
            kind = event.type()
            if kind == QEvent.Type.Resize and isValid(canvas):
                canvas.setGeometry(watched.rect())
            if kind in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange):
                self._sync_playback()
            if kind == QEvent.Type.ChildAdded and isValid(canvas):
                canvas.lower()
        return super().eventFilter(watched, event)

    def stop(self):
        self._check_thread()
        if self._closed:
            return
        self._active = False
        self._frame_timer.stop()
        self._pending_video_frame = None
        movie, player, sink = self._movie, self._player, self._sink
        self._movie = self._player = self._sink = None
        if movie is not None:
            movie.stop()
            movie.deleteLater()
        if player is not None:
            player.stop()
            player.setVideoSink(None)
            player.setSource(QUrl())
            player.deleteLater()
        if sink is not None:
            sink.deleteLater()
        if self._scene is not None:
            self._scene.deleteLater()
            self._scene = self._blur_item = self._blur_effect = None
        self._frame = QImage()
        self._display_frame = QImage()
        self._path = ''
        for window_ref, canvas in self._windows.values():
            if isValid(canvas):
                canvas.hide()

    def close(self):
        self._check_thread()
        if self._closed:
            return
        self.stop()
        self._closed = True
        self._frame_timer.deleteLater()
        for connection in self._destroy_connections.values():
            QObject.disconnect(connection)
        self._destroy_connections.clear()
        for window_ref, canvas in self._windows.values():
            window = window_ref()
            if window is not None and isValid(window):
                window.removeEventFilter(self)
            if isValid(canvas):
                canvas.deleteLater()
        self._windows.clear()
