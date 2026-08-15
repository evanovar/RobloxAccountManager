"""
features/updater.py
Core logic of update checker.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable

import requests

from utils.app_paths import get_data_dir

GITHUB_API = "https://api.github.com/repos/evanovar/RobloxAccountManager/releases/latest"
RELEASES_PAGE = "https://github.com/evanovar/RobloxAccountManager/releases/latest"
PREFERRED_ASSET_NAME = "RobloxAccountManager.exe"
PROCESS_WAIT_SECONDS = 120
REPLACE_WAIT_SECONDS = 30

def _clean(version: str) -> str:
    """Strip alpha/beta suffixes so we compare only numeric parts."""
    return re.sub(r"(alpha|beta).*$", "", version, flags=re.IGNORECASE).strip(" .")


def _parts(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in _clean(version).split("."))
    except ValueError:
        return (0,)


def is_newer(current: str, latest: str) -> bool:
    return _parts(latest.lstrip("v")) > _parts(current.lstrip("v"))

def check_latest_version() -> str | None:
    try:
        response = requests.get(GITHUB_API, timeout=8)
        if response.status_code == 200:
            tag = response.json().get("tag_name", "").lstrip("v")
            return tag or None
        print(f"[INFO] GitHub API status {response.status_code}")
        return None
    except Exception as exc:
        print(f"[ERROR] check_latest_version error: {exc}")
        return None


def get_exe_download_url() -> tuple[str, str] | None:
    try:
        response = requests.get(GITHUB_API, timeout=8)
        response.raise_for_status()
        assets = [
            asset
            for asset in response.json().get("assets", [])
            if str(asset.get("name", "")).lower().endswith(".exe")
            and asset.get("browser_download_url")
        ]
        preferred = next(
            (
                asset
                for asset in assets
                if asset["name"].lower() == PREFERRED_ASSET_NAME.lower()
            ),
            None,
        )
        selected = preferred or next(
            (
                asset
                for asset in assets
                if "robloxaccountmanager" in asset["name"].lower()
            ),
            None,
        )
        if not selected:
            return None
        return selected["browser_download_url"], selected["name"]
    except Exception as exc:
        print(f"[ERROR] get_exe_download_url error: {exc}")
        return None


def get_update_target() -> str | None:
    if not getattr(sys, "frozen", False):
        return None
    target = os.path.abspath(sys.executable)
    if not os.path.isfile(target):
        return None
    return target


def _build_update_log_path() -> str:
    log_dir = os.path.join(get_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(log_dir, f"update-{stamp}.log")


def _build_installer_script() -> str:
    return f'''param(
    [Parameter(Mandatory=$true)][int]$TargetProcessId,
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$DestinationPath,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [Parameter(Mandatory=$true)][string]$UpdateDirectory
)

$ErrorActionPreference = "Stop"

function Write-UpdateFailure([string]$Message) {{
    try {{
        $parent = Split-Path -Parent $LogPath
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        $Message | Set-Content -LiteralPath $LogPath -Encoding UTF8
    }} catch {{
    }}
}}

try {{
    $exitDeadline = [DateTime]::UtcNow.AddSeconds({PROCESS_WAIT_SECONDS})
    while (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) {{
        if ([DateTime]::UtcNow -ge $exitDeadline) {{
            throw "The running application did not exit within {PROCESS_WAIT_SECONDS} seconds."
        }}
        Start-Sleep -Milliseconds 500
    }}

    if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {{
        throw "The downloaded update file is missing."
    }}

    $replaceDeadline = [DateTime]::UtcNow.AddSeconds({REPLACE_WAIT_SECONDS})
    $installed = $false
    while (-not $installed) {{
        try {{
            Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
            $sourceLength = (Get-Item -LiteralPath $SourcePath).Length
            $destinationLength = (Get-Item -LiteralPath $DestinationPath).Length
            if ($sourceLength -ne $destinationLength) {{
                throw "The installed executable size does not match the download."
            }}
            $installed = $true
        }} catch {{
            if ([DateTime]::UtcNow -ge $replaceDeadline) {{
                throw
            }}
            Start-Sleep -Milliseconds 500
        }}
    }}

    Remove-Item -LiteralPath $SourcePath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $UpdateDirectory -Force -ErrorAction SilentlyContinue
    exit 0
}} catch {{
    $detail = "Evanovar RAM automatic update failed.`r`n"
    $detail += "Timestamp: $([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))`r`n"
    $detail += "Destination: $DestinationPath`r`n"
    $detail += "Error: $($_.Exception.Message)"
    Write-UpdateFailure $detail
    exit 1
}}
'''


def _launch_installer(
    source_path: str,
    destination_path: str,
    update_directory: str,
) -> None:
    script_path = os.path.join(update_directory, "install_update.ps1")
    log_path = _build_update_log_path()
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(_build_installer_script())

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script_path,
            "-TargetProcessId",
            str(os.getpid()),
            "-SourcePath",
            source_path,
            "-DestinationPath",
            destination_path,
            "-LogPath",
            log_path,
            "-UpdateDirectory",
            update_directory,
        ],
        shell=False,
        creationflags=creation_flags,
    )


def download_update(
    on_progress: Callable[[int], None],
    on_done: Callable[[bool, str], None],
) -> None:
    def _run():
        update_directory = ""
        installer_started = False
        try:
            target = get_update_target()
            if not target:
                on_done(
                    False,
                    "Automatic updates are only available in the compiled application. "
                    "Use Manual Download when running from source.",
                )
                return

            on_progress(0)
            result = get_exe_download_url()
            if not result:
                on_done(False, "No Roblox Account Manager executable was found in the latest release.")
                return

            url, filename = result
            print(f"[INFO] Downloading {filename} from {url}")
            on_progress(2)

            update_directory = tempfile.mkdtemp(prefix="evanovar_ram_update_")
            source_path = os.path.join(update_directory, "update.exe")

            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(source_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        on_progress(int(2 + (downloaded / total) * 95))

            if not os.path.isfile(source_path) or os.path.getsize(source_path) == 0:
                raise RuntimeError("The downloaded update file is empty.")

            _launch_installer(source_path, target, update_directory)
            installer_started = True
            on_progress(100)
            print(
                f"[SUCCESS] Update downloaded. It will replace: {target}"
            )
            on_done(True, "")
        except Exception as exc:
            print(f"[ERROR] download_update error: {type(exc).__name__}: {exc}")
            on_done(False, str(exc))
        finally:
            if update_directory and not installer_started:
                shutil.rmtree(update_directory, ignore_errors=True)

    threading.Thread(target=_run, daemon=True, name="UpdaterDownload").start()
