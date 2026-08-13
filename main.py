"""
Roblox Account Manager
Main entry point for the application.
"""

# if you find this tool helpful, consider starring the repo!

import ctypes
import os

from features import diagnostics
from utils.app_paths import get_data_dir, get_resource_path
from utils.version import APP_VERSION

diagnostics.install(APP_VERSION)

from features import account_actions as actions
from features import webhook
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


def _set_app_user_model_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "evanovar.robloxaccountmanager.ram"
        )
    except Exception:
        pass


def main():
    diagnostics.set_startup_stage("main startup")
    _set_app_user_model_id()
    webhook.install_console_capture(
        lambda: actions.get_ui_setting("discord_webhook", {})
    )
    diagnostics.set_startup_stage("console capture installed")
    _ensure_data_folder()
    diagnostics.set_startup_stage("data folder ready")

    icon_path = resolve_icon_path()

    try:
        exit_code = _ui_main(icon_path=icon_path)
    except Exception as exc:
        crash_path = diagnostics.report_exception(
            "Application startup or UI runtime",
            exc,
            fatal=True,
        )
        diagnostics.show_native_error(
            "Evanovar RAM Could Not Start",
            "The application encountered an unexpected error.\n\n"
            f"Crash report:\n{crash_path or diagnostics.get_session_log_path()}",
        )
        exit_code = 1

    diagnostics.shutdown(exit_code)
    return exit_code

if __name__ == "__main__":
    raise SystemExit(main())
