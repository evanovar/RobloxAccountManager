"""
features/color_themes.py
Colour presets for the application and the maths for a custom accent colour.
"""

from __future__ import annotations

import re

DEFAULT_THEME = "default"
THEME_SETTING = "color_theme"
ACCENT_SETTING = "accent_color"

BASE_KEYS = ("BG", "PANEL", "INPUT", "TEXT", "MUTED", "LINE", "SELECT", "NOTE", "ACCENT")
DERIVED_KEYS = (
    "HOVER", "PRESSED", "RAISED",
    "ACCENT_HOVER", "ACCENT_PRESSED", "ACCENT_BRIGHT", "ACCENT_SOFT",
    "ACCENT_TEXT", "ACCENT_DEEP", "ON_ACCENT",
)
KEYS = BASE_KEYS + DERIVED_KEYS
DERIVED_ACCENT = frozenset({
    "ACCENT_HOVER", "ACCENT_PRESSED", "ACCENT_BRIGHT", "ACCENT_SOFT", "ACCENT_TEXT", "ACCENT_DEEP",
})

_HEX = re.compile(r"#[0-9a-fA-F]{6}")

PRESETS: dict[str, dict] = {
    "default": {
        "label": "Default",
        "BG": "#0E0E0E", "PANEL": "#151515", "INPUT": "#1A1A1A",
        "TEXT": "#EDEDED", "MUTED": "#AAAAAA", "LINE": "#242424",
        "SELECT": "#2A2A2A", "NOTE": "#D6BB7D", "ACCENT": "#0078D7",
        "explicit": {
            "HOVER": "#3A3A3A", "PRESSED": "#1E1E1E", "RAISED": "#2E2E2E",
            "ACCENT_HOVER": "#1A8FE0", "ACCENT_PRESSED": "#006DC4",
            "ACCENT_BRIGHT": "#3A7BD5", "ACCENT_SOFT": "#3A5A9A",
            "ACCENT_TEXT": "#5DBBFF", "ACCENT_DEEP": "#0A1A2A",
        },
    },
    "midnight": {
        "label": "Midnight",
        "BG": "#0B0F1A", "PANEL": "#111827", "INPUT": "#172033",
        "TEXT": "#E6EDF7", "MUTED": "#9AA7BD", "LINE": "#223049",
        "SELECT": "#1F2C47", "NOTE": "#E3C98B", "ACCENT": "#4C8DFF",
    },
    "amoled": {
        "label": "AMOLED Black",
        "BG": "#000000", "PANEL": "#080808", "INPUT": "#101010",
        "TEXT": "#F2F2F2", "MUTED": "#A0A0A0", "LINE": "#1E1E1E",
        "SELECT": "#1A1A1A", "NOTE": "#D6BB7D", "ACCENT": "#00A3FF",
    },
    "nord": {
        "label": "Nord",
        "BG": "#2E3440", "PANEL": "#343B49", "INPUT": "#3B4252",
        "TEXT": "#ECEFF4", "MUTED": "#B4BED0", "LINE": "#4C566A",
        "SELECT": "#434C5E", "NOTE": "#EBCB8B", "ACCENT": "#88C0D0",
    },
    "dracula": {
        "label": "Dracula",
        "BG": "#1E1F29", "PANEL": "#282A36", "INPUT": "#2F3142",
        "TEXT": "#F8F8F2", "MUTED": "#B4B8CC", "LINE": "#3B3E52",
        "SELECT": "#44475A", "NOTE": "#F1FA8C", "ACCENT": "#BD93F9",
    },
    "solarized": {
        "label": "Solarized Dark",
        "BG": "#002B36", "PANEL": "#073642", "INPUT": "#0B3E4B",
        "TEXT": "#EEE8D5", "MUTED": "#9CAAAA", "LINE": "#14515F",
        "SELECT": "#18505E", "NOTE": "#D9A520", "ACCENT": "#268BD2",
    },
    "forest": {
        "label": "Forest",
        "BG": "#0D1411", "PANEL": "#131D18", "INPUT": "#19261F",
        "TEXT": "#E4EFE8", "MUTED": "#9DB3A6", "LINE": "#223229",
        "SELECT": "#263A2F", "NOTE": "#D8C48A", "ACCENT": "#3FB68B",
    },
    "rose": {
        "label": "Rose",
        "BG": "#160F13", "PANEL": "#1E151A", "INPUT": "#271B22",
        "TEXT": "#F3E8EE", "MUTED": "#B79AA8", "LINE": "#36242E",
        "SELECT": "#3A2733", "NOTE": "#E6C98F", "ACCENT": "#E5557F",
    },
}


def is_hex_color(value) -> bool:
    return isinstance(value, str) and bool(_HEX.fullmatch(value))


def _to_rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _to_hex(rgb: tuple[float, float, float]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(c))) for c in rgb))


def mix(first: str, second: str, amount: float) -> str:
    a, b = _to_rgb(first), _to_rgb(second)
    return _to_hex(tuple(x + (y - x) * amount for x, y in zip(a, b)))


def luminance(color: str) -> float:
    def channel(value: int) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _readable_on(color: str, background: str, minimum: float = 4.5) -> str:
    amount = 0.45
    candidate = mix(color, "#FFFFFF", amount)
    while contrast_ratio(candidate, background) < minimum and amount < 1:
        amount = min(1.0, amount + 0.05)
        candidate = mix(color, "#FFFFFF", amount)
    return candidate


def accent_variants(accent: str, background: str) -> dict[str, str]:
    return {
        "ACCENT_HOVER": mix(accent, "#FFFFFF", 0.15),
        "ACCENT_PRESSED": mix(accent, "#000000", 0.15),
        "ACCENT_BRIGHT": mix(accent, "#FFFFFF", 0.10),
        "ACCENT_SOFT": mix(background, accent, 0.55),
        "ACCENT_TEXT": _readable_on(accent, background),
        "ACCENT_DEEP": mix(background, accent, 0.14),
        "ON_ACCENT": "#FFFFFF" if contrast_ratio(accent, "#FFFFFF") >= contrast_ratio(accent, "#101010") else "#101010",
    }


def neutral_variants(colors: dict) -> dict[str, str]:
    return {
        "HOVER": mix(colors["INPUT"], colors["TEXT"], 0.14),
        "PRESSED": mix(colors["INPUT"], colors["BG"], 0.55),
        "RAISED": mix(colors["INPUT"], colors["TEXT"], 0.07),
    }


def theme_choices() -> list[tuple[str, str]]:
    return [(key, preset["label"]) for key, preset in PRESETS.items()]


def resolve_colors(settings: dict | None = None) -> dict[str, str]:
    settings = settings if isinstance(settings, dict) else {}
    name = settings.get(THEME_SETTING)
    preset = PRESETS.get(name if isinstance(name, str) else "", PRESETS[DEFAULT_THEME])
    colors = {key: preset[key] for key in BASE_KEYS}

    accent = settings.get(ACCENT_SETTING)
    custom_accent = is_hex_color(accent)
    if custom_accent:
        colors["ACCENT"] = accent.upper()

    colors.update(neutral_variants(colors))
    colors.update(accent_variants(colors["ACCENT"], colors["BG"]))
    explicit = preset.get("explicit")
    if explicit:
        colors.update({key: value for key, value in explicit.items() if key not in DERIVED_ACCENT or not custom_accent})
    colors["ON_ACCENT"] = accent_variants(colors["ACCENT"], colors["BG"])["ON_ACCENT"]
    return colors
