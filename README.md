[![Version](https://img.shields.io/github/v/release/evanovar/RobloxAccountManager)](https://github.com/evanovar/RobloxAccountManager/releases/latest)
![License](https://img.shields.io/github/license/evanovar/RobloxAccountManager)
[![Discord](https://img.shields.io/discord/1436930121897476140?label=Discord)](https://discord.gg/TYnJXyEhgY)
![DownloadCount](https://img.shields.io/github/downloads/evanovar/RobloxAccountManager/total)
[![Website](https://img.shields.io/badge/website-online-1F58FF
)](https://evanovars-roblox-account-manager.gitbook.io/evanovars-ram/homepage)<br>
[![Download](https://img.shields.io/badge/Download-280ab?style=for-the-badge)](https://github.com/evanovar/RobloxAccountManager/releases/latest/download/RobloxAccountManager.exe)

> [!IMPORTANT]
> Before you see this as a **"Virus"** or **"Unofficial,"** please read:
> - **Project Status:** This project was inspired by the original Roblox Account Manager by ic3w0lf22. I recreated it in Python as a personal project because I thought it would be fun to build and learn from. It is not intended to be an official continuation of the original project.<br><br>
> - **100% Open Source:** Every line of code is transparent and available for everyone. If you don't trust the .exe, you are encouraged to run the script directly from the source code.<br><br>
> - **Integrity:** The standalone .exe in the releases is compiled directly from this code with zero alterations.

# Evanovar RAM

A powerful tool for managing multiple Roblox accounts with secure cookie extraction and modern UI interface.

**Created by evanovar** · **Get Help:** [Discord Server](https://discord.gg/TYnJXyEhgY)<br>

⭐ If you like this project, please consider starring the repository! ⭐<br>
Or support the creator by donating via [Robux](https://www.roblox.com/games/718090786/donation#store) ♥️

<img width="795" height="651" alt="image" src="https://github.com/user-attachments/assets/6dab4d69-11fd-47d0-9348-db2aef5211fb" />

## 📑 Table of Contents

- [Installation](#installation)
- [Requirements](#requirements)
- [Disclaimer](#disclaimer)
- [Privacy Policy](#privacy-policy)
- [System Changes and Uninstallation](#system-changes-and-uninstallation)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)
- [Features](#features)

## Installation

### Method 1: Direct EXE (Recommended for Users)

**Quick & Easy - No Python Required!**

1. Go to [Releases](https://github.com/evanovar/RobloxAccountManager/releases)
2. Download `RobloxAccountManager.exe` from the latest release
3. Put it in a folder
4. Double-click to run - that's it!

**Requirements:**

- **Google Chrome browser**
- **Windows** (currently optimized for Windows)

> ⚠️ Windows Defender may flag the EXE as untrusted since it's not signed. Click "More info" → "Run anyway" to proceed.

### Method 2: Clone Repository (For Developers, or for people that dont trust the EXE)

**Full source code access and customization**
**Requirements:**

- **Python 3.7+**
- **Google Chrome browser**
- **Windows** (currently optimized for Windows)

### Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/evanovar/RobloxAccountManager
   cd RobloxAccountManager
   ```

2. **Install dependencies**

   ```bash
   py -m pip install -r requirements.txt
   ```

3. **Run the application**

   ```bash
   py main.py
   ```

## Requirements

The following Python packages are required:

- `selenium` - Browser automation
- `requests` - HTTP requests for account validation and game info
- `webdriver-manager` - Automatic ChromeDriver management
- `pycryptodome` - Encryption and cookie handling
- `PySide6` - Main desktop UI framework
- `pywin32` - Windows API access for Multi Roblox feature
- `psutil` - Process monitoring for Multi Roblox handle64 mode
- `pyautoit` - Window rotation and maintenance actions for Anti-AFK
- `websockets` - WebSocket server support for developer features
- `PyInstaller` - Required to build the standalone EXE

## Disclaimer

This tool is for educational purposes only. Users are responsible for complying with Roblox's Terms of Service. The developers are not responsible for any consequences resulting from the use of this tool.

### Team Roles

- Committers and reviewers: [evanovar](https://github.com/evanovar)
- Approvers: [evanovar](https://github.com/evanovar)

## Privacy Policy

This program does not include hidden telemetry, ad SDKs, or analytics tracking.

Network communication is limited to documented functionality:

- Roblox API calls required for Roblox account and game features.
- GitHub API/release checks for update-related features.
- Discord webhook/bot endpoints only when Discord integration is configured by the operator.
- Optional connectivity checks used by auto-rejoin safety logic.

If Discord/webhook/auto-update features are not enabled, those related network requests are not performed.

## System Changes and Uninstallation

The program may make local system changes based on enabled settings:

- Creates/updates local application data under AccountManagerData.
- Can create/remove a Start Menu shortcut.
- Can set Roblox settings files as read-only when the lock option is enabled.
- Can download optional dependencies/features only when requested by the user.

Uninstallation:

1. Close the application.
2. Delete the application folder containing RobloxAccountManager.exe.
3. Delete AccountManagerData if you want to remove local data.
4. Remove the Start Menu shortcut if it exists.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the [GPL 3.0 License](LICENSE).

## Support

Have questions or need help? Join our **[Discord Server](https://discord.gg/TYnJXyEhgY)** where the community and developers can assist you!

## Features

### Account Management

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Browser Login** | Add accounts by logging in manually through Chrome | Click "Add Account" → browser opens → login to Roblox |
| **Cookie Import** | Import accounts using `.ROBLOSECURITY` cookie | Click "Add Account" dropdown → "Import Cookie" → paste cookie |
| **Multiple Cookie Import** | Import multiple accounts at once | Click "Add Account" dropdown → "Import Cookie" → paste multiple cookies |
| **JavaScript Automation** | Bulk add accounts with custom JavaScript execution (up to 10 instances) | Click "Add Account" dropdown → "Javascript"|
| **Password Capture** | Automatically captures and saves passwords during browser login | Automatic during browser login; right-click account → "Copy Password" |
| **Cookie Validity Indicator** | Warning icon next to accounts with expired or invalid cookies | Automatically shown in the account list |
| **Account Notes** | Add custom notes/tags to accounts for organization | Right-click account → "Edit Note" |
| **Account Deletion** | Remove accounts from your saved list | Right-click account → "Delete" → confirm |
| **Multi-Select Mode** | Select and manage multiple accounts at once | Enable in Settings → Use Ctrl+Click to select multiple |
| **Drag & Drop Reordering** | Reorder accounts by dragging and dropping in the list | Click & hold account for 0.5s, then drag to new position |

### Game Launching

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Single Game Launch** | Launch Roblox game with one account | Enter Place ID → Click "Join Place" |
| **Multi-Account Launch** | Launch the same game with multiple accounts simultaneously | Enable Multi-Select → Select accounts → Enter Place ID → Click "Join Place" |
| **Private Server Support** | Save and launch private servers (marked with [P]) | Enter Private Server ID → Game automatically joins private server |
| **VIP Link Parsing** | Paste a full Roblox VIP URL into the Private Server field to auto-extract Place ID and server code | Paste VIP URL into "Private Server" field |
| **Join User** | Join a specific user's current game; last-used account saved across sessions | Select account → "Join Place" dropdown → "Join User" → enter username |
| **Join by Job-ID** | Join a specific server instance using Job-ID | Enter Place ID & Job-ID → "Join Place" dropdown → "Job-ID" |
| **Join Smallest Server** | Automatically join the server with the lowest player count | "Join Place" dropdown → "Small Server" |
| **Game List (Recently Played)** | Auto-save recently played games for quick access | Games auto-save on launch (configurable 5-50 games) |
| **Game Name Lookup** | Auto-fetch and display game names from Place IDs | Automatic when Place ID changes |
| **Roblox Launcher Selection** | Choose your preferred Roblox launcher | Settings → Roblox → select Default, Bloxstrap, Fishstrap, Froststrap, or Roblox Client |

### Multi Roblox

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Multi Roblox (Default Mode)** | Run multiple Roblox instances with mutex lock | Enable "Multi Roblox" → select "Default" method |
| **Multi Roblox (Handle64 Mode)** | Advanced mode using handle64.exe — works alongside already-running instances | Enable "Multi Roblox" → select "Handle64" → run as administrator |
| **Admin Relaunch Prompt** | Prompts to relaunch as admin when switching to Handle64 without elevated privileges | Automatic when selecting Handle64 without admin rights |
| **Handle64 Custom Launcher Support** | Handle64 method works correctly with Bloxstrap, Fishstrap, and Froststrap | Automatic when custom launcher is selected |
| **Error 773 Prevention** | Automatic lock of `RobloxCookies.dat` to prevent Error 773 | Activates when Multi Roblox is enabled |
| **Running Instance Check** | Warns if Roblox is already running when enabling Multi Roblox | Prompts to close existing instances |

### Auto-Rejoin System

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Auto-Rejoin Setup** | Configure automatic game rejoin for accounts | Click "Auto-Rejoin" → "Add" → select account & Place ID |
| **Start/Stop Individual** | Control rejoin status per account | Select account → Right click → "Start Selected" / "Stop Selected" |
| **Start/Stop All** | Bulk start/stop all rejoin configurations | Click "Start All" / "Stop All" buttons |
| **Active Status Display** | See which accounts are actively monitored | [ACTIVE] / [INACTIVE] status shown in list |

### Settings & Tools

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Switch Encryption Method** | Seamlessly switch between Hardware and Password encryption | Settings → Misc → "Switch Encryption Method" |
| **Wipe Data** | Securely overwrite all data in `AccountManagerData` | Settings → Misc → "Wipe Data" |
| **Start Menu Shortcut** | Add or remove a Windows Start Menu shortcut for the app | Settings → General → "Add to Start Menu" |
| **Rename Roblox Windows** | Automatically renames Roblox window titles to the account's username | Settings → Roblox → "Rename Roblox Windows to username" |
| **Console Output** | Real-time color-coded log of all operations with timestamps | Console Category |
| **Update Checker** | Auto-checks for new releases on startup | Automatic; to disable, Settings → Uncheck "Check for Updates on Startup" |
| **Auto Update** | Download and install the latest version automatically | Click "Auto Update" in the update notification |
| **Roblox RAM Trim** | Clears the working set of newly detected Roblox processes | Settings → Roblox → enable **Optimize Roblox Ram** |


### Encryption & Data Security

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Hardware Encryption** | Encryption tied to your PC's hardware — no password needed | Setup Wizard → choose "Hardware" |
| **Password Encryption** | Portable encryption requiring a password — works on any PC | Setup Wizard → choose "Password" |
| **No Encryption** | Store accounts unencrypted (not recommended) | Setup Wizard → choose "No Encryption" |
| **Encryption Status Indicator** | Shows encryption type in the UI | Displayed as [HARDWARE ENCRYPTED] / [PASSWORD ENCRYPTED] / [NOT ENCRYPTED] |
| **Password Prompt** | Prompts for password on startup when using password encryption | Automatic |
| **Portable Chromium** | Built-in Chromium browser download for environments without Chrome | Settings → Misc → Browser Engine → download Chromium |

### Anti-AFK

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Anti-AFK Window** | Opens a dedicated maintenance window for anti-AFK controls | Anti AFK Category |
| **Key Recording** | Record any keyboard or mouse input as the maintenance action | Anti AFK category → click the action key button |
| **Press Count** | Set how much the chosen input is pressed during maintenance | Anti AFK category → press count |
| **Configurable Interval** | Set how often maintenance runs | Anti AFK category → set interval |
| **30s Countdown Tooltip** | Shows a countdown before each maintenance cycle | Anti AFK category → Show countdown tooltip |
