"""
Loading screen shown while the application starts.
"""

from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

import features.color_themes as color_themes
import features.settings_store as settings_store
from utils import motion

SPLASH_SETTING = "startup_splash"
WIDTH = 380
HEIGHT = 190
FADE_MS = 220
PROGRESS_MS = 260
SHIMMER_MS = 1300

_active: "StartupSplash | None" = None


class StartupSplash(QWidget):
    def __init__(self, version: str, colors: dict, icon_paths: list[str], animate: bool):
        super().__init__(
            None,
            Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.colors = colors
        self.version = version
        self.animate = animate
        self.status_text = "Starting"
        self.progress = 0.0
        self.target = None
        self.shimmer = 0.0
        self.setFixedSize(WIDTH, HEIGHT)
        self.setWindowTitle("Roblox Account Manager")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._icon = self._load_icon(icon_paths)
        self._progress_animation = QVariantAnimation(self)
        self._progress_animation.setDuration(PROGRESS_MS)
        self._progress_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._progress_animation.valueChanged.connect(self._on_progress)
        self._shimmer_animation = QVariantAnimation(self)
        self._shimmer_animation.setDuration(SHIMMER_MS)
        self._shimmer_animation.setStartValue(0.0)
        self._shimmer_animation.setEndValue(1.0)
        self._shimmer_animation.setLoopCount(-1)
        self._shimmer_animation.valueChanged.connect(self._on_shimmer)
        self._center()

    @staticmethod
    def _load_icon(paths: list[str]) -> QIcon | None:
        for path in paths:
            icon = QIcon(path)
            if path and not icon.isNull():
                return icon
        return None

    def _center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center().x() - WIDTH // 2, area.center().y() - HEIGHT // 2)

    def start(self) -> None:
        self.show()
        if self.animate:
            self._shimmer_animation.start()

    def set_status(self, text: str, progress: float | None) -> None:
        self.status_text = text
        self.target = None if progress is None else max(0.0, min(1.0, float(progress)))
        if self.target is not None:
            self._progress_animation.stop()
            if self.animate:
                self._progress_animation.setStartValue(self.progress)
                self._progress_animation.setEndValue(self.target)
                self._progress_animation.start()
            else:
                self.progress = self.target
        self.update()

    def _on_progress(self, value) -> None:
        self.progress = float(value)
        self.update()

    def _on_shimmer(self, value) -> None:
        self.shimmer = float(value)
        if self.target is None:
            self.update()

    def paintEvent(self, _event):
        c = self.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(c["BG"]))
        painter.setPen(QPen(QColor(c["LINE"]), 1))
        painter.drawRect(0, 0, WIDTH - 1, HEIGHT - 1)

        left = 28
        if self._icon is not None:
            self._icon.paint(painter, left, 34, 44, 44)
            left += 58
        painter.setPen(QColor(c["TEXT"]))
        painter.setFont(QFont("Segoe UI", 15, QFont.Weight.DemiBold))
        painter.drawText(left, 55, "Roblox Account Manager")
        painter.setPen(QColor(c["MUTED"]))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(left, 75, f"Version {self.version}")

        painter.setPen(QColor(c["MUTED"]))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRectF(28, 118, WIDTH - 56, 20), Qt.AlignmentFlag.AlignVCenter, self.status_text)

        track = QRectF(28, 150, WIDTH - 56, 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["LINE"]))
        painter.drawRoundedRect(track, 1.5, 1.5)
        painter.setBrush(QColor(c["ACCENT"]))
        if self.target is None:
            span = track.width() * 0.3
            start = track.left() + (track.width() + span) * self.shimmer - span
            fill = QRectF(max(track.left(), start), track.top(), 0, track.height())
            fill.setRight(min(track.right(), start + span))
            if fill.width() > 0:
                painter.drawRoundedRect(fill, 1.5, 1.5)
        else:
            painter.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * self.progress, track.height()), 1.5, 1.5)


def _enabled() -> bool:
    return bool(settings_store.get(SPLASH_SETTING, True))


def show(version: str, icon_paths: list[str] | None = None) -> bool:
    global _active
    if _active is not None or not _enabled():
        return False
    app = QApplication.instance() or QApplication(sys.argv)
    settings = settings_store.load()
    _active = StartupSplash(
        version,
        color_themes.resolve_colors(settings),
        list(icon_paths or []),
        motion.animations_enabled(settings),
    )
    _active.start()
    app.processEvents()
    return True


def is_active() -> bool:
    return _active is not None


def status(text: str, progress: float | None = None) -> None:
    if _active is None:
        return
    _active.set_status(text, progress)
    QApplication.processEvents()


def pause() -> None:
    if _active is not None:
        _active.hide()


def resume() -> None:
    if _active is not None:
        _active.show()
        QApplication.processEvents()


def dismiss() -> None:
    global _active
    splash, _active = _active, None
    if splash is not None:
        splash.hide()
        splash.deleteLater()


def reveal(window: QWidget, on_ready: Callable[[], None] | None = None) -> None:
    global _active
    splash, _active = _active, None
    if splash is None or not splash.animate:
        window.show()
        if splash is not None:
            splash.hide()
            splash.deleteLater()
        if on_ready is not None:
            QTimer.singleShot(0, window, on_ready)
        return

    window.setWindowOpacity(0.0)
    window.show()
    fade = QVariantAnimation(window)
    fade.setDuration(FADE_MS)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def step(value) -> None:
        window.setWindowOpacity(float(value))
        splash.setWindowOpacity(1.0 - float(value))

    finished = []

    def done() -> None:
        if finished:
            return
        finished.append(True)
        window.setWindowOpacity(1.0)
        splash.hide()
        splash.deleteLater()
        if on_ready is not None:
            QTimer.singleShot(0, window, on_ready)

    fade.valueChanged.connect(step)
    fade.finished.connect(done)
    fade.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    QTimer.singleShot(FADE_MS * 3, done)
