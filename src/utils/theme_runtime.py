from __future__ import annotations

import os
import tempfile
import weakref

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPixmap, QPolygon
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMenu
from shiboken6 import isValid

from features import settings_store
from features.theme_library import ThemeLibrary
from features.theme_model import Theme, validate_theme
from utils import icons
lazy from utils.theme_background import BackgroundRenderer


STATUS_COLORS = {
    'SUCCESS': '#2ECC71', 'WARNING': '#E8A020', 'ERROR': '#EF7676',
    'DANGER_SURFACE': '#5A2A2A', 'ON_DANGER': '#FFFFFF',
    'SUCCESS_SURFACE': '#1E4D1E', 'SUCCESS_BORDER': '#2E6D2E',
}
_arrows = {}


def _arrow_path(value):
    path = _arrows.get(value)
    if path and os.path.isfile(path):
        return path
    path = os.path.join(tempfile.gettempdir(), f'ram_arrow_{value.strip("#")}.png')
    pixmap = QPixmap(10, 10)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(value))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(QPolygon([QPoint(1, 3), QPoint(9, 3), QPoint(5, 8)]))
    painter.end()
    pixmap.save(path, 'PNG')
    _arrows[value] = path.replace('\\', '/')
    return _arrows[value]


def resolve_startup_theme(settings=None):
    return ThemeLibrary().startup(settings_store.load() if settings is None else settings)


class ThemeManager(QObject):
    changed = Signal(object)
    failed = Signal(str)

    def __init__(self, app, library=None):
        super().__init__(app)
        self.app = app
        self.library = library if library is not None else ThemeLibrary()
        self.theme = self.library.startup(settings_store.load()).clone()
        self._styles = weakref.WeakKeyDictionary()
        self._icons = weakref.WeakKeyDictionary()
        self._paints = weakref.WeakSet()
        self._foregrounds = {}
        self._placeholders = weakref.WeakKeyDictionary()
        self._placeholder_cache = {}
        self._windows = weakref.WeakSet()
        self._media_available = True
        self.background = BackgroundRenderer(self)
        self.background.failed.connect(self._media_failed)
        self._closed = False
        self._apply_palette()
        self.background.configure(self.theme.background)

    @property
    def colors(self):
        return {**STATUS_COLORS, **self.theme.colors}

    def register(self, window):
        if self._closed or not isValid(window) or isinstance(window, QMenu):
            return
        if isinstance(window, (QMainWindow, QDialog)):
            self._windows.add(window)
            self.background.register(window)

    def apply(self, theme: Theme):
        if self._closed:
            return
        validate_theme(theme)
        old_background = self.theme.background
        old_colors = self.theme.colors
        self.theme = theme.clone()
        colors_changed = old_colors != self.theme.colors
        if colors_changed:
            self._apply_palette()
        if self.theme.background != old_background:
            self._media_available = True
            self.background.configure(self.theme.background)
        for widget, template in list(self._styles.items()):
            if isValid(widget):
                self._update_style(widget, template)
        if colors_changed:
            for button, (name, size) in list(self._icons.items()):
                if isValid(button):
                    icons.set_button_icon(button, name, self.colors, size)
            self._placeholder_cache.clear()
            for label, (size, previous_key) in list(self._placeholders.items()):
                if not isValid(label):
                    continue
                if label.pixmap().cacheKey() != previous_key:
                    self._placeholders.pop(label, None)
                    continue
                self.bind_placeholder(label, size)
        for widget in list(self._paints):
            if isValid(widget):
                widget.update()
        for reference, role in list(self._foregrounds.values()):
            item = reference()
            if item is not None and isValid(item):
                item.setForeground(QColor(self.colors[role]))
        for window in list(self._windows):
            if isValid(window):
                window.update()
        self.changed.emit(self.theme.clone())

    def activate(self, theme: Theme):
        self.library.activate(theme.id)
        self.apply(theme)

    def render(self, template, widget=None):
        palette = self.colors
        media = self._media_available and self.theme.background.enabled and bool(self.theme.background.path)
        opaque = isinstance(widget, QMenu) or (
            widget is not None and widget.window().windowType() == Qt.WindowType.Popup
        )
        surfaces = {'BG': 60, 'PANEL': 160, 'INPUT': 180, 'RAISED': 185,
                    'SELECT': 215, 'HOVER': 225, 'PRESSED': 225}
        result = str(template)
        for role in ('PANEL', 'SELECT', 'INPUT'):
            result = result.replace(f'@RAM_OPAQUE_{role}@', palette[role])
        if '@RAM_ARROW@' in result:
            result = result.replace('@RAM_ARROW@', _arrow_path(palette['TEXT']))
        for role, value in palette.items():
            if media and not opaque and role in surfaces:
                tint = QColor(value)
                value = f'rgba({tint.red()}, {tint.green()}, {tint.blue()}, {surfaces[role]})'
            result = result.replace(f'@RAM_{role}@', value)
        return result

    def bind_style(self, widget, template):
        if not isValid(widget):
            return
        self._styles[widget] = str(template)
        self.register(widget.window())
        self._update_style(widget, template)

    def _update_style(self, widget, template):
        rendered = self.render(template, widget)
        if widget.styleSheet() != rendered:
            widget.setStyleSheet(rendered)

    def _media_failed(self, detail):
        self._media_available = False
        for widget, template in list(self._styles.items()):
            if isValid(widget):
                self._update_style(widget, template)
        issues = getattr(self.library, 'issues', None)
        if issues is not None and detail not in issues:
            issues.append(detail)
        self.failed.emit(detail)

    def style_template(self, widget):
        return self._styles.get(widget, widget.styleSheet())

    def bind_icon(self, button, name, size=16):
        self._icons[button] = (name, size)
        icons.set_button_icon(button, name, self.colors, size)

    def bind_paint(self, widget):
        self._paints.add(widget)

    def bind_foreground(self, item, role):
        key = id(item)
        reference = weakref.ref(item, lambda unused: self._foregrounds.pop(key, None))
        self._foregrounds[key] = (reference, role)
        item.setForeground(QColor(self.colors[role]))

    def placeholder_pixmap(self, size):
        if size not in self._placeholder_cache:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(self.colors['SELECT']))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, size, size)
            painter.end()
            self._placeholder_cache[size] = pixmap
        return self._placeholder_cache[size]

    def bind_placeholder(self, label, size):
        pixmap = self.placeholder_pixmap(size)
        label.setPixmap(pixmap)
        self._placeholders[label] = (size, pixmap.cacheKey())

    def _apply_palette(self):
        c = self.colors
        p = QPalette()
        roles = {
            'Window': 'BG', 'WindowText': 'TEXT', 'Base': 'INPUT',
            'AlternateBase': 'PANEL', 'Text': 'TEXT', 'Button': 'INPUT',
            'ButtonText': 'TEXT', 'ToolTipBase': 'PANEL', 'ToolTipText': 'TEXT',
            'Highlight': 'SELECT', 'HighlightedText': 'TEXT', 'Link': 'ACCENT_TEXT',
            'PlaceholderText': 'MUTED', 'BrightText': 'ON_ACCENT',
        }
        for role, key in roles.items():
            p.setColor(getattr(QPalette.ColorRole, role), QColor(c[key]))
        for role in ('WindowText', 'Text', 'ButtonText'):
            p.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(c['MUTED']))
        self.app.setPalette(p)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.background.close()
        self._styles.clear()
        self._icons.clear()
        self._paints.clear()
        self._foregrounds.clear()
        self._placeholders.clear()
        self._placeholder_cache.clear()
        self._windows.clear()
        self.deleteLater()


def get_manager():
    app = QApplication.instance()
    if app is None:
        raise RuntimeError('Create QApplication before using the theme manager.')
    manager = getattr(app, '_ram_theme_manager', None)
    if manager is None or manager._closed:
        manager = ThemeManager(app)
        app._ram_theme_manager = manager
    return manager


def colors():
    app = QApplication.instance()
    manager = getattr(app, '_ram_theme_manager', None) if app else None
    if manager is not None and not manager._closed:
        return manager.colors
    return {**STATUS_COLORS, **resolve_startup_theme().colors}


def color(role):
    return colors()[role]


def bind_style(widget, template):
    get_manager().bind_style(widget, template)


def bind_icon(button, name, size=16):
    get_manager().bind_icon(button, name, size)


def bind_paint(widget):
    get_manager().bind_paint(widget)


def bind_foreground(item, role):
    get_manager().bind_foreground(item, role)


def bind_placeholder(label, size):
    get_manager().bind_placeholder(label, size)


def placeholder_pixmap(size):
    return get_manager().placeholder_pixmap(size)


def palette(app):
    get_manager()._apply_palette()
