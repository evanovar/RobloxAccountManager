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
> - **Release builds:** The repository's release workflow builds the executable from the source at the release tag.

# Evanovar RAM

Evanovar RAM is an open source Windows desktop application for organizing Roblox accounts, launching multiple clients, and automating common account management tasks. It combines encrypted local storage, multi-account launching, process controls, Roblox settings management, and diagnostics in one interface.

[Download the latest release](https://github.com/evanovar/RobloxAccountManager/releases/latest) | [Documentation](https://www.evanovarram.com/documentation/developer) | [Discord](https://discord.gg/SZaZU8zwZA) | [Website](https://www.evanovarram.com/)

<img width="800" height="650" alt="default" src="https://github.com/user-attachments/assets/e5728aff-92d4-4fec-ada2-2b883ea9f683" />

## Table of contents

- [Highlights](#highlights)
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
- Find games with the Games Selector and retrieve owned private server links with the Private Server Manager.
- Manage Roblox windows with custom titles, hide/show controls, global grid tiling, and process controls.
- Search and edit Roblox settings through a saved local profile with optional Auto Apply.
- Protect saved account data with hardware encryption or password encryption, and export password-protected account backups.
- Use Chrome, Firefox, Edge, or the optional portable Chromium browser for account login flows.
- Customize the interface with color themes, image/GIF/video backgrounds, and detachable pages.

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
- Python 3.15 (uv installs the required version automatically)
- [uv](https://docs.astral.sh/uv/) 0.13.0 or newer
- Git
- Chrome, Firefox, or Edge for browser login, unless portable Chromium is downloaded from the application. Cookie import does not require a browser.

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
| Browser login | Open the selected supported browser, sign in to Roblox, and save the authenticated account to the local list. |
| Cookie import | Import one or multiple `.ROBLOSECURITY` cookies. |
| User and password import | Import credentials manually or from a `User:Pass` text file. Login sessions run in batches of up to five browsers, which can be lowered to as few as one under Settings > General. |
| Account Creator | Prepare signup details for 1 to 100 accounts with up to five browser sessions. Choose generated passwords or a shared password, and optionally add a username prefix. Any CAPTCHA must be completed manually in the browser. |
| JavaScript login | Open one login browser and optionally run supplied JavaScript after the page loads. |
| Account search | Filter the list by username, note, group or user ID with the search box above the list (Ctrl+F focuses it, Esc clears it). Every word has to match. |
| Groups and notes | Create, rename, or delete groups, move accounts between them, filter by group, and assign notes to one or multiple selected accounts. |
| Account list controls | Use avatars, drag-and-drop ordering, list refresh, and account removal. Enable Ctrl/Shift multi-select under Settings > General for batch actions. |
| Copy and text export | Copy a selected account's username, saved password, or `User:Pass`, with multiple accounts selected, save the chosen contents to a text file. Cookie copying/export must be enabled under Settings > Developer. Passwords are available only when saved with the account. |
| Cookie status | Check saved cookies on startup and flag repeated unauthorized responses. Temporary failures remain unknown, and rate limiting pauses the check. Startup checking and the delay between accounts are configurable under Settings > General. |
| Avatar cache | Avatars are saved locally and downloaded again once they are 7 days old (change it under Settings > General, 0 keeps them forever). If a refresh fails the older copy is still shown, and copies for accounts that no longer exist are cleaned up. |
| Account Activity Monitor | Optionally show a status dot to the left of each avatar, plus combined local Roblox RAM and CPU usage. Updates about every 2 seconds using local processes and logs; hover the dot for details. Blue (matching memory usage text): signed-in desktop app outside a game; green: connected to a game server; yellow: running without a displayed window; red: a detected Roblox hard error. An outlined dot means all matched clients are headless. |

Enable the monitor under **Settings > Roblox > Windows > Account Activity Monitor**. Dots and metrics turn off together. A non-headless background-only client is yellow even if its log still indicates a game connection; ordinary taskbar minimization keeps its desktop/game color. For multiple clients on one account, the dot prioritizes in-game, desktop app, red status, then background. Tooltips use short labels: In Game, In Main Screen, Running in Background, or Error: followed by the error. Headless dots add (Headless). When no dot is visible, its slot has no tooltip.

Green does not require a PlaceID or JobID. Ordinary disconnects, joining, loading, teleporting, returning to the desktop app, sign-out, and observation/log-read failures do not change the last displayed color. Red requires an explicit Roblox session-failure, security-challenge, or fatal-crash marker, or a visible native error/crash dialog belonging to that client. ROBLOX_SECURITY_CHALLENGE shows red even if the main window is absent; its tooltip is Error: ROBLOX_SECURITY_CHALLENGE. Generic asset, script, and HTTP errors do not count. A hard error takes precedence over background-only status for that client. Native dialog detection recognizes standard Windows dialogs titled Error, Roblox Error, or Roblox Crash; other popups require log evidence. Until the first supported state is observed, the dot stays absent. Unidentified clients do not add dots to unrelated accounts. Initial identification can take longer than a normal scan. This monitor does not query Roblox presence on other devices or change Auto-Rejoin decisions.

### Game launching

| Feature | Description |
| :--- | :--- |
| Place launch | Launch one or multiple selected accounts into a Place ID. |
| Roblox Home | Launch the Roblox application for one or multiple selected accounts without specifying a game. |
| Games Selector | Use the search icon beside Place ID to browse popular games or search by name. Switch between thumbnail grid and list views, page through results, and apply a game's Place ID to the launch field. |
| Private servers | Resolve current and legacy private server links. A Place ID inside the link is used when the Place ID field is empty. |
| Private Server Manager | Open it from the Private Server Link dropdown to list a saved account's owned private servers, optionally filtered by Place ID. View active/inactive status, copy a join link, or apply it to the launch fields. If a link is missing, the app can request a new join code after confirmation, this replaces the current code on Roblox. |
| Join User | Enter a Roblox username and join the user's current game when Roblox returns joinable game information. |
| Job ID | Join a specific running server by Place ID and Job ID. |
| Small Server | Find and join a server with a low player count. |
| Game favorites | Save a Place ID with its optional private server link, select it from the Place ID list, or remove it from the context menu. |
| Recent games | Keep recent public and private server launches, marked with `[P]` for private entries. Double-click to fill the launch fields or remove an entry from the context menu. The history limit is configurable under Settings > General. |
| Launch controls | Optionally confirm UI launch actions and set an additional delay between accounts during bulk launches under Settings > General. |
| Launcher selection | Use Automatic, Bloxstrap, Fishstrap, Froststrap, Roblox Client, or a custom executable. |

With Multi Roblox active, a game launch is confirmed only when the matching client log reports a join as the selected account. A verification challenge, account mismatch, or unconfirmed launch pauses further launches for that Multi Roblox session, including Auto-Rejoin. Close the affected clients, address any account verification on roblox.com, then restart Multi Roblox before launching again. Roblox Home launches confirm the client window rather than a game join.

### Multi Roblox and window management

| Feature | Description |
| :--- | :--- |
| Default Multi Roblox | Pre-create the Roblox singleton mutex before clients launch. Existing Roblox clients must be closed before enabling this mode. |
| Handle64 mode | Detect validated Roblox game processes and close their singleton handles with retry handling. Administrator access and a Microsoft-signed Handle64 executable are required, the app includes a download button. Existing Roblox clients must be closed before enabling this mode. |
| Shared login protection | Block access to the shared `RobloxCookies.dat` and `appStorage.json` files while either Multi Roblox mode is active. Existing contents are preserved. Multi Roblox will not start if either file cannot be protected. |
| Rename Roblox windows | Continuously map Roblox processes to accounts and rename windows to the account username or note. |
| Window Grid | Arrange visible Roblox windows into an equal grid on the monitor under the cursor. Enable the global shortcut under Settings > Roblox, its default is Ctrl+Shift+A and it can be changed. |
| Headless Manager | List identified running Roblox clients and hide or show selected windows while the clients keep running. Hidden windows are restored on normal application exit. The scan interval (3 to 60 seconds, 10 by default) is configurable under Settings > Roblox. |
| Kill All Roblox | Use the navigation-panel button to close validated Roblox game clients after confirmation. |
| Roblox Installer Fix | Temporarily quarantine Roblox installer executables to prevent installer popups, then restore them on exit. |
| RAM working-set trimming | The optional RAM Boost worker checks clients every 15 seconds and requests working-set trimming when usage reaches the configured threshold. The value is a trigger, not an enforced memory cap. The UI marks this option as potentially causing crashes. |

While Multi Roblox protects the native files, Roblox cannot persist shared app configuration or account-picker state in `appStorage.json`. Protection lasts until Multi Roblox is disabled or RAM exits, close clients before starting another session. This protection does not bypass Roblox verification or establish which account an embedded CAPTCHA authenticates.

### Auto-Rejoin and Anti-AFK

| Feature | Description |
| :--- | :--- |
| Per-account Auto-Rejoin | Monitor configured accounts and relaunch them after a client exits or disconnects. |
| Flexible destinations | Configure a Place ID, private server, or Job ID for each Auto-Rejoin entry. |
| Join a user automatically | Configure a target username or user ID. Auto-Rejoin resolves that user's current server when launching or rejoining, and waits if the user is offline or Roblox does not expose the server. |
| Monitoring controls | Choose the check interval, maximum retries, internet checking, and whether to check account presence and the joined game. Add multiple accounts with the same configuration, edit individual entries, and start or stop one or all workers. |
| Process cleanup | Track account processes and close stale disconnected clients before relaunching. |
| Network handling | Optionally wait for connectivity and stagger presence checks and launches. Unavailable presence responses are kept separate from confirmed disconnects. |
| Anti-AFK actions | Record a keyboard or mouse action, choose the press count and interval, and send it to detected Roblox windows. Maintenance temporarily focuses each window and then attempts to restore the previous window state and focus. |
| Anti-AFK controls | Trigger maintenance immediately, enable or disable the countdown tooltip, preview it, and adjust its size. |
| Headless support | Temporarily restore hidden Roblox windows for Anti-AFK maintenance, then return them to their previous state. |

### Roblox tools and settings

| Feature | Description |
| :--- | :--- |
| Roblox settings editor | Search settings from `GlobalBasicSettings_13.xml`, inspect their types, and edit supported values through a saved local profile. Changes are marked pending until applied. Reload from Roblox or use Apply to Roblox, close Roblox before applying changes. |
| Settings file location | Use the default Roblox settings XML file or browse for a custom file. The editor shows the active path. |
| Auto Apply Settings | Apply the saved profile on application startup and before launches. While enabled, the app marks the settings XML read-only and releases its own read-only lock on normal exit. |
| Roblox Downloader | Download and extract the latest LIVE Windows Roblox Player deployment to Roblox's default Versions folder. Enable Customizations to choose a version hash or destination folder. |
| Portable Chromium | Download or reinstall the latest supported Chromium build and its matching driver. |
| Browser selection | Choose Chrome, Firefox, Edge, or portable Chromium for automated browser flows. Brave and Opera GX users can use portable Chromium. |

### Application controls and integrations

| Feature | Description |
| :--- | :--- |
| Smooth animations | Buttons light up when you point at or click them and pages fade in. This can be turned off under Settings > General, and it is off automatically when Windows animations are off. |
| Loading screen | A small window with the version and a progress bar shows while the app starts and fades into the main window. It can be turned off under Settings > General. |
| Color themes | Pick one of eight color presets (Default, Midnight, AMOLED Black, Nord, Dracula, Solarized Dark, Forest, Rose) and optionally your own accent color under Settings > Themes, with a live preview. The choice is applied the next time the application starts. |
| Custom backgrounds | Choose a local image, animated GIF, or video under Settings > Themes, adjust the Opacity Blur slider, and customize text, muted text, outlines, and surface tint. Background changes apply immediately, Reset Theme restores the background defaults. |
| Detachable pages | Right-click a navigation page and choose Open in New Window. Show or reattach it from the same menu, closing the detached window also reattaches it. |
| Window preferences | Resize the main window, keep its saved size between runs, or enable Always on Top under Settings > General. |
| System tray | Hide the main window to the system tray, restore it from the tray icon, or exit from the tray menu. |
| Windows startup | Optionally start Evanovar RAM with Windows and add a Start Menu shortcut. |
| Update manager | Check GitHub releases on startup or manually, read release notes, skip a version, or open Manual Download. Compiled builds can download and install an update automatically, with a backup during executable replacement and an application restart. Source runs use Manual Download. |
| WebSocket server | Enable Developer Mode and the optional local command server under Settings > Developer. Configure its port and optional password to query accounts, import cookies, launch games, and control configured Auto-Rejoin workers. |
| Console | Review color-coded application output and copy or clear the current console view. |
| Structured errors | Show specific error codes and technical details instead of generic failure messages. |
| Crash and hang diagnostics | Save session, UI-hang, and update logs under `AccountManagerData/logs`, and exception reports under `AccountManagerData/crash_logs`. Error dialogs can copy the message or session log. Startup keeps the newest 20 files of each kind by default, change Log Files to Keep under Settings > General (0 keeps everything). |

### Security and local data

| Feature | Description |
| :--- | :--- |
| Hardware encryption | Encrypt saved accounts with a key tied to the current Windows machine. No password is required at startup. |
| Password encryption | Encrypt saved accounts with a user-provided password. |
| No encryption | Store account data without encryption when explicitly selected. |
| Encryption switching | Re-encrypt saved accounts and secure settings when changing encryption methods. |
| Encryption status | Display the active hardware, password, or unencrypted state beside the account list. |
| Local account recovery | Save accounts atomically and keep `saved_accounts.json.bak`. If the main file cannot be read, the app attempts to load a compatible backup and warns that recent changes may be missing. |
| Account backup | Export all accounts to a file protected by a password you choose and import them again from Settings > Misc, for example to move them to another computer. Existing accounts are kept unless you choose to replace them. |
| Data removal | Wipe local application data from Settings > Misc. |

## Data and privacy

Evanovar RAM stores its application data in `AccountManagerData`. This includes saved accounts and their backup, encryption configuration, groups, favorites, recent games, Auto-Rejoin configurations, UI preferences, the local `RobloxSettings.json` profile, avatar cache, and diagnostic logs. Downloaded portable Chromium is also kept there. Custom background media is read from the path you choose.

By default this folder is created next to the application. To keep the data somewhere else, or to run separate profiles side by side, start the application with `--data-dir "D:/Profiles/Alt"` or set the `RAM_DATA_DIR` environment variable. The option wins over the variable, and relative paths, `~` and `%VARIABLES%` are expanded.

The application does not include a telemetry or advertising integration. Network requests support account operations and enabled or requested features:

- Roblox APIs and content servers for login/signup, cookie validation, account details, avatars, game search, presence, private server links, authentication, and client downloads.
- GitHub requests for release and update checks.
- Google's Chromium snapshot storage for the optional portable browser and matching driver. Selenium can also obtain drivers for installed browsers.
- Microsoft Sysinternals for the optional Handle64 download.
- Connectivity checks used by Auto-Rejoin. They use Google and Cloudflare by default, and `connectivity_check_urls` in `AccountManagerData/ui_settings.json` can replace them with your own list of addresses.

Saved cookies are sent to Roblox to authenticate account operations, including the default startup cookie check. Local account data and the WebSocket password use the selected encryption method, choosing No Encryption stores them as plaintext. Ordinary settings, groups, favorites, recent-game entries, and Auto-Rejoin configurations are not covered by account encryption and can include private server links.

Account backups made with Export Accounts use their own password. Copy Contents exports are plain text. Diagnostics redact recognized cookie, password, authentication-ticket, and private-link patterns before writing application logs.

## Build from source

Install [uv](https://docs.astral.sh/uv/), then run the shared build command on Windows:

```powershell
.\scripts\build.cmd
```

The command clears inherited Python path overrides, then uv installs the Python version in `.python-version` and the locked dependencies into a fresh build environment. The builder limits DLL discovery to that Python installation and Windows system directories, so unrelated tools on your PATH are not used. Local builds and CI use the same Python build script.

The executable is written to `dist/EvanovarRAM.exe`. Before reporting success, the builder checks that the packaged app can create its main window and exit, using Qt's offscreen platform and temporary application data. Build configuration lives in `packaging/EvanovarRAM.spec`, and version metadata is generated during the build. Release builds also create `dist/EvanovarRAM-v<version>.exe` for GitHub Releases.

`src/utils/version.py` is the single source of truth for the application version. Release tags must match `APP_VERSION`.

## System changes and uninstallation

Depending on enabled features, Evanovar RAM can:

- Create and update files under `AccountManagerData`.
- Register or remove Windows startup and Start Menu entries.
- Download portable Chromium, Handle64, or Roblox deployment files when requested.
- Temporarily mark Roblox settings as read-only when Auto Apply Settings is enabled.
- Write changes to the selected Roblox settings XML file and keep a `.ram.bak` backup beside it.
- Hold exclusive locks on Roblox's shared native login files while Multi Roblox is active.
- Temporarily move Roblox installer files into the application quarantine folder.

To uninstall:

1. Disable Roblox Installer Fix if enabled, then exit the application normally from the window or system tray so temporary resources can be released.
2. Remove any startup or Start Menu entry that was enabled in the application.
3. Delete the application folder or executable.
4. Delete `AccountManagerData`, or the custom data directory you selected, to remove saved accounts, settings, downloads, and logs. Separately remove any exported backups, text exports, or Roblox deployments you saved elsewhere if they are no longer needed.

## Disclaimer

This project is provided for educational and account management purposes. Users are responsible for complying with Roblox's Terms of Use and all applicable rules. The project maintainers are not responsible for account actions, moderation, data loss, or other consequences caused by use of the application.

## Contributing

Issues and pull requests are welcome. Keep changes focused, describe how they were tested, and avoid committing files from `AccountManagerData`.

Before opening a pull request, run the tests with `uv run --no-sync python scripts/run_tests.py --all`.
Use `--list` to see available tests, `--test <module-or-test-id>` for an individual
selection, or `--suite unit`, `--suite ui`, or `--suite integration` to choose a suite.

## Support

- [Discord community](https://discord.gg/SZaZU8zwZA)
- [Documentation](https://evanovars-roblox-account-manager.gitbook.io/evanovars-ram)
- [GitHub issues](https://github.com/evanovar/RobloxAccountManager/issues)

## License

Evanovar RAM is available under the [GNU General Public License v3.0](LICENSE).
