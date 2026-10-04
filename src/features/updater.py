"""
features/updater.py
Core logic of update checker.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable
from urllib.parse import urlparse

import requests
import win32api

from classes.operation_result import OperationResult
from utils.app_paths import get_data_dir

GITHUB_API = "https://api.github.com/repos/evanovar/RobloxAccountManager/releases/latest"
RELEASES_PAGE = "https://github.com/evanovar/RobloxAccountManager/releases/latest"
RELEASE_ASSET_PATTERN = re.compile(
    r"^EvanovarRAM-v\d+\.\d+\.\d+(?:\.\d+)?\.exe$",
    re.IGNORECASE,
)
LEGACY_ASSET_NAMES = (
    "EvanovarRAM.exe",
    "RobloxAccountManager.exe",
)
DOWNLOAD_HOST = "github.com"
MAX_NOTES_LENGTH = 6000
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


def get_latest_release() -> OperationResult:
    try:
        response = requests.get(GITHUB_API, timeout=8)
    except requests.RequestException as exc:
        return OperationResult.failure(
            "UPDATE_CHECK_FAILED",
            "Update Check Failed",
            "GitHub could not be reached. Check your connection and try again.",
            detail=f"{type(exc).__name__}: {exc}",
            retryable=True,
        )
    if response.status_code != 200:
        return OperationResult.failure(
            "UPDATE_CHECK_FAILED",
            "Update Check Failed",
            "GitHub did not return the latest release.",
            detail=f"HTTP {response.status_code}",
            retryable=response.status_code >= 500 or response.status_code == 429,
        )
    try:
        release = response.json()
        version = str(release.get("tag_name", "")).lstrip("v").strip()
    except (ValueError, AttributeError):
        version = ""
    if not version:
        return OperationResult.failure(
            "UPDATE_CHECK_FAILED",
            "Update Check Failed",
            "GitHub returned a release without a version.",
        )
    return OperationResult.success(data={
        "version": version,
        "notes": str(release.get("body") or "").strip()[:MAX_NOTES_LENGTH],
        "url": str(release.get("html_url") or RELEASES_PAGE),
    })


def get_exe_asset() -> dict | None:
    try:
        response = requests.get(GITHUB_API, timeout=8)
        response.raise_for_status()
        release = response.json()
        assets = [
            asset
            for asset in release.get("assets", [])
            if str(asset.get("name", "")).lower().endswith(".exe")
            and asset.get("browser_download_url")
        ]
        release_tag = str(release.get("tag_name", "")).strip()
        if release_tag and not release_tag.lower().startswith("v"):
            release_tag = f"v{release_tag}"
        expected_name = f"EvanovarRAM-{release_tag}.exe" if release_tag else ""
        preferred = next(
            (
                asset
                for asset in assets
                if expected_name
                and asset["name"].lower() == expected_name.lower()
            ),
            None,
        )
        selected = preferred or next(
            (
                asset
                for asset in assets
                if RELEASE_ASSET_PATTERN.fullmatch(asset["name"])
            ),
            None,
        )
        selected = selected or next(
            (
                asset
                for asset in assets
                if asset["name"].lower()
                in {name.lower() for name in LEGACY_ASSET_NAMES}
            ),
            None,
        )
        if not selected:
            return None
        return {
            "url": selected["browser_download_url"],
            "name": selected["name"],
            "size": selected.get("size"),
            "digest": selected.get("digest"),
        }
    except Exception as exc:
        print(f"[ERROR] get_exe_download_url error: {exc}")
        return None


def get_exe_download_url() -> tuple[str, str] | None:
    asset = get_exe_asset()
    if not asset:
        return None
    return asset["url"], asset["name"]


def is_trusted_download_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.scheme == "https" and parsed.hostname == DOWNLOAD_HOST


def verify_download(path: str, expected_size=None, expected_digest=None) -> None:
    actual_size = os.path.getsize(path)
    if actual_size == 0:
        raise RuntimeError("The downloaded update file is empty.")
    if isinstance(expected_size, int) and expected_size > 0 and actual_size != expected_size:
        raise RuntimeError(
            f"The downloaded update is {actual_size} bytes but the release lists {expected_size}."
        )
    with open(path, "rb") as handle:
        if handle.read(2) != b"MZ":
            raise RuntimeError("The downloaded update is not a Windows executable.")
    algorithm, _, expected_hash = str(expected_digest or "").partition(":")
    if algorithm.lower() != "sha256" or not expected_hash:
        print("[WARNING] The release does not publish a SHA-256 checksum, so only the size was verified.")
        return
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected_hash.strip().lower():
        raise RuntimeError("The downloaded update does not match the checksum published for the release.")


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


def _system_powershell() -> str:
    return os.path.join(
        win32api.GetSystemDirectory(), "WindowsPowerShell", "v1.0", "powershell.exe"
    )


def _build_installer_script() -> str:
    return f'''param(
    [Parameter(Mandatory=$true)][int]$TargetProcessId,
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$DestinationPath,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [Parameter(Mandatory=$true)][string]$UpdateDirectory,
    [string]$ExpectedSha256 = "",
    [string]$LaunchArgumentsBase64 = ""
)

$ErrorActionPreference = "Stop"
$StagedPath = "$DestinationPath.new"
$BackupPath = "$DestinationPath.old"

function Write-UpdateFailure([string]$Message) {{
    try {{
        $parent = Split-Path -Parent $LogPath
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        $Message | Set-Content -LiteralPath $LogPath -Encoding UTF8
    }} catch {{
    }}
}}

function Start-Application {{
    $start = @{{
        FilePath = $DestinationPath
        WorkingDirectory = (Split-Path -Parent $DestinationPath)
    }}
    if ($LaunchArgumentsBase64) {{
        $start.ArgumentList = [System.Text.Encoding]::UTF8.GetString(
            [Convert]::FromBase64String($LaunchArgumentsBase64)
        )
    }}
    Start-Process @start | Out-Null
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
    $staged = $false
    while (-not $staged) {{
        try {{
            Copy-Item -LiteralPath $SourcePath -Destination $StagedPath -Force
            $staged = $true
        }} catch {{
            if ([DateTime]::UtcNow -ge $replaceDeadline) {{
                throw
            }}
            Start-Sleep -Milliseconds 500
        }}
    }}

    $sourceLength = (Get-Item -LiteralPath $SourcePath).Length
    if ((Get-Item -LiteralPath $StagedPath).Length -ne $sourceLength) {{
        throw "The staged executable size does not match the download."
    }}
    if ($ExpectedSha256) {{
        $stagedHash = (Get-FileHash -LiteralPath $StagedPath -Algorithm SHA256).Hash
        if ($stagedHash -ne $ExpectedSha256) {{
            throw "The staged executable does not match the published checksum."
        }}
    }}

    $swapped = $false
    while (-not $swapped) {{
        try {{
            if (Test-Path -LiteralPath $BackupPath) {{
                Remove-Item -LiteralPath $BackupPath -Force
            }}
            if (Test-Path -LiteralPath $DestinationPath) {{
                Move-Item -LiteralPath $DestinationPath -Destination $BackupPath -Force
            }}
            Move-Item -LiteralPath $StagedPath -Destination $DestinationPath -Force
            $swapped = $true
        }} catch {{
            if ((Test-Path -LiteralPath $BackupPath) -and -not (Test-Path -LiteralPath $DestinationPath)) {{
                Move-Item -LiteralPath $BackupPath -Destination $DestinationPath -Force
            }}
            if ([DateTime]::UtcNow -ge $replaceDeadline) {{
                throw
            }}
            Start-Sleep -Milliseconds 500
        }}
    }}

    Start-Application
    Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
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
    Remove-Item -LiteralPath $StagedPath -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $DestinationPath) -and (Test-Path -LiteralPath $BackupPath)) {{
        Move-Item -LiteralPath $BackupPath -Destination $DestinationPath -Force -ErrorAction SilentlyContinue
    }}
    if ((Test-Path -LiteralPath $DestinationPath) -and -not (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue)) {{
        try {{ Start-Application }} catch {{ }}
    }}
    exit 1
}}
'''


def _launch_installer(
    source_path: str,
    destination_path: str,
    update_directory: str,
    expected_sha256: str = "",
    launch_arguments: list[str] | None = None,
) -> None:
    script_path = os.path.join(update_directory, "install_update.ps1")
    log_path = _build_update_log_path()
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(_build_installer_script())

    arguments_text = subprocess.list2cmdline(list(launch_arguments or []))
    encoded_arguments = base64.b64encode(arguments_text.encode("utf-8")).decode("ascii") if arguments_text else ""

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            _system_powershell(),
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
            "-ExpectedSha256",
            expected_sha256,
            "-LaunchArgumentsBase64",
            encoded_arguments,
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
            asset = get_exe_asset()
            if not asset:
                on_done(False, "No Evanovar RAM executable was found in the latest release.")
                return

            url, filename = asset["url"], asset["name"]
            if not is_trusted_download_url(url):
                raise RuntimeError(f"The update download address is not a {DOWNLOAD_HOST} HTTPS link.")
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

            if total > 0 and not response.headers.get("content-encoding") and downloaded != total:
                raise RuntimeError("The update download was interrupted before it finished.")
            verify_download(source_path, asset.get("size"), asset.get("digest"))

            digest = str(asset.get("digest") or "")
            expected_sha256 = digest.partition(":")[2].upper() if digest.lower().startswith("sha256:") else ""
            _launch_installer(
                source_path, target, update_directory,
                expected_sha256=expected_sha256,
                launch_arguments=sys.argv[1:],
            )
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
