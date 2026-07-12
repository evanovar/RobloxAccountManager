"""
Roblox Account Manager
Main entry point for the application.
"""

# if you find this tool helpful, consider starring the repo!

import ctypes
import os
import sys

from features import account_actions as actions
from features import webhook
from utils.app_paths import get_data_dir, get_resource_path
from utils.ui import main as _ui_main

DATA_FOLDER = get_data_dir()

def _ensure_data_folder():
    os.makedirs(DATA_FOLDER, exist_ok=True)


def resolve_icon_path() -> str | None:
    icon_path = os.path.join(DATA_FOLDER, "icon.ico")
    if os.path.exists(icon_path):
        return icon_path
    root_icon = get_resource_path("icon.ico")
    if os.path.exists(root_icon):
        return root_icon
    return None


def resolve_discord_logo_path() -> str | None:
    logo_path = os.path.join(DATA_FOLDER, "discordlogo.png")
    if os.path.exists(logo_path):
        return logo_path
    bundled_logo = get_resource_path("discordlogo.png")
    if os.path.exists(bundled_logo):
        return bundled_logo
    return None

def _set_app_user_model_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "evanovar.robloxaccountmanager.ram"
        )
    except Exception:
        pass


def main():
    _set_app_user_model_id()
    webhook.install_console_capture(lambda: actions.load_ui_settings().get("discord_webhook", {}))
    _ensure_data_folder()

    icon_path = resolve_icon_path()
    resolve_discord_logo_path()

    return _ui_main(icon_path=icon_path)

if __name__ == "__main__":
    raise SystemExit(main())