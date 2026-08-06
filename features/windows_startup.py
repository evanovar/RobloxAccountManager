"""
Windows Startup folder shortcut management.
"""

from __future__ import annotations

import os
import subprocess
import sys

from classes.operation_result import OperationResult, unexpected_result
from utils.app_paths import get_app_dir, get_data_dir, get_resource_path


_SHORTCUT_NAME = "Evanovar RAM.lnk"


def get_startup_folder() -> str:
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return ""
    return os.path.join(
        appdata,
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )


def get_shortcut_path() -> str:
    startup_folder = get_startup_folder()
    return os.path.join(startup_folder, _SHORTCUT_NAME) if startup_folder else ""


def is_startup_enabled() -> bool:
    shortcut_path = get_shortcut_path()
    return bool(shortcut_path and os.path.isfile(shortcut_path))


def _powershell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _get_launch_details() -> OperationResult:
    if getattr(sys, "frozen", False):
        target = os.path.abspath(sys.executable)
        arguments = ""
        working_directory = os.path.dirname(target)
    else:
        target = os.path.abspath(sys.executable)
        main_path = os.path.join(get_app_dir(), "main.py")
        arguments = f'"{main_path}"'
        working_directory = get_app_dir()

    if not os.path.isfile(target):
        return OperationResult.failure(
            "STARTUP_TARGET_MISSING",
            "Startup Target Missing",
            "The application launch target could not be found.",
            detail=f"Target: {target}",
        )

    if not getattr(sys, "frozen", False) and not os.path.isfile(arguments.strip('"')):
        return OperationResult.failure(
            "STARTUP_TARGET_MISSING",
            "Startup Target Missing",
            "The source application entry point could not be found.",
            detail=f"Entry point: {arguments}",
        )

    icon_candidates = [
        os.path.join(get_data_dir(), "icon.ico"),
        get_resource_path("icon.ico"),
    ]
    icon_path = next(
        (path for path in icon_candidates if path and os.path.isfile(path)),
        "",
    )

    return OperationResult.success(data={
        "target": target,
        "arguments": arguments,
        "working_directory": working_directory,
        "icon_path": icon_path,
    })


def _run_powershell(script: str) -> OperationResult:
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=creationflags,
        )
    except Exception as exc:
        return unexpected_result("Creating the Windows Startup shortcut", exc)

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return OperationResult.failure(
            "STARTUP_SHORTCUT_CREATE_FAILED",
            "Startup Shortcut Could Not Be Created",
            "Windows could not create the Evanovar RAM Startup shortcut.",
            detail=detail or f"PowerShell exit code: {completed.returncode}",
        )
    return OperationResult.success()


def enable_startup() -> OperationResult:
    shortcut_path = get_shortcut_path()
    startup_folder = get_startup_folder()
    if not shortcut_path or not startup_folder:
        return OperationResult.failure(
            "STARTUP_FOLDER_UNAVAILABLE",
            "Startup Folder Unavailable",
            "The current Windows user's Startup folder could not be found.",
            detail=f"APPDATA: {os.environ.get('APPDATA', '')}",
        )

    launch_result = _get_launch_details()
    if not launch_result:
        return launch_result

    try:
        os.makedirs(startup_folder, exist_ok=True)
        details = launch_result.data
        icon_location = (
            f"{details['icon_path']},0"
            if details.get("icon_path")
            else ""
        )
        script = (
            "$ErrorActionPreference = 'Stop'; "
            f"$shell = New-Object -ComObject WScript.Shell; "
            f"$shortcut = $shell.CreateShortcut({_powershell_quote(shortcut_path)}); "
            f"$shortcut.TargetPath = {_powershell_quote(details['target'])}; "
            f"$shortcut.Arguments = {_powershell_quote(details['arguments'])}; "
            f"$shortcut.WorkingDirectory = {_powershell_quote(details['working_directory'])}; "
            f"$shortcut.Description = {_powershell_quote('Start Evanovar RAM with Windows')}; "
            f"$shortcut.IconLocation = {_powershell_quote(icon_location)}; "
            "$shortcut.Save();"
        )
        result = _run_powershell(script)
        if not result:
            return result
        if not os.path.isfile(shortcut_path):
            return OperationResult.failure(
                "STARTUP_SHORTCUT_INVALID",
                "Startup Shortcut Could Not Be Verified",
                "Windows did not create the expected Startup shortcut.",
                detail=f"Shortcut: {shortcut_path}",
            )
        return OperationResult.success(
            "Evanovar RAM will start with Windows.",
            data={"shortcut_path": shortcut_path},
        )
    except Exception as exc:
        return unexpected_result("Enabling Evanovar RAM at Windows startup", exc)


def disable_startup() -> OperationResult:
    shortcut_path = get_shortcut_path()
    if not shortcut_path:
        return OperationResult.failure(
            "STARTUP_FOLDER_UNAVAILABLE",
            "Startup Folder Unavailable",
            "The current Windows user's Startup folder could not be found.",
        )

    try:
        if os.path.isfile(shortcut_path):
            os.remove(shortcut_path)
        if os.path.exists(shortcut_path):
            return OperationResult.failure(
                "STARTUP_SHORTCUT_REMOVE_FAILED",
                "Startup Shortcut Could Not Be Removed",
                "Windows did not remove the Evanovar RAM Startup shortcut.",
                detail=f"Shortcut: {shortcut_path}",
            )
        return OperationResult.success(
            "Evanovar RAM will no longer start with Windows.",
            data={"shortcut_path": shortcut_path},
        )
    except Exception as exc:
        return OperationResult.failure(
            "STARTUP_SHORTCUT_REMOVE_FAILED",
            "Startup Shortcut Could Not Be Removed",
            "The Evanovar RAM Startup shortcut could not be removed.",
            detail=f"{type(exc).__name__}: {exc}",
        )
