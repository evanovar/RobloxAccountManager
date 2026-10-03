[![Latest release](https://img.shields.io/github/v/release/evanovar/RobloxAccountManager?label=release)](https://github.com/evanovar/RobloxAccountManager/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/evanovar/RobloxAccountManager/total)](https://github.com/evanovar/RobloxAccountManager/releases)
[![License](https://img.shields.io/github/license/evanovar/RobloxAccountManager)](LICENSE)
[![Discord](https://img.shields.io/discord/1436930121897476140?label=Discord)](https://discord.gg/SZaZU8zwZA)
[![Website](https://img.shields.io/badge/website-evanovarram.com-1F58FF)](https://www.evanovarram.com/)
![OS](https://img.shields.io/badge/os-windows-0078D4)<br>
[![Download](https://img.shields.io/badge/Download-280ab?style=for-the-badge)](https://github.com/evanovar/RobloxAccountManager/releases/latest)

> [!IMPORTANT]
> Before you see this as a **"Virus"** or **"Unofficial,"** please read:
> - **Project Status:** This project was inspired by the original Roblox Account Manager by ic3w0lf22. I recreated it in Python as a personal project because I thought it would be fun to build and learn from. It is not intended to be an official continuation of the original project.<br><br>
> - **100% Open Source:** Every line of code is transparent and available for everyone. If you don't trust the .exe, you are encouraged to run the script directly from the source code.<br><br>
> - **Integrity:** The standalone .exe in the releases is compiled directly from this code with zero alterations.

# Evanovar RAM

Evanovar RAM is an open source Windows desktop application for organizing Roblox accounts, launching multiple clients, and automating common account management tasks. It combines encrypted local storage, multi-account launching, process controls, Roblox settings management, and diagnostics in one interface.

[Download the latest release](https://github.com/evanovar/RobloxAccountManager/releases/latest) | [Documentation](https://www.evanovarram.com/documentation/developer) | [Discord](https://discord.gg/SZaZU8zwZA) | [Website](https://www.evanovarram.com/)

![Evanovar RAM account manager interface](https://github.com/user-attachments/assets/6dab4d69-11fd-47d0-9348-db2aef5211fb)

## Table of contents

- [Installation](#installation)
- [Features](#features)
- [Data and privacy](#data-and-privacy)
- [Build from source](#build-from-source)
- [System changes and uninstallation](#system-changes-and-uninstallation)
- [Disclaimer](#disclaimer)
- [Contributing](#contributing)
- [Support](#support)
- [License](#license)

## Highlights

- Organize accounts with groups, notes, avatars, drag-and-drop ordering, and multi-select actions.
- Launch one or many accounts into public games, private servers, specific jobs, or small servers.
- Run multiple Roblox clients using the default mutex method or Handle64 mode.
- Monitor and recover sessions with Auto-Rejoin, Anti-AFK, activity data, and structured diagnostics.
- Manage Roblox windows with custom titles, headless mode, global grid tiling, and process controls.
- Edit Roblox settings through basic presets or a searchable advanced settings editor.
- Protect saved account data with hardware encryption or password encryption.
- Use Chrome, Firefox, Edge, or the optional portable Chromium browser for account login flows.

## Installation

### Windows executable

1. Open the [latest release](https://github.com/evanovar/RobloxAccountManager/releases/latest).
2. Download `EvanovarRAM-v<version>.exe`.
3. Place it in a folder where the application can keep its local data.
4. Run the executable.

The release executable is unsigned. Windows or antivirus software may display a reputation warning for new PyInstaller builds. Releases are built from the tagged source by the repository's GitHub Actions workflow. You can inspect the source and run it directly if preferred.

### Run from source

Requirements:

- Windows 10 or Windows 11
- [uv](https://docs.astral.sh/uv/)
- Git
- Chrome, Firefox, or Edge for browser login, unless portable Chromium is installed from the application

```powershell
git clone https://github.com/evanovar/RobloxAccountManager.git
cd RobloxAccountManager
uv sync --locked
uv run python src/main.py
```

## Features

### Account management

| Feature | Description |
| :--- | :--- |
| Browser login | Add an account through a supported browser and save it to the local account list. |
| Cookie import | Import one or multiple `.ROBLOSECURITY` cookies. |
| User and password import | Import credentials manually or from a `User:Pass` text file. Login sessions run in batches of up to five browsers. |
| Account Creator | Create up to 100 accounts in one operation with up to five browser sessions, an optional custom prefix, and an optional shared password. |
| JavaScript login | Open multiple browser sessions and run custom JavaScript for advanced login workflows. |
| Groups and notes | Organize accounts into groups and assign notes to one or multiple selected accounts. |
| Account list controls | Use avatars, drag-and-drop ordering, multi-select actions, refresh, deletion, and controlled password or cookie copying. |
| Cookie status | Detect unauthorized cookies while keeping rate limits and temporary validation failures separate from invalid accounts. |
| Activity data | Display online status, Roblox memory usage, and CPU usage beside saved accounts. |

### Game launching

| Feature | Description |
| :--- | :--- |
| Place launch | Launch one or multiple selected accounts into a Place ID. |
| Private servers | Resolve current and legacy private server links. A Place ID inside the link is used when the Place ID field is empty. |
| Join User | Resolve a username or user ID and join the user's current game when permitted. |
| Job ID | Join a specific running server by Place ID and Job ID. |
| Small Server | Find and join a server with a low player count. |
| Game favorites | Save a Place ID with its optional private server link, select it from the Place ID list, or remove it from the context menu. |
| Recent games | Save recent public and private server launches. Private entries are marked with `[P]`. |
| Launch delay | Add a configurable delay between accounts during bulk launches. |
| Launcher selection | Use Automatic, Bloxstrap, Fishstrap, Froststrap, Roblox Client, or a custom executable. |

### Multi Roblox and window management

| Feature | Description |
| :--- | :--- |
| Default Multi Roblox | Pre-create the Roblox singleton mutex before clients launch. Existing Roblox clients must be closed before enabling this mode. |
| Handle64 mode | Detect validated Roblox game processes and close their singleton handles with retry handling. Administrator access is required. |
| Error 773 protection | Lock `RobloxCookies.dat` when possible while Multi Roblox is active. |
| Rename Roblox windows | Continuously map Roblox processes to accounts and rename windows to the account username or note. |
| Window Grid | Arrange visible Roblox windows into an equal grid with a customizable global keyboard shortcut. |
| Headless Manager | List running Roblox clients and hide or show selected windows. Hidden windows are restored when the application exits. |
| Kill all Roblox processes | Close every validated Roblox game client from General settings. |
| Roblox Installer Fix | Temporarily quarantine Roblox installer executables to prevent installer popups, then restore them on exit. |
| RAM optimization | Optionally trim the working set of detected Roblox clients to a configured target. |

### Auto-Rejoin and Anti-AFK

| Feature | Description |
| :--- | :--- |
| Per-account Auto-Rejoin | Monitor configured accounts and relaunch them after a client exits or disconnects. |
| Flexible destinations | Configure a Place ID, private server, or Job ID for each Auto-Rejoin entry. |
| Process cleanup | Track account processes and close stale disconnected clients before relaunching. |
| Network handling | Wait for connectivity and stagger relaunch attempts to reduce duplicate clients. |
| Anti-AFK actions | Record a keyboard or mouse action, press count, and maintenance interval. |
| Headless support | Temporarily restore hidden Roblox windows for Anti-AFK maintenance, then return them to their previous state. |

### Roblox tools and settings

| Feature | Description |
| :--- | :--- |
| Basic Roblox settings | Enable presets for Framerate Cap, Master Volume, and Start Quality. Enabled presets apply before Roblox launches. |
| Advanced settings editor | Search and edit values from `GlobalBasicSettings_13.xml` through a local settings profile. |
| Advanced Auto Apply | Apply the saved advanced profile on application startup and before Roblox launches, with basic presets taking priority. |
| Roblox Downloader | Download the latest LIVE Windows Roblox Player deployment or a specific version hash to a chosen folder. |
| Portable Chromium | Download or reinstall the latest supported Chromium build and its matching driver. |
| Browser selection | Choose Chrome, Firefox, Edge, or portable Chromium for automated browser flows. Brave and Opera GX users can use portable Chromium. |

### Application controls and integrations

| Feature | Description |
| :--- | :--- |
| System tray | Hide the main window to the system tray, restore it from the tray icon, or exit from the tray menu. |
| Windows startup | Optionally start Evanovar RAM with Windows and add a Start Menu shortcut. |
| Update manager | Check GitHub releases on startup or manually, then download updates from the application. |
| Discord webhooks | Send selected log levels, Auto-Rejoin events, optional mentions, and periodic screenshots to a configured webhook. |
| WebSocket server | Run an optional local command server with a configurable port and encrypted password storage. Password-protected commands use `AUTH <password> | <command>`. Connections from web pages are refused unless the page origin is listed under `websocket_allowed_origins` in `AccountManagerData/ui_settings.json`. |
| Console | Review timestamped, color-coded application output and copy or clear the current console view. |
| Structured errors | Show specific error codes and technical details instead of generic failure messages. |
| Crash diagnostics | Save timestamped session and crash logs under `AccountManagerData/logs`. Error dialogs can copy the message or the full log. |

### Security and local data

| Feature | Description |
| :--- | :--- |
| Hardware encryption | Encrypt saved accounts with a key tied to the current Windows machine. No password is required at startup. |
| Password encryption | Encrypt saved accounts with a user-provided password. |
| No encryption | Store account data without encryption when explicitly selected. |
| Encryption switching | Re-encrypt saved accounts and secure settings when changing encryption methods. |
| Encryption status | Display the active hardware, password, or unencrypted state beside the account list. |
| Data removal | Wipe local application data from Settings > Misc. |

## Data and privacy

Evanovar RAM stores its persistent data in `AccountManagerData`. This includes saved accounts, settings, groups, recent games, local Roblox settings, avatar cache, and diagnostic logs.

The application does not include hidden telemetry, advertising SDKs, or analytics tracking. Network communication is limited to enabled or requested functionality:

- Roblox API requests for account, game, presence, authentication, and download features.
- GitHub requests for release and update checks.
- Connectivity checks used by Auto-Rejoin.

Account cookies and stored WebSocket passwords remain local unless the user explicitly enables a feature that sends related data elsewhere.

## Build from source

Install the locked runtime and build dependencies, then run the shared build script:

```powershell
uv sync --locked --group build
uv run --no-sync python scripts/build.py
```

The executable is written to `dist/EvanovarRAM.exe`. Build configuration lives in `packaging/EvanovarRAM.spec`, and version metadata is generated during the build. Release builds also create `dist/EvanovarRAM-v<version>.exe` for GitHub Releases.

`src/utils/version.py` is the single source of truth for the application version. Release tags must match `APP_VERSION`.

## System changes and uninstallation

Depending on enabled features, Evanovar RAM can:

- Create and update files under `AccountManagerData`.
- Register or remove Windows startup and Start Menu entries.
- Download portable Chromium, Handle64, or Roblox deployment files when requested.
- Temporarily mark Roblox settings as read-only when Advanced Auto Apply is enabled.
- Temporarily move Roblox installer files into the application quarantine folder.

To uninstall:

1. Exit the application from the window or system tray.
2. Delete the application folder or executable.
3. Delete `AccountManagerData` to remove saved accounts, settings, and logs.
4. Remove any startup or Start Menu entry that was enabled in the application.

## Disclaimer

This project is provided for educational and account management purposes. Users are responsible for complying with Roblox's Terms of Use and all applicable rules. The project maintainers are not responsible for account actions, moderation, data loss, or other consequences caused by use of the application.

## Contributing

Issues and pull requests are welcome. Keep changes focused, describe how they were tested, and avoid committing files from `AccountManagerData`.

Run the tests with `uv run --no-sync python scripts/run_tests.py --all`.
Use `--list` to see available tests, `--test <module-or-test-id>` for an individual
selection, or `--suite unit`, `--suite ui`, or `--suite integration` to choose a suite.

## Support

- [Discord community](https://discord.gg/SZaZU8zwZA)
- [Documentation](https://evanovars-roblox-account-manager.gitbook.io/evanovars-ram)
- [GitHub issues](https://github.com/evanovar/RobloxAccountManager/issues)

## License

Evanovar RAM is available under the [GNU General Public License v3.0](LICENSE).
