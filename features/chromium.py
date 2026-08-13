"""
Chromium installation, validation, and update handling.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile

import requests

from classes.operation_result import OperationResult, unexpected_result
from utils.app_paths import get_data_dir

_CHROMIUM_ROOT = os.path.join(get_data_dir(), "Chromium")
_CHROMIUM_DIR = os.path.join(_CHROMIUM_ROOT, "chrome-win64")
_CHROMIUM_EXE = os.path.join(_CHROMIUM_DIR, "chrome.exe")
_CHROMEDRIVER_EXE = os.path.join(_CHROMIUM_DIR, "chromedriver.exe")
_SNAPSHOT_BUILD_FILE = os.path.join(_CHROMIUM_DIR, "snapshot_build.txt")
_SNAPSHOT_ROOT = "https://storage.googleapis.com/chromium-browser-snapshots/Win_x64"


class _VSFixedFileInfo(ctypes.Structure):
    _fields_ = [
        ("signature", wintypes.DWORD),
        ("struct_version", wintypes.DWORD),
        ("file_version_ms", wintypes.DWORD),
        ("file_version_ls", wintypes.DWORD),
        ("product_version_ms", wintypes.DWORD),
        ("product_version_ls", wintypes.DWORD),
        ("file_flags_mask", wintypes.DWORD),
        ("file_flags", wintypes.DWORD),
        ("file_os", wintypes.DWORD),
        ("file_type", wintypes.DWORD),
        ("file_subtype", wintypes.DWORD),
        ("file_date_ms", wintypes.DWORD),
        ("file_date_ls", wintypes.DWORD),
    ]


def get_chromium_path() -> str:
    return _CHROMIUM_EXE


def get_installed_build() -> str:
    try:
        with open(_SNAPSHOT_BUILD_FILE, "r", encoding="utf-8") as handle:
            build = handle.read().strip()
        return build if build.isdigit() else ""
    except Exception:
        return ""


def _fetch_latest_build(timeout: int = 30) -> str:
    response = requests.get(
        f"{_SNAPSHOT_ROOT}/LAST_CHANGE",
        timeout=timeout,
    )
    response.raise_for_status()
    build = response.text.strip()
    if not build.isdigit():
        raise ValueError(f"Unexpected Chromium build value: {build}")
    return build


def _is_pe_executable(path: str) -> bool:
    try:
        if os.path.getsize(path) < 4096:
            return False
        with open(path, "rb") as handle:
            return handle.read(2) == b"MZ"
    except Exception:
        return False


def _get_file_version(path: str) -> str:
    try:
        version_api = ctypes.WinDLL("version", use_last_error=True)
        version_api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version_api.GetFileVersionInfoSizeW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        version_api.GetFileVersionInfoW.restype = wintypes.BOOL
        version_api.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        version_api.VerQueryValueW.restype = wintypes.BOOL
        version_api.VerQueryValueW.argtypes = [
            wintypes.LPCVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.UINT),
        ]

        unused_handle = wintypes.DWORD()
        size = version_api.GetFileVersionInfoSizeW(
            path,
            ctypes.byref(unused_handle),
        )
        if not size:
            return ""

        buffer = ctypes.create_string_buffer(size)
        if not version_api.GetFileVersionInfoW(path, 0, size, buffer):
            return ""

        value = wintypes.LPVOID()
        value_size = wintypes.UINT()
        if not version_api.VerQueryValueW(
            buffer,
            "\\",
            ctypes.byref(value),
            ctypes.byref(value_size),
        ):
            return ""
        if value_size.value < ctypes.sizeof(_VSFixedFileInfo):
            return ""

        info = ctypes.cast(
            value,
            ctypes.POINTER(_VSFixedFileInfo),
        ).contents
        if info.signature != 0xFEEF04BD:
            return ""

        return ".".join(str(part) for part in (
            info.file_version_ms >> 16,
            info.file_version_ms & 0xFFFF,
            info.file_version_ls >> 16,
            info.file_version_ls & 0xFFFF,
        ))
    except Exception:
        return ""


def _run_console_version(path: str) -> str:
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (result.stdout or result.stderr or "").strip()
    except Exception:
        return ""


def validate_chromium(verify_executables: bool = False) -> OperationResult:
    if not os.path.isfile(_CHROMIUM_EXE):
        return OperationResult.failure(
            "CHROMIUM_NOT_INSTALLED",
            "Chromium Is Not Installed",
            "Download Chromium from Settings before using it for browser login.",
            detail=f"Missing executable: {_CHROMIUM_EXE}",
        )
    if not os.path.isfile(_CHROMEDRIVER_EXE):
        return OperationResult.failure(
            "BROWSER_DRIVER_MISSING",
            "Chromium Driver Missing",
            "The Chromium installation is incomplete. Download Chromium again.",
            detail=f"Missing driver: {_CHROMEDRIVER_EXE}",
        )
    if not _is_pe_executable(_CHROMIUM_EXE):
        return OperationResult.failure(
            "CHROMIUM_INVALID",
            "Chromium Installation Invalid",
            "The Chromium executable is incomplete or corrupted. Reinstall Chromium.",
            detail=f"Invalid executable: {_CHROMIUM_EXE}",
        )
    if not _is_pe_executable(_CHROMEDRIVER_EXE):
        return OperationResult.failure(
            "BROWSER_DRIVER_INVALID",
            "Chromium Driver Invalid",
            "The bundled ChromeDriver is incomplete or corrupted. Reinstall Chromium.",
            detail=f"Invalid driver: {_CHROMEDRIVER_EXE}",
        )

    if not verify_executables:
        return OperationResult.success(data={
            "browser_path": _CHROMIUM_EXE,
            "driver_path": _CHROMEDRIVER_EXE,
            "browser_version": "",
            "driver_version": "",
            "snapshot_build": get_installed_build(),
        })

    browser_file_version = _get_file_version(_CHROMIUM_EXE)
    installed_build = get_installed_build()
    browser_version = browser_file_version
    if not browser_version and installed_build:
        browser_version = f"Snapshot {installed_build}"
    driver_version = _run_console_version(_CHROMEDRIVER_EXE)
    if not browser_version:
        return OperationResult.failure(
            "CHROMIUM_INVALID",
            "Chromium Could Not Be Verified",
            "Chromium version information could not be read. Reinstall Chromium.",
            detail=(
                f"Executable: {_CHROMIUM_EXE}\n"
                "The browser was not launched during validation."
            ),
        )
    if not driver_version:
        return OperationResult.failure(
            "BROWSER_DRIVER_INVALID",
            "Chromium Driver Could Not Be Verified",
            "The bundled ChromeDriver could not be started. Download Chromium again.",
            detail=f"Driver: {_CHROMEDRIVER_EXE}",
        )

    browser_major = re.search(r"(\d+)\.", browser_file_version)
    driver_major = re.search(r"(\d+)\.", driver_version)
    if (
        browser_major
        and driver_major
        and browser_major.group(1) != driver_major.group(1)
    ):
        return OperationResult.failure(
            "BROWSER_DRIVER_MISMATCH",
            "Browser Driver Version Mismatch",
            "The downloaded Chromium and ChromeDriver versions do not match.",
            detail=(
                f"Chromium: {browser_version}\n"
                f"ChromeDriver: {driver_version}"
            ),
        )

    return OperationResult.success(
        data={
            "browser_path": _CHROMIUM_EXE,
            "driver_path": _CHROMEDRIVER_EXE,
            "browser_version": browser_version,
            "driver_version": driver_version,
            "snapshot_build": installed_build,
        }
    )


def check_chromium_status(on_done) -> None:
    def _worker():
        validation = validate_chromium()
        installed_build = get_installed_build()
        try:
            latest_build = _fetch_latest_build()
        except requests.Timeout as exc:
            on_done(OperationResult.failure(
                "CHROMIUM_STATUS_TIMEOUT",
                "Chromium Check Timed Out",
                "The latest Chromium version could not be checked.",
                detail=str(exc),
                retryable=True,
            ))
            return
        except requests.RequestException as exc:
            on_done(OperationResult.failure(
                "CHROMIUM_STATUS_FAILED",
                "Chromium Check Failed",
                "The latest Chromium version could not be checked.",
                detail=f"{type(exc).__name__}: {exc}",
                retryable=True,
            ))
            return
        except Exception as exc:
            on_done(unexpected_result("Checking Chromium version", exc))
            return

        on_done(OperationResult.success(data={
            "installed": bool(validation),
            "installed_build": installed_build,
            "latest_build": latest_build,
            "outdated": bool(
                validation
                and installed_build
                and installed_build != latest_build
            ),
            "validation": validation,
        }))

    threading.Thread(
        target=_worker,
        daemon=True,
        name="chromium-status",
    ).start()


def _download_file(
    url: str,
    destination: str,
    start_percent: int,
    end_percent: int,
    label: str,
    on_progress,
    timeout: int,
) -> None:
    response = requests.get(url, stream=True, timeout=timeout)
    response.raise_for_status()
    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    last_percent = start_percent

    with open(destination, "wb") as handle:
        for chunk in response.iter_content(65536):
            if not chunk:
                continue
            handle.write(chunk)
            downloaded += len(chunk)
            if total:
                span = max(1, end_percent - start_percent)
                percent = start_percent + int(downloaded / total * span)
                percent = min(end_percent, percent)
                if percent > last_percent:
                    last_percent = percent
                    on_progress(percent, label)


def _safe_extract(archive_path: str, destination: str, on_progress=None) -> None:
    destination_real = os.path.realpath(destination)
    with zipfile.ZipFile(archive_path, "r") as archive:
        members = archive.infolist()
        total = max(1, len(members))
        for index, member in enumerate(members):
            member_path = os.path.realpath(
                os.path.join(destination, member.filename)
            )
            if (
                member_path != destination_real
                and not member_path.startswith(destination_real + os.sep)
            ):
                raise ValueError(f"Unsafe archive path: {member.filename}")
            archive.extract(member, destination)
            if on_progress and index % 100 == 0:
                on_progress(index, total)


def _find_file(root: str, filename: str) -> str:
    for current_root, _, files in os.walk(root):
        if filename in files:
            return os.path.join(current_root, filename)
    return ""


def _restore_previous_install(backup_dir: str) -> None:
    if os.path.isdir(_CHROMIUM_DIR):
        shutil.rmtree(_CHROMIUM_DIR, ignore_errors=True)
    if backup_dir and os.path.isdir(backup_dir):
        os.replace(backup_dir, _CHROMIUM_DIR)


def download_chromium(on_progress, on_done) -> None:
    def _worker():
        staging_root = ""
        backup_dir = ""
        installed_new = False
        try:
            os.makedirs(_CHROMIUM_ROOT, exist_ok=True)
            staging_root = tempfile.mkdtemp(
                prefix="chromium-install-",
                dir=_CHROMIUM_ROOT,
            )

            on_progress(0, "Fetching version...")
            build = _fetch_latest_build()

            browser_zip = os.path.join(staging_root, "chromium.zip")
            driver_zip = os.path.join(staging_root, "chromedriver.zip")
            _download_file(
                f"{_SNAPSHOT_ROOT}/{build}/chrome-win.zip",
                browser_zip,
                1,
                78,
                "Downloading...",
                on_progress,
                300,
            )

            extract_root = os.path.join(staging_root, "extract")
            os.makedirs(extract_root, exist_ok=True)
            on_progress(80, "Extracting...")
            _safe_extract(
                browser_zip,
                extract_root,
                lambda index, total: on_progress(
                    80 + int(index / total * 9),
                    "Extracting...",
                ),
            )

            on_progress(90, "ChromeDriver...")
            _download_file(
                f"{_SNAPSHOT_ROOT}/{build}/chromedriver_win32.zip",
                driver_zip,
                90,
                97,
                "ChromeDriver...",
                on_progress,
                120,
            )
            driver_extract_root = os.path.join(staging_root, "driver")
            os.makedirs(driver_extract_root, exist_ok=True)
            _safe_extract(driver_zip, driver_extract_root)

            source_browser_dir = os.path.join(extract_root, "chrome-win")
            if not os.path.isdir(source_browser_dir):
                raise FileNotFoundError("chrome-win was not found in the Chromium archive.")
            source_driver = _find_file(driver_extract_root, "chromedriver.exe")
            if not source_driver:
                raise FileNotFoundError("chromedriver.exe was not found in its archive.")

            staged_install = os.path.join(staging_root, "chrome-win64")
            os.replace(source_browser_dir, staged_install)
            shutil.copy2(
                source_driver,
                os.path.join(staged_install, "chromedriver.exe"),
            )
            with open(
                os.path.join(staged_install, "snapshot_build.txt"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(build)

            if not os.path.isfile(os.path.join(staged_install, "chrome.exe")):
                raise FileNotFoundError("chrome.exe is missing from the extracted archive.")
            if not os.path.isfile(os.path.join(staged_install, "chromedriver.exe")):
                raise FileNotFoundError("chromedriver.exe is missing from the extracted archive.")

            if os.path.exists(_CHROMIUM_DIR):
                backup_dir = os.path.join(
                    _CHROMIUM_ROOT,
                    "chrome-win64.backup",
                )
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir, ignore_errors=True)
                os.replace(_CHROMIUM_DIR, backup_dir)

            os.replace(staged_install, _CHROMIUM_DIR)
            installed_new = True
            validation = validate_chromium(verify_executables=True)
            if not validation:
                _restore_previous_install(backup_dir)
                installed_new = False
                backup_dir = ""
                on_done(validation)
                return

            if backup_dir:
                shutil.rmtree(backup_dir, ignore_errors=True)
            on_progress(100, "")
            on_done(OperationResult.success(
                "Chromium was downloaded successfully.",
                data=validation.data,
            ))
        except requests.Timeout as exc:
            on_done(OperationResult.failure(
                "CHROMIUM_DOWNLOAD_TIMEOUT",
                "Chromium Download Timed Out",
                "The Chromium download timed out. Check your connection and try again.",
                detail=str(exc),
                retryable=True,
            ))
        except requests.RequestException as exc:
            on_done(OperationResult.failure(
                "CHROMIUM_DOWNLOAD_FAILED",
                "Chromium Download Failed",
                "Chromium could not be downloaded. Check your connection and try again.",
                detail=f"{type(exc).__name__}: {exc}",
                retryable=True,
            ))
        except Exception as exc:
            if installed_new or backup_dir:
                try:
                    _restore_previous_install(backup_dir)
                except Exception as restore_exc:
                    print(
                        f"[ERROR] Failed to restore previous Chromium: "
                        f"{restore_exc}"
                    )
            on_done(unexpected_result("Installing Chromium", exc))
        finally:
            if staging_root:
                shutil.rmtree(staging_root, ignore_errors=True)

    threading.Thread(
        target=_worker,
        daemon=True,
        name="chromium-download",
    ).start()
