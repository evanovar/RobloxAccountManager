from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


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


def collect_ssl_binaries() -> list[tuple[str, str]]:
    """Prefer this interpreter's OpenSSL DLLs over unrelated copies on PATH."""
    if sys.platform != "win32":
        return []
    import _ssl

    dll_dir = Path(_ssl.__file__).resolve().parent
    binaries = []
    for pattern in ("libssl-*.dll", "libcrypto-*.dll"):
        matches = sorted(dll_dir.glob(pattern))
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected one Python OpenSSL DLL matching {pattern} in {dll_dir}; "
                f"found {len(matches)}. Refusing to use DLLs from PATH."
            )
        binaries.append((str(matches[0]), "."))
    return binaries


def validate_frozen_runtime() -> str:
    """Exercise the actual executable before reporting a successful build."""
    import ssl

    with tempfile.TemporaryDirectory(prefix="ram-build-check-") as directory:
        report_path = Path(directory) / "runtime.json"
        result = subprocess.run(
            [str(OUTPUT_PATH), "--build-self-test", str(report_path)],
            cwd=directory, check=False, timeout=60,
        )
        if not report_path.is_file():
            raise RuntimeError(
                f"Executable did not produce a runtime report (exit {result.returncode})."
            )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if result.returncode != 0 or report.get("ok") is not True:
            raise RuntimeError(f"Executable runtime check failed: {report.get('error', report)}")
        version = report.get("openssl_version")
        if version != ssl.OPENSSL_VERSION:
            raise RuntimeError(
                f"Executable OpenSSL {version!r} differs from Python's {ssl.OPENSSL_VERSION!r}."
            )
        return version


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
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC_PATH),
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        print(f"[ERROR] PyInstaller exited with code {result.returncode}.")
        return result.returncode
    if not OUTPUT_PATH.is_file():
        print(f"[ERROR] Build output was not found: {OUTPUT_PATH}")
        return 1

    try:
        openssl_version = validate_frozen_runtime()
    except Exception as exc:
        print(f"[ERROR] Built executable validation failed: {exc}")
        return 1

    print(f"[INFO] Executable SSL check passed: {openssl_version}")
    print(f"[SUCCESS] Build complete: {OUTPUT_PATH}")
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
