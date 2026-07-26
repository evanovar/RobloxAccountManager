"""
features/roblox_downloader.py
Download and install Roblox WindowsPlayer deployments.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable
import zipfile

import requests


_CLIENT_VERSION_URL = (
    "https://clientsettings.roblox.com/v2/client-version/WindowsPlayer/"
)
_HOST_PATH = "https://setup-aws.rbxcdn.com"
_VERSION_PATTERN = re.compile(r"^version-[A-Za-z0-9]+$")
_PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+\.zip$")

_EXTRACT_ROOTS = {
    "RobloxApp.zip": "",
    "redist.zip": "",
    "shaders.zip": "shaders/",
    "ssl.zip": "ssl/",
    "WebView2.zip": "",
    "WebView2RuntimeInstaller.zip": "WebView2RuntimeInstaller/",
    "content-avatar.zip": "content/avatar/",
    "content-configs.zip": "content/configs/",
    "content-fonts.zip": "content/fonts/",
    "content-sky.zip": "content/sky/",
    "content-sounds.zip": "content/sounds/",
    "content-textures2.zip": "content/textures/",
    "content-models.zip": "content/models/",
    "content-platform-fonts.zip": "PlatformContent/pc/fonts/",
    "content-platform-dictionaries.zip": (
        "PlatformContent/pc/shared_compression_dictionaries/"
    ),
    "content-terrain.zip": "PlatformContent/pc/terrain/",
    "content-textures3.zip": "PlatformContent/pc/textures/",
    "extracontent-luapackages.zip": "ExtraContent/LuaPackages/",
    "extracontent-translations.zip": "ExtraContent/translations/",
    "extracontent-models.zip": "ExtraContent/models/",
    "extracontent-textures.zip": "ExtraContent/textures/",
    "extracontent-places.zip": "ExtraContent/places/",
}

_APP_SETTINGS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<Settings>\n"
    "\t<ContentFolder>content</ContentFolder>\n"
    "\t<BaseUrl>http://www.roblox.com</BaseUrl>\n"
    "</Settings>\n"
)

ProgressCallback = Callable[[int, str], None]


class RobloxDownloadError(Exception):
    pass


def get_default_versions_path() -> str:
    local_appdata = os.getenv("LOCALAPPDATA")
    if not local_appdata:
        return ""
    return str(Path(local_appdata) / "Roblox" / "Versions")


def _emit_progress(callback: ProgressCallback | None, percent: float, text: str) -> None:
    if callback:
        callback(max(0, min(100, int(percent))), text)


def _normalize_version(version: str) -> str:
    value = str(version or "").strip()
    if not value:
        raise RobloxDownloadError("Enter a Roblox version or use LIVE.")
    if not value.lower().startswith("version-"):
        value = f"version-{value}"
    value = value.lower()
    if not _VERSION_PATTERN.fullmatch(value):
        raise RobloxDownloadError("The Roblox version hash contains invalid characters.")
    return value


def _get_latest_version() -> str:
    response = requests.get(_CLIENT_VERSION_URL, timeout=15)
    response.raise_for_status()
    data = response.json()
    version = data.get("clientVersionUpload", "")
    if not version:
        raise RobloxDownloadError(
            "Roblox ClientSettings did not return clientVersionUpload."
        )
    return _normalize_version(version)


def _same_path(first: Path, second: Path) -> bool:
    try:
        return os.path.normcase(str(first.resolve())) == os.path.normcase(
            str(second.resolve())
        )
    except OSError:
        return os.path.normcase(os.path.abspath(first)) == os.path.normcase(
            os.path.abspath(second)
        )


def _remove_version_folder(path: Path, versions_root: Path) -> None:
    resolved_root = versions_root.resolve()
    resolved_path = path.resolve()
    if path.is_symlink() or resolved_path.parent != resolved_root:
        raise RobloxDownloadError(f"Refused to remove unsafe version path: {path}")
    shutil.rmtree(path)


def _clean_default_versions(versions_root: Path, keep_version: str) -> None:
    versions_root.mkdir(parents=True, exist_ok=True)
    failures = []
    for entry in versions_root.iterdir():
        if not entry.name.lower().startswith("version-") or not entry.is_dir():
            continue
        if entry.name.lower() == keep_version:
            continue
        try:
            _remove_version_folder(entry, versions_root)
            print(f"[Roblox Downloader] Removed old version: {entry.name}")
        except Exception as e:
            failures.append(f"{entry.name}: {e}")
    if failures:
        raise RobloxDownloadError(
            "Failed to remove old Roblox versions. Close Roblox and try again.\n"
            + "\n".join(failures)
        )


def _fetch_manifest(version: str) -> tuple[str, list[str]]:
    version_path = f"{_HOST_PATH}/{version}-"
    response = requests.get(f"{version_path}rbxPkgManifest.txt", timeout=30)
    if response.status_code != 200:
        version_path = f"{_HOST_PATH}/channel/common/{version}-"
        response = requests.get(f"{version_path}rbxPkgManifest.txt", timeout=30)
    if response.status_code != 200:
        raise RobloxDownloadError(
            f"Failed to fetch the Roblox package manifest (HTTP {response.status_code})."
        )

    lines = [line.strip() for line in response.text.splitlines()]
    if not lines or lines[0] != "v0":
        raise RobloxDownloadError("Roblox returned an unsupported package manifest.")
    if "RobloxApp.zip" not in lines:
        raise RobloxDownloadError("The selected version is not WindowsPlayer.")

    packages = [line for line in lines if line.endswith(".zip")]
    if not packages:
        raise RobloxDownloadError("The Roblox package manifest contains no packages.")
    for package_name in packages:
        if not _PACKAGE_PATTERN.fullmatch(package_name):
            raise RobloxDownloadError(
                f"The manifest contains an unsafe package name: {package_name}"
            )
        if package_name not in _EXTRACT_ROOTS:
            raise RobloxDownloadError(
                f"The manifest contains an unsupported package: {package_name}"
            )
    return version_path, packages


def _safe_extract(
    archive_path: Path,
    install_path: Path,
    extract_root: str,
    package_start: float,
    package_size: float,
    progress_callback: ProgressCallback | None,
    package_name: str,
) -> None:
    destination_root = (install_path / extract_root).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        total_members = max(1, len(members))
        for index, member in enumerate(members, 1):
            fixed_name = member.filename.replace("\\", "/")
            destination = (destination_root / fixed_name).resolve()
            try:
                is_safe = os.path.commonpath(
                    [str(destination_root), str(destination)]
                ) == str(destination_root)
            except ValueError:
                is_safe = False
            if not is_safe:
                raise RobloxDownloadError(
                    f"Unsafe path found inside {package_name}: {member.filename}"
                )

            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source:
                with open(destination, "wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)

            extract_fraction = index / total_members
            percent = package_start + package_size * (0.8 + extract_fraction * 0.2)
            _emit_progress(
                progress_callback,
                percent,
                f"Extracting {package_name}",
            )


def _download_packages(
    version_path: str,
    packages: list[str],
    install_path: Path,
    progress_callback: ProgressCallback | None,
) -> None:
    package_size = 96.0 / len(packages)

    with tempfile.TemporaryDirectory(prefix="ram_roblox_download_") as temp_dir:
        temp_root = Path(temp_dir)
        for index, package_name in enumerate(packages):
            package_start = 2.0 + index * package_size
            package_path = temp_root / package_name
            _emit_progress(
                progress_callback,
                package_start,
                f"Downloading {package_name}",
            )

            try:
                with requests.get(
                    f"{version_path}{package_name}",
                    stream=True,
                    timeout=(15, 120),
                ) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    with open(package_path, "wb") as package_file:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if not chunk:
                                continue
                            package_file.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                fraction = min(1.0, downloaded / total_size)
                                percent = package_start + package_size * 0.8 * fraction
                                _emit_progress(
                                    progress_callback,
                                    percent,
                                    f"Downloading {package_name}",
                                )

                _safe_extract(
                    package_path,
                    install_path,
                    _EXTRACT_ROOTS[package_name],
                    package_start,
                    package_size,
                    progress_callback,
                    package_name,
                )
            finally:
                try:
                    package_path.unlink(missing_ok=True)
                except OSError:
                    pass


def download_roblox(
    version_value: str,
    location_path: str,
    customizations_enabled: bool,
    progress_callback: ProgressCallback | None = None,
) -> tuple[bool, str, str]:
    default_path_value = get_default_versions_path()
    if not default_path_value:
        return False, "error", "LOCALAPPDATA is not available."

    default_root = Path(default_path_value)
    requested_path = str(location_path or "").strip()
    versions_root = (
        Path(os.path.expandvars(requested_path)).expanduser()
        if customizations_enabled and requested_path
        else default_root
    )
    requested_version = (
        str(version_value or "").strip()
        if customizations_enabled
        else "LIVE"
    )

    install_path = None
    remove_install_on_failure = False
    try:
        if not requested_version or requested_version.upper() == "LIVE":
            _emit_progress(progress_callback, 0, "Fetching latest version")
            version = _get_latest_version()
        else:
            version = _normalize_version(requested_version)

        versions_root.mkdir(parents=True, exist_ok=True)
        install_path = versions_root / version
        is_default_location = _same_path(versions_root, default_root)

        if is_default_location:
            _clean_default_versions(versions_root, version)

        executable = install_path / "RobloxPlayerBeta.exe"
        if executable.exists():
            _emit_progress(progress_callback, 100, "Already downloaded")
            return (
                True,
                "already_exists",
                f"{version} is already downloaded.",
            )

        if install_path.exists():
            if install_path.is_symlink():
                raise RobloxDownloadError(
                    f"Refused to replace unsafe version path: {install_path}"
                )
            shutil.rmtree(install_path)
        install_path.mkdir(parents=True, exist_ok=True)
        remove_install_on_failure = True

        _emit_progress(progress_callback, 1, "Fetching package manifest")
        version_path, packages = _fetch_manifest(version)
        print(
            f"[Roblox Downloader] Downloading {version} "
            f"with {len(packages)} packages."
        )

        (install_path / "AppSettings.xml").write_text(
            _APP_SETTINGS_XML,
            encoding="utf-8",
        )
        _download_packages(
            version_path,
            packages,
            install_path,
            progress_callback,
        )

        if not executable.exists():
            raise RobloxDownloadError(
                "Installation is incomplete. RobloxPlayerBeta.exe was not found."
            )

        _emit_progress(progress_callback, 100, "Download complete")
        print(f"[Roblox Downloader] Installed {version} to {install_path}")
        return True, "downloaded", str(install_path)
    except Exception as e:
        if remove_install_on_failure and install_path and install_path.exists():
            try:
                shutil.rmtree(install_path)
            except OSError:
                pass
        print(f"[Roblox Downloader] Download failed: {e}")
        return False, "error", str(e)
