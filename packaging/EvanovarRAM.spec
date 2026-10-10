# -*- mode: python ; coding: utf-8 -*-

import _ssl
from pathlib import Path

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.winutils import get_windows_dir


PROJECT_ROOT = Path(SPECPATH).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
ASSETS_ROOT = PROJECT_ROOT / "assets"
VERSION_INFO_PATH = PROJECT_ROOT / "build" / "version_info.txt"
PYTHON_DLLS_ROOT = Path(_ssl.__file__).resolve().parent
WINDOWS_ICU_PATH = Path(get_windows_dir()) / "System32" / "icuuc.dll"

if not VERSION_INFO_PATH.is_file():
    raise FileNotFoundError("Run scripts/build.py to generate version information.")

datas = [
    (str(ASSETS_ROOT / "icon.ico"), "assets"),
    (str(ASSETS_ROOT / "discordlogo.png"), "assets"),
]
# Explicit inputs take precedence over native dependencies discovered on PATH.
binaries = [
    (str(PYTHON_DLLS_ROOT / "libssl-*.dll"), "."),
    (str(PYTHON_DLLS_ROOT / "libcrypto-*.dll"), "."),
    (str(WINDOWS_ICU_PATH), "."),
]
hiddenimports = [
    "requests",
    "Crypto",
    "win32event",
    "win32api",
    "msvcrt",
    "psutil",
    "websockets",
]

selenium_data, selenium_binaries, selenium_imports = collect_all("selenium")
datas += selenium_data
binaries += selenium_binaries
hiddenimports += selenium_imports


a = Analysis(
    [str(SOURCE_ROOT / "main.py")],
    pathex=[str(SOURCE_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.binaries = [entry for entry in a.binaries if entry[0].lower() != "icuuc.dll"]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EvanovarRAM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(VERSION_INFO_PATH),
    icon=[str(ASSETS_ROOT / "icon.ico")],
)
