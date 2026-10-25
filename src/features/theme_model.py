from __future__ import annotations

import copy
from dataclasses import dataclass, field
import uuid

from features.color_themes import (
    BASE_KEYS, DERIVED_KEYS, KEYS, PRESETS, accent_variants, is_hex_color,
    neutral_variants, resolve_colors,
)


class ThemeError(ValueError):
    pass


DEPENDENCIES = {
    'HOVER': {'INPUT', 'TEXT'},
    'PRESSED': {'INPUT', 'BG'},
    'RAISED': {'INPUT', 'TEXT'},
    'ACCENT_HOVER': {'ACCENT'},
    'ACCENT_PRESSED': {'ACCENT'},
    'ACCENT_BRIGHT': {'ACCENT'},
    'ACCENT_SOFT': {'ACCENT', 'BG'},
    'ACCENT_TEXT': {'ACCENT', 'BG'},
    'ACCENT_DEEP': {'ACCENT', 'BG'},
    'ON_ACCENT': {'ACCENT'},
}


@dataclass
class Background:
    enabled: bool = False
    path: str = ''
    blur: int = 0
    dim: int = 35
    tint: str = '#181818'


@dataclass
class Theme:
    id: str
    name: str
    colors: dict[str, str]
    background: Background
    customized: set[str]
    starting_colors: dict[str, str]
    starting_customized: set[str]
    recovery: dict[str, str] = field(default_factory=dict)
    _staging_dir: str = field(default='', repr=False, compare=False)

    def clone(self) -> Theme:
        return copy.deepcopy(self)

    def _regenerate(self, role: str) -> None:
        defaults = neutral_variants(self.colors)
        defaults.update(accent_variants(self.colors['ACCENT'], self.colors['BG']))
        for derived, dependencies in DEPENDENCIES.items():
            if role in dependencies and derived not in self.customized:
                unchanged = all(self.colors[key] == self.starting_colors[key] for key in dependencies)
                self.colors[derived] = self.starting_colors[derived] if unchanged else defaults[derived]

    def set_color(self, role: str, value: str) -> None:
        if role not in KEYS or not is_hex_color(value):
            raise ThemeError('Choose a known color role and a six-digit hexadecimal color such as #123456.')
        self.colors[role] = value.upper()
        if role in DERIVED_KEYS:
            self.customized.add(role)
        else:
            self._regenerate(role)

    def reset_color(self, role: str) -> None:
        if role not in KEYS:
            raise ThemeError('Choose a known color role to reset.')
        self.colors[role] = self.starting_colors[role]
        if role in self.starting_customized:
            self.customized.add(role)
        else:
            self.customized.discard(role)
        if role in BASE_KEYS:
            self._regenerate(role)


def builtin_theme(preset_name: str) -> Theme:
    if preset_name not in PRESETS:
        raise ThemeError('This built-in theme is unavailable. Choose another theme.')
    colors = resolve_colors({'color_theme': preset_name})
    return Theme('builtin:' + preset_name, PRESETS[preset_name]['label'], colors,
                 Background(), set(), colors.copy(), set())


def _validate_palette(colors, label: str) -> None:
    if not isinstance(colors, dict) or set(colors) != set(KEYS):
        raise ThemeError(f'The {label} must contain every supported color role.')
    if not all(is_hex_color(value) for value in colors.values()):
        raise ThemeError(f'The {label} contains an invalid color. Use six-digit hexadecimal colors.')


def _validate_customized(roles, label: str) -> None:
    if not isinstance(roles, (set, frozenset)) or not roles <= set(DERIVED_KEYS):
        raise ThemeError(f'The {label} contains an unsupported advanced color role.')


def validate_theme(theme: Theme) -> None:
    if not isinstance(theme, Theme):
        raise ThemeError('The theme document is invalid.')
    if not isinstance(theme.id, str):
        raise ThemeError('The theme ID is invalid.')
    if theme.id:
        if theme.id.startswith('builtin:'):
            if theme.id[8:] not in PRESETS:
                raise ThemeError('The built-in theme ID is unknown.')
        else:
            try:
                valid = str(uuid.UUID(theme.id)) == theme.id
            except (ValueError, AttributeError):
                valid = False
            if not valid:
                raise ThemeError('The custom theme ID must be a valid UUID.')
    if not isinstance(theme.name, str) or not 1 <= len(theme.name.strip()) <= 80:
        raise ThemeError('Enter a theme name between 1 and 80 characters.')
    _validate_palette(theme.colors, 'palette')
    _validate_palette(theme.starting_colors, 'starting palette')
    _validate_customized(theme.customized, 'customized colors')
    _validate_customized(theme.starting_customized, 'starting customized colors')
    background = theme.background
    if not isinstance(background, Background) or type(background.enabled) is not bool:
        raise ThemeError('The background settings are invalid.')
    if not isinstance(background.path, str) or '\x00' in background.path:
        raise ThemeError('The background path is invalid.')
    for name in ('blur', 'dim'):
        value = getattr(background, name)
        if type(value) is not int or not 0 <= value <= 100:
            raise ThemeError(f'Background {name} must be between 0 and 100.')
    if not is_hex_color(background.tint):
        raise ThemeError('The surface tint must be a six-digit hexadecimal color.')
    if not isinstance(theme.recovery, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in theme.recovery.items()
    ):
        raise ThemeError('The recovery information is invalid.')


def theme_to_dict(theme: Theme) -> dict:
    validate_theme(theme)
    data = {
        'format': 'ram-theme', 'version': 1, 'id': theme.id, 'name': theme.name.strip(),
        'colors': theme.colors.copy(), 'customized': sorted(theme.customized),
        'starting_colors': theme.starting_colors.copy(),
        'starting_customized': sorted(theme.starting_customized),
        'background': {'enabled': theme.background.enabled, 'path': theme.background.path,
                       'blur': theme.background.blur, 'dim': theme.background.dim,
                       'tint': theme.background.tint},
    }
    if theme.recovery:
        data['recovery'] = theme.recovery.copy()
    return data


def theme_from_dict(data: dict) -> Theme:
    if not isinstance(data, dict) or data.get('format') != 'ram-theme' or type(data.get('version')) is not int:
        raise ThemeError('Choose a valid RAM theme document.')
    if data['version'] != 1:
        raise ThemeError('This theme version is unsupported. Update RAM before importing it.')
    try:
        background = data['background']
        if not isinstance(background, dict):
            raise TypeError
        for key in ('customized', 'starting_customized'):
            if not isinstance(data[key], list) or not all(isinstance(role, str) for role in data[key]):
                raise TypeError
        theme = Theme(data.get('id', ''), data['name'], copy.deepcopy(data['colors']),
                      Background(**{key: background[key] for key in ('enabled', 'path', 'blur', 'dim', 'tint')}),
                      set(data['customized']), copy.deepcopy(data['starting_colors']),
                      set(data['starting_customized']), copy.deepcopy(data.get('recovery', {})))
    except (KeyError, TypeError) as error:
        raise ThemeError('The theme document is incomplete or contains invalid fields.') from error
    validate_theme(theme)
    theme.colors = {key: value.upper() for key, value in theme.colors.items()}
    theme.starting_colors = {key: value.upper() for key, value in theme.starting_colors.items()}
    theme.background.tint = theme.background.tint.upper()
    theme.name = theme.name.strip()
    return theme
