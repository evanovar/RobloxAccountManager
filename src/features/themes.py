import os
import re

from classes.operation_result import OperationResult
from features.account_actions import get_ui_setting, save_ui_setting


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif'}
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mkv', '.mov', '.avi'}
DEFAULT_COLORS = {'text': '#EDEDED', 'muted': '#AAAAAA',
                  'outline': '#242424', 'tint': '#181818'}


def load_background():
    data = get_ui_setting('custom_background', {})
    if not isinstance(data, dict):
        data = {}
    try:
        blur = max(0, min(100, int(data.get('blur', 50))))
    except (TypeError, ValueError):
        blur = 50
    colors = {key: data.get(key, default) for key, default in DEFAULT_COLORS.items()}
    colors = {key: value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value)
              else DEFAULT_COLORS[key] for key, value in colors.items()}
    return {
        'enabled': bool(data.get('enabled', False)),
        'path': str(data.get('path', '') or ''),
        'blur': blur,
        **colors,
    }


def validate_background(path):
    if not path or not os.path.isfile(path):
        return OperationResult.failure(
            'BACKGROUND_NOT_FOUND', 'Background Not Found',
            'Choose an existing image, GIF, or video file.', detail=path,
        )
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        return OperationResult.failure(
            'BACKGROUND_UNSUPPORTED', 'Unsupported Background',
            'Choose a PNG, JPEG, BMP, WebP, GIF, MP4, WebM, MKV, MOV, or AVI file.',
            detail=path,
        )
    return OperationResult.success()


def save_background(enabled, path, blur):
    save_ui_setting('custom_background', {
        **load_background(),
        'enabled': bool(enabled), 'path': path,
        'blur': max(0, min(100, int(blur))),
    })


def save_color(key, value):
    if key not in DEFAULT_COLORS or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        return
    data = load_background()
    data[key] = value
    save_ui_setting('custom_background', data)


def reset_background():
    data = {'enabled': False, 'path': '', 'blur': 50, **DEFAULT_COLORS}
    save_ui_setting('custom_background', data)
    return data
