[![Version](https://img.shields.io/github/v/release/evanovar/RobloxAccountManager)](https://github.com/evanovar/RobloxAccountManager/releases/latest)
![License](https://img.shields.io/github/license/evanovar/RobloxAccountManager)
[![Discord](https://img.shields.io/discord/1436930121897476140?label=Discord)](https://discord.gg/TYnJXyEhgY)
![DownloadCount](https://img.shields.io/github/downloads/evanovar/RobloxAccountManager/total)<br>
[![Download](https://img.shields.io/badge/Download-280ab?style=for-the-badge)](https://github.com/evanovar/RobloxAccountManager/releases/latest/download/RobloxAccountManager.exe)

# 🚀 Roblox Account Manager

A powerful tool for managing multiple Roblox accounts with secure cookie extraction and modern UI interface.

**Created by evanovar** · **Get Help:** [Discord Server](https://discord.gg/TYnJXyEhgY)<br>

⭐ If you like this project, please consider starring the repository! ⭐<br>
Or support the creator by donating via [Robux](https://www.roblox.com/games/718090786/donation#store) ♥️

<img width="447" height="544" alt="image" src="https://github.com/user-attachments/assets/7296d21f-4026-486b-a9fd-ea75515be930" />
<img width="295" height="412" alt="image" src="https://github.com/user-attachments/assets/7a5acb0d-3b65-470e-ac90-7d022570df5b" />

## 📑 Table of Contents

- [Installation](#-installation)
- [Requirements](#-requirements)
- [Disclaimer](#-disclaimer)
- [Contributing](#-contributing)
- [License](#-license)
- [Support](#-support)
- [Features](#-features)

## 🛠️ Installation

### Method 1: Direct EXE (Recommended for Users)

**Quick & Easy - No Python Required!**

1. Go to [Releases](https://github.com/evanovar/RobloxAccountManagerConsole/releases)
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
   
## 📋 Requirements

The following Python packages are required:
- `selenium` - Browser automation
- `requests` - HTTP requests for account validation and game info
- `webdriver-manager` - Automatic ChromeDriver management
- `pycryptodome` - Encryption and cookie handling
- `pywin32` - Windows API access for Multi Roblox feature
- `psutil` - Process monitoring for Multi Roblox handle64 mode

## ⚠️ Disclaimer

This tool is for educational purposes only. Users are responsible for complying with Roblox's Terms of Service. The developers are not responsible for any consequences resulting from the use of this tool.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [GPL 3.0 License](LICENSE).

## 📞 Support

Have questions or need help? Join our **[Discord Server](https://discord.gg/TYnJXyEhgY)** where the community and developers can assist you!

## ✨ Features

### Account Management

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Browser Login** | Add accounts by logging in manually through Chrome | Click "Add Account" → browser opens → login to Roblox |
| **Cookie Import** | Import accounts using `.ROBLOSECURITY` cookie | Click "Add Account" dropdown → "Import Cookie" → paste cookie |
| **Multiple Cookie Import** | Import multiple accounts at once | Click "Add Account" dropdown → "Import Cookie" → paste multiple cookies |
| **JavaScript Automation** | Bulk add accounts with custom JavaScript execution (up to 10 instances) | Click "Add Account" dropdown → "Javascript" → choose amount, website, and code |
| **Password Capture** | Automatically captures and saves passwords during browser login | Automatic during browser login; right-click account → "Copy Password" |
| **Cookie Validity Indicator** | Warning icon next to accounts with expired or invalid cookies | Automatically shown in the account list |
| **Account Notes** | Add custom notes/tags to accounts for organization | Right-click account → "Edit Note" |
| **Account Deletion** | Remove accounts from your saved list | Right-click account → "Delete" → confirm |
| **Multi-Select Mode** | Select and manage multiple accounts at once | Enable in Settings → Use Ctrl+Click to select multiple |
| **Drag & Drop Reordering** | Reorder accounts by dragging and dropping in the list | Click & hold account for 0.5s, then drag to new position |
| **Keyboard Shortcuts** | Delete selected accounts with the Delete key | Select account(s) → press Delete |

### Game Launching

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Single Game Launch** | Launch Roblox game with one account | Enter Place ID → Click "Join Place" |
| **Multi-Account Launch** | Launch the same game with multiple accounts simultaneously | Enable Multi-Select → Select accounts → Enter Place ID → Click "Join Place" |
| **Auto Window Tiling** | Automatically arranges Roblox windows in a tiled grid when launching multiple instances | Automatic when launching 2+ accounts simultaneously |
| **Private Server Support** | Save and launch private servers (marked with [P]) | Enter Private Server ID → Game automatically joins private server |
| **VIP Link Parsing** | Paste a full Roblox VIP URL into the Private Server field to auto-extract Place ID and server code | Paste VIP URL into "Private Server" field |
| **Join User** | Join a specific user's current game; last-used account saved across sessions | Select account → "Join Place" dropdown → "Join User" → enter username |
| **Join by Job-ID** | Join a specific server instance using Job-ID | Enter Place ID & Job-ID → "Join Place" dropdown → "Job-ID" |
| **Join Smallest Server** | Automatically join the server with the lowest player count | "Join Place" dropdown → "Small Server" |
| **Favorite Games** | Save and quickly launch favorite games with optional notes | Click ⭐ next to Recent Games → add favorites |
| **Game List (Recently Played)** | Auto-save recently played games for quick access | Games auto-save on launch (configurable 5-50 games) |
| **Game Name Lookup** | Auto-fetch and display game names from Place IDs | Automatic when Place ID changes |
| **Launch Popup Disable** | Disable success notification popups | Settings → General tab → "Disable Launch Popups" |
| **Roblox Launcher Selection** | Choose your preferred Roblox launcher | Settings → Roblox tab → select Default, Bloxstrap, Fishstrap, Froststrap, or Roblox Client |

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
| **Rejoin Configuration** | Set check interval, private server ID, job ID, and max retries | In Auto-Rejoin window → "Edit" existing config |
| **Presence Check Toggle** | Optionally rejoin only when player is not in the target Place ID | In Auto-Rejoin config → enable "Check if player is in target Place ID" |
| **Multi-Select Auto-Rejoin** | Select multiple accounts at once in the Auto-Rejoin window | Hold Ctrl or Shift to select multiple accounts |
| **Start/Stop Individual** | Control rejoin status per account | Select account → "Start Selected" / "Stop Selected" |
| **Start/Stop All** | Bulk start/stop all rejoin configurations | Click "Start All" / "Stop All" buttons |
| **Active Status Display** | See which accounts are actively monitored | [ACTIVE] / [INACTIVE] status shown in list |
| **Remove Configuration** | Delete rejoin setup for an account | Select account → "Remove" |
| **Webhook Notifications** | Send Discord webhook alerts on rejoin events, errors, and failures | Click the Discord logo button next to "Auto-Rejoin Accounts" |
| **Hourly Screenshot Webhook** | Automatically sends a screenshot to Discord every hour while auto-rejoin is active | Configure in webhook settings |
| **Ping on Error** | Ping a specific Discord user when a rejoin failure occurs | Set User ID in webhook settings |

### Settings & Tools

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Active Instances Window** | View all running Roblox instances in real time with username, Place ID, and PID | Settings → Tool tab → "Active Instances" |
| **Roblox Settings Editor** | Edit Roblox's local settings file directly from the app | Settings → Tool tab → "Roblox Setting" |
| **Lock Roblox Settings** | Sets the Roblox settings file read-only on every launch to prevent Roblox overwriting it | Settings → Tool tab → Roblox Settings → enable "Lock settings" |
| **Roblox Version Downloader** | Download and install any Roblox version by version hash | Settings → Tool tab → "Roblox Version" |
| **Switch Encryption Method** | Seamlessly switch between Hardware and Password encryption | Settings → Tool tab → "Switch Encryption Method" |
| **Wipe Data** | Securely overwrite all data in `AccountManagerData` | Settings → Tool tab → "Wipe Data" |
| **Window Position Memory** | Saves and restores the position of main window, Settings, Favorites, Auto-Rejoin, and Console Output | Automatic |
| **Start Menu Shortcut** | Add or remove a Windows Start Menu shortcut for the app | Settings → General tab → "Add to Start Menu" |
| **Rename Roblox Windows** | Automatically renames Roblox window titles to the account's username | Settings → Roblox tab → "Rename Roblox Windows with Account Name" |
| **Console Output** | Real-time color-coded log of all operations with timestamps | Settings → "Console Output" button; supports Copy All & Clear |
| **Update Checker** | Auto-checks for new releases on startup | Automatic; shows notification if update is available |
| **Auto Update** | Download and install the latest version automatically | Click "Auto Update" in the update notification |
| **About Tab** | View app version and access Discord/GitHub links | Settings → About tab |

### UI Customization

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Dark Theme System** | Fully customizable dark theme | Settings → Theme tab |
| **Color Customization** | 5 color pickers: Background Dark/Mid/Light, Text, Accent | Settings → Theme tab → click color picker icons |
| **Font Selection** | Choose from 7 preset fonts (Segoe UI, Arial, Calibri, etc.) | Settings → Theme tab → font dropdown |
| **Font Size Adjustment** | Adjust font size (8–16px) | Settings → Theme tab → size controls |
| **Always on Top** | Keep the window above all other windows | Settings → General tab → "Always on Top" |
| **Discord Quick Link** | Discord logo button next to "Quick Actions" opens the project server | Click the Discord logo button |

### Encryption & Data Security

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Hardware Encryption** | Encryption tied to your PC's hardware — no password needed | Setup Wizard → choose "Hardware" |
| **Password Encryption** | Portable encryption requiring a password — works on any PC | Setup Wizard → choose "Password" |
| **No Encryption** | Store accounts unencrypted (not recommended) | Setup Wizard → choose "No Encryption" |
| **Encryption Status Indicator** | Shows encryption type in the UI | Displayed as [HARDWARE ENCRYPTED] / [PASSWORD ENCRYPTED] / [NOT ENCRYPTED] |
| **Password Prompt** | Prompts for password on startup when using password encryption | Automatic |
| **Portable Chromium** | Built-in Chromium browser download for environments without Chrome | Settings → Tools → "Browser Engine" → download Chromium |

### Anti-AFK

| Feature | Description | How to Use |
| :--- | :--- | :--- |
| **Anti-AFK System** | Periodic key/mouse presses to prevent AFK detection | Settings → Anti-AFK tab → enable & configure |
| **Key Recording** | Record any keyboard or mouse input as the AFK action | Settings → Anti-AFK → click record button |
| **Mouse Button Support** | Use LMB, RMB, MMB, scroll, or XButton as AFK input | Settings → Anti-AFK → select mouse action |
| **Key Press Amount** | Configure how many times the input is triggered (1–10) | Settings → Anti-AFK → set amount |
| **Configurable Interval** | Set how often the AFK action fires (1–19 minutes) | Settings → Anti-AFK → set interval |
