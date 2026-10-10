from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import win32api


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
ASSETS_ROOT = PROJECT_ROOT / "assets"
SPEC_PATH = PROJECT_ROOT / "packaging" / "EvanovarRAM.spec"
VERSION_MODULE_PATH = SOURCE_ROOT / "utils" / "version.py"
VERSION_INFO_PATH = PROJECT_ROOT / "build" / "version_info.txt"
OUTPUT_PATH = PROJECT_ROOT / "dist" / "EvanovarRAM.exe"

_VERSION_ASSIGNMENT = re.compile(
    r'^\s*APP_VERSION\s*=\s*["\']([^"\']+)["\']\s*$'
)
_VERSION_FORMAT = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")


def read_app_version() -> str:
    for line in VERSION_MODULE_PATH.read_text(encoding="utf-8").splitlines():
        match = _VERSION_ASSIGNMENT.fullmatch(line)
        if match:
            version = match.group(1)
            if not _VERSION_FORMAT.fullmatch(version):
                raise ValueError(
                    "APP_VERSION must use three or four numeric components."
                )
            return version
    raise ValueError("APP_VERSION was not found in src/utils/version.py.")


def generate_version_info(version: str) -> None:
    parts = [int(part) for part in version.split(".")]
    while len(parts) < 4:
        parts.append(0)
    version_tuple = tuple(parts[:4])
    windows_version = ".".join(str(part) for part in version_tuple)
    content = "\n".join([
        "# UTF-8",
        "VSVersionInfo(",
        "  ffi=FixedFileInfo(",
        f"    filevers={version_tuple},",
        f"    prodvers={version_tuple},",
        "    mask=0x3f,",
        "    flags=0x0,",
        "    OS=0x40004,",
        "    fileType=0x1,",
        "    subtype=0x0,",
        "    date=(0, 0)",
        "    ),",
        "  kids=[",
        "    StringFileInfo(",
        "      [",
        "      StringTable(",
        "        u'040904B0',",
        "        [StringStruct(u'CompanyName', u'evanovar'),",
        "        StringStruct(u'FileDescription', u'Evanovar RAM'),",
        f"        StringStruct(u'FileVersion', u'{windows_version}'),",
        "        StringStruct(u'InternalName', u'EvanovarRAM'),",
        "        StringStruct(u'LegalCopyright', u'Copyright (C) evanovar'),",
        "        StringStruct(u'OriginalFilename', u'EvanovarRAM.exe'),",
        "        StringStruct(u'ProductName', u'Evanovar RAM'),",
        f"        StringStruct(u'ProductVersion', u'{windows_version}')])",
        "      ]),",
        "    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])",
        "  ]",
        ")",
        "",
    ])
    VERSION_INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
    VERSION_INFO_PATH.write_text(content, encoding="utf-8")


def validate_build_files() -> None:
    required_paths = (
        SOURCE_ROOT / "main.py",
        ASSETS_ROOT / "icon.ico",
        ASSETS_ROOT / "discordlogo.png",
        SPEC_PATH,
        VERSION_MODULE_PATH,
    )
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Required build files are missing:\n" + "\n".join(missing)
        )


def validate_release_tag(version: str) -> bool:
    release_tag = os.environ.get("RAM_RELEASE_TAG", "").strip()
    if not release_tag:
        return False
    expected_tag = f"v{version}"
    if release_tag != expected_tag:
        raise ValueError(
            f"Release tag {release_tag} does not match {expected_tag}."
        )
    return True


def create_release_asset(version: str) -> Path:
    release_path = PROJECT_ROOT / "dist" / f"EvanovarRAM-v{version}.exe"
    shutil.copy2(OUTPUT_PATH, release_path)
    return release_path


def build_environment() -> dict[str, str]:
    path_overrides = {
        "PATH", "PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH", "QML_IMPORT_PATH", "QML2_IMPORT_PATH",
    }
    environment = {
        key: value for key, value in os.environ.items()
        if key.upper() not in path_overrides
    }
    # Native dependency discovery must not search unrelated host installations.
    environment["PATH"] = os.pathsep.join([
        win32api.GetSystemDirectory(),
        win32api.GetWindowsDirectory(),
        str(Path(sys.executable).parent),
        sys.base_prefix,
        str(Path(sys.base_prefix) / "DLLs"),
    ])
    return environment


def check_packaged_startup(environment: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="ram-build-check-") as data_dir:
        smoke_environment = {**environment, "QT_QPA_PLATFORM": "offscreen"}
        with subprocess.Popen(
            [str(OUTPUT_PATH), "--smoke-test", "--data-dir", data_dir],
            cwd=PROJECT_ROOT,
            env=smoke_environment,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ) as process:
            try:
                exit_code = process.wait(timeout=60)
            except subprocess.TimeoutExpired as exc:
                # A one-file build has a bootloader and child; stop both on timeout.
                subprocess.run(
                    [str(Path(win32api.GetSystemDirectory()) / "taskkill.exe"),
                     "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
                raise RuntimeError("Packaged app startup check timed out.") from exc
        if exit_code != 0:
            raise RuntimeError(f"Packaged app startup check exited with code {exit_code}.")


def main() -> int:
    try:
        validate_build_files()
        version = read_app_version()
        is_release = validate_release_tag(version)
        generate_version_info(version)
    except Exception as exc:
        print(f"[ERROR] Build preparation failed: {exc}")
        return 1

    print(f"[INFO] Building Evanovar RAM {version}")
    environment = build_environment()
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC_PATH),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        print(f"[ERROR] PyInstaller exited with code {result.returncode}.")
        return result.returncode
    if not OUTPUT_PATH.is_file():
        print(f"[ERROR] Build output was not found: {OUTPUT_PATH}")
        return 1

    print("[INFO] Checking packaged app startup")
    try:
        check_packaged_startup(environment)
    except Exception as exc:
        print(f"[ERROR] Build startup check failed: {exc}")
        return 1

    print(f"[SUCCESS] Build and startup check complete: {OUTPUT_PATH}")
    if is_release:
        try:
            release_path = create_release_asset(version)
            print(f"[SUCCESS] Release asset ready: {release_path}")
        except Exception as exc:
            print(f"[ERROR] Release asset creation failed: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
