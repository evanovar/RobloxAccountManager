"""
Small, optional animations: button hover and press feedback and page fades.

Nothing here touches a widget's stylesheet. Buttons get a transparent child
overlay that is tinted with the theme's text color, so every existing button
style keeps working.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QEasingCurve, QEvent, QObject, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QGraphicsOpacityEffect, QPushButton, QToolButton, QWidget

ANIMATIONS_SETTING = "ui_animations"
HOVER_ALPHA = 14
PRESS_ALPHA = 22
HOVER_MS = 130
PRESS_MS = 80
FADE_MS = 150
_MARKER = "_motion_attached"
_SPI_GETCLIENTAREAANIMATION = 0x1042


def system_animations_enabled() -> bool:
    try:
        flag = wintypes.BOOL(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            _SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(flag), 0,
        )
        return bool(flag.value) if ok else True
    except (AttributeError, OSError):
        return True


def animations_enabled(settings: dict | None = None) -> bool:
    settings = settings if isinstance(settings, dict) else {}
    if not bool(settings.get(ANIMATIONS_SETTING, True)):
        return False
    return system_animations_enabled()


class _Overlay(QWidget):
    def __init__(self, motion: "ButtonMotion", parent: QWidget):
        super().__init__(parent)
        self._motion = motion
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, _event):
        alpha = self._motion.current_alpha()
        if alpha <= 0:
            return
        painter = QPainter(self)
        color = QColor(self._motion.tint)
        color.setAlpha(alpha)
        painter.fillRect(self.rect(), color)


class ButtonMotion(QObject):
    def __init__(self, button: QAbstractButton, tint: str, animate: bool = True):
        super().__init__(button)
        self.button = button
        self.tint = tint
        self.animate = animate
        self.hover = 0.0
        self.press = 0.0
        self._hover_animation = self._make_animation(HOVER_MS, "hover")
        self._press_animation = self._make_animation(PRESS_MS, "press")
        self.overlay = _Overlay(self, button)
        self.overlay.setGeometry(button.rect())
        self.overlay.raise_()
        self.overlay.show()
        button.installEventFilter(self)

    def _make_animation(self, duration: int, attribute: str) -> QVariantAnimation:
        animation = QVariantAnimation(self)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(lambda value, name=attribute: self._set(name, float(value)))
        return animation

    def _set(self, attribute: str, value: float) -> None:
        setattr(self, attribute, value)
        self.overlay.update()

    def current_alpha(self) -> int:
        if not self.button.isEnabled():
            return 0
        return min(255, round(HOVER_ALPHA * self.hover + PRESS_ALPHA * self.press))

    def _go(self, attribute: str, target: float) -> None:
        animation = self._hover_animation if attribute == "hover" else self._press_animation
        animation.stop()
        if not self.animate:
            self._set(attribute, target)
            return
        animation.setStartValue(getattr(self, attribute))
        animation.setEndValue(target)
        animation.start()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.Enter:
            self._go("hover", 1.0)
        elif kind in (QEvent.Type.Leave, QEvent.Type.Hide):
            self._go("hover", 0.0)
            self._go("press", 0.0)
        elif kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._go("press", 1.0)
        elif kind == QEvent.Type.MouseButtonRelease:
            self._go("press", 0.0)
        elif kind == QEvent.Type.Resize:
            self.overlay.setGeometry(self.button.rect())
            self.overlay.raise_()
        elif kind == QEvent.Type.EnabledChange:
            self.overlay.update()
        return False


class MotionFilter(QObject):
    def __init__(self, tint: str, animate: bool = True, parent: QObject | None = None):
        super().__init__(parent)
        self.tint = tint
        self.animate = animate

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, (QPushButton, QToolButton))
            and not watched.property(_MARKER)
        ):
            watched.setProperty(_MARKER, True)
            ButtonMotion(watched, self.tint, self.animate)
        return False


def install(app, tint: str, settings: dict | None = None) -> MotionFilter | None:
    if not bool((settings or {}).get(ANIMATIONS_SETTING, True)):
        return None
    motion_filter = MotionFilter(tint, animate=animations_enabled(settings), parent=app)
    app.installEventFilter(motion_filter)
    return motion_filter


def fade_in(widget: QWidget, duration: int = FADE_MS, enabled: bool = True) -> QVariantAnimation | None:
    if not enabled or widget is None or not widget.isVisible():
        return None
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    animation = QVariantAnimation(widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def finish() -> None:
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)

    animation.valueChanged.connect(lambda value: effect.setOpacity(float(value)))
    animation.finished.connect(finish)
    animation.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation
