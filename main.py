"""
Roblox Account Manager
Main entry point for the application.
"""

# if you find this tool helpful, consider starring the repo!

import os
import sys
import threading
import requests

from utils.ui import main as _ui_main

DATA_FOLDER = "AccountManagerData"

def _ensure_data_folder():
    os.makedirs(DATA_FOLDER, exist_ok=True)


def setup_icon() -> str | None:
    icon_path = os.path.join(DATA_FOLDER, "icon.ico")
    if os.path.exists(icon_path):
        return icon_path
    
    root_icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(root_icon):
        return root_icon
    try:
        print("[INFO] Downloading application icon...")
        url = "https://raw.githubusercontent.com/evanovar/RobloxAccountManager/main/icon.ico"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            with open(icon_path, "wb") as f:
                f.write(resp.content)
            print("[SUCCESS] Icon downloaded successfully.")
            return icon_path
        else:
            print(f"[ERROR] Failed to download icon: HTTP {resp.status_code}")
    except Exception as e:
        print(f"[ERROR] Error downloading icon: {e}")
    return None


def setup_discord_logo() -> str | None:
    logo_path = os.path.join(DATA_FOLDER, "discordlogo.png")
    if os.path.exists(logo_path):
        return logo_path
    try:
        url = (
            "https://raw.githubusercontent.com/evanovar/RobloxAccountManager"
            "/main/discordlogo.png"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            with open(logo_path, "wb") as f:
                f.write(resp.content)
            print("[INFO] Discord logo downloaded.")
            return logo_path
    except Exception as e:
        print(f"[WARNING] Discord logo download failed: {e}")
    return None

def _download_assets_async():
    threading.Thread(
        target=lambda: (setup_icon(), setup_discord_logo()),
        daemon=True,
        name="AssetDownload",
    ).start()

def main():
    _ensure_data_folder()

    icon_path = setup_icon()

    threading.Thread(target=setup_discord_logo, daemon=True, name="DiscordLogoDownload").start()

    return _ui_main(icon_path=icon_path)

if __name__ == "__main__":
    raise SystemExit(main())