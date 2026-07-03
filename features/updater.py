"""
features/updater.py
Core logic of update checker.
"""

from __future__ import annotations

import os
import re
import sys
import subprocess
import tempfile
import threading
import requests
from typing import Callable

GITHUB_API = "https://api.github.com/repos/evanovar/RobloxAccountManager/releases/latest"
RELEASES_PAGE = "https://github.com/evanovar/RobloxAccountManager/releases/latest"

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
        r = requests.get(GITHUB_API, timeout=8)
        if r.status_code == 200:
            tag = r.json().get("tag_name", "").lstrip("v")
            return tag or None
        print(f"[INFO] GitHub API status {r.status_code}")
        return None
    except Exception as exc:
        print(f"[ERROR] check_latest_version error: {exc}")
        return None


def get_exe_download_url() -> tuple[str, str] | None:
    try:
        r = requests.get(GITHUB_API, timeout=8)
        r.raise_for_status()
        for asset in r.json().get("assets", []):
            if asset["name"].lower().endswith(".exe"):
                return asset["browser_download_url"], asset["name"]
        return None
    except Exception as exc:
        print(f"[ERROR] get_exe_download_url error: {exc}")
        return None

def download_update(on_progress: Callable[[int], None], on_done: Callable[[bool, str], None],) -> None:
    def _run():
        try:
            on_progress(0)
            result = get_exe_download_url()
            if not result:
                on_done(False, "No .exe asset found in the latest release.")
                return

            url, filename = result
            print(f"[INFO] Downloading {filename} from {url}")
            on_progress(2)

            tmp_dir = tempfile.gettempdir()
            tmp_file = os.path.join(tmp_dir, filename)

            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            done = 0

            with open(tmp_file, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
                        done += len(chunk)
                        if total > 0:
                            on_progress(int(2 + (done / total) * 95))

            on_progress(100)
            print(f"[SUCCESS] Download complete: {tmp_file}")

            current_exe = sys.executable
            if current_exe.lower().endswith(("python.exe", "pythonw.exe")):
                current_exe = os.path.abspath(sys.argv[0])

            bat_path = os.path.join(tmp_dir, "ram_update.bat")
            bat = (
                "@echo off\n"
                "setlocal enabledelayedexpansion\n"
                ":wait_loop\n"
                f'copy /Y "{tmp_file}" "{current_exe}" >nul 2>&1\n'
                "if errorlevel 1 (\n"
                "    timeout /t 1 /nobreak >nul\n"
                "    goto wait_loop\n"
                ")\n"
                f'if exist "{tmp_file}" del /f /q "{tmp_file}"\n'
                'del /f /q "%~f0"\n'
            )
            with open(bat_path, "w") as fh:
                fh.write(bat)

            subprocess.Popen(
                [bat_path],
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            on_done(True, "")

        except Exception as exc:
            print(f"[ERROR] download_update error: {exc}")
            on_done(False, str(exc))

    threading.Thread(target=_run, daemon=True, name="UpdaterDownload").start()
