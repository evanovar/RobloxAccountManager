# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all


PROJECT_ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.build import collect_ssl_binaries

SOURCE_ROOT = PROJECT_ROOT / "src"
ASSETS_ROOT = PROJECT_ROOT / "assets"
VERSION_INFO_PATH = PROJECT_ROOT / "build" / "version_info.txt"

if not VERSION_INFO_PATH.is_file():
    raise FileNotFoundError("Run scripts/build.py to generate version information.")

datas = [
    (str(ASSETS_ROOT / "icon.ico"), "assets"),
    (str(ASSETS_ROOT / "discordlogo.png"), "assets"),
]
# Explicit inputs take precedence over native dependencies discovered on PATH.
binaries = collect_ssl_binaries()
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
    upx=True,
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
