[![Version](https://img.shields.io/github/v/release/evanovar/RobloxAccountManager)](https://github.com/evanovar/RobloxAccountManager/releases/latest)
![License](https://img.shields.io/github/license/evanovar/RobloxAccountManager)
[![Discord](https://img.shields.io/discord/1436930121897476140?label=Discord)](https://discord.gg/TYnJXyEhgY)
![DownloadCount](https://img.shields.io/github/downloads/evanovar/RobloxAccountManager/total)<br>
[![Download](https://img.shields.io/badge/Download-280ab?style=for-the-badge)](https://github.com/evanovar/RobloxAccountManager/releases/latest/download/RobloxAccountManager.exe)

# 🚀 Roblox Account Manager

A powerful tool for managing multiple Roblox accounts with secure cookie extraction and modern UI interface.

**Created by evanovar** · **Get Help:** [Discord Server](https://discord.gg/TYnJXyEhgY)<br>

⭐ If you like this project, please consider starring the repository! ⭐

<img width="447" height="542" alt="image" src="https://github.com/user-attachments/assets/d005e780-96ef-4130-97f7-d192b1629a01" />
<img width="297" height="411" alt="image" src="https://github.com/user-attachments/assets/95ba25f5-035b-4618-a56b-9920dd7953a4" />

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
| :--- | :---: | ---: |
| **Browser Login** | Add accounts by logging in manually through Chrome | Click "Add Account" → browser opens → login to Roblox |
| **Cookie Import** | Import accounts using `.ROBLOSECURITY` cookie | Click "Add Account" dropdown → "Import Cookie" → paste cookie |
| **JavaScript Automation** | Bulk add accounts with custom JavaScript execution (up to 10 instances) | Click "Add Account" dropdown → "Javascript" → choose amount, website, and code |
| **Account Validation** | Check if account cookies are still valid or expired | Right-click account → "Validate Account" |
| **Account Notes** | Add custom notes/tags to accounts for organization | Right-click account → "Edit Note" |
| **Account Deletion** | Remove accounts from your saved list | Right-click account → "Delete" → confirm |
| **Multi-Select Mode** | Select and manage multiple accounts at once | Enable in Settings → Use Ctrl+Click to select multiple |
| **Drag & Drop Reordering** | Reorder accounts by dragging and dropping in the list | Click & hold account for 0.5s, then drag to new position |

### Game Launching

| Feature | Description | How to Use |
|---------|-------------|-----------|
| **Single Game Launch** | Launch Roblox game with one account | Enter Place ID → Click "Join Place" |
| **Multi-Account Launch** | Launch the same game with multiple accounts simultaneously | Enable Multi-Select → Select accounts → Enter Place ID → Click "Join Place" |
| **Private Server Support** | Save and launch private servers (marked with [P]) | Enter Private Server ID → Game automatically joins private server |
| **Join User** | Join a specific user's current game | Select account → Click "Join Place" dropdown → "Join User" → enter username |
| **Join by Job-ID** | Join a specific server instance using Job-ID | Enter Place ID & Job-ID → Click "Join Place" dropdown → "Job-ID" |
| **Game List (Recently Played)** | Auto-save recently played games for quick access | Games auto-save on launch (configurable 5-50 games) |
| **Game Name Lookup** | Auto-fetch and display game names from Place IDs | Place ID auto-fetches name in background |
| **Launch Confirmation** | Optional confirmation before launching games | Enable in Settings → "Confirm Before Launch" |
| **Launch Popup Disable** | Disable success notification popups | Enable in Settings → "Disable Launch Popups" |

### Multi Roblox & Error 773

| Feature | Description | How to Use |
|---------|-------------|-----------|
| **Multi Roblox (Default Mode)** | Run multiple Roblox instances with mutex lock | Enable in Settings → "Multi Roblox" → uses default method |
| **Multi Roblox (handle64 Mode)** | Advanced mode for closing handle events (requires admin) | Enable in Settings → Choose "handle64" → must run as administrator |
| **Error 773 Prevention** | Automatic lock of RobloxCookies.dat to prevent Error 773 | Activates when Multi Roblox is enabled |
| **Running Instance Check** | Warns if Roblox is already running when enabling Multi Roblox | Prompts to close existing instances |

### Auto-Rejoin System

| Feature | Description | How to Use |
|---------|-------------|-----------|
| **Auto-Rejoin Setup** | Configure automatic game rejoin for accounts | Click "Auto-Rejoin" → "Add" → select account & Place ID |
| **Rejoin Configuration** | Set check interval, private server ID, job ID, max retries | In Auto-Rejoin window → "Edit" existing config |
| **Start/Stop Individual** | Control rejoin status per account | Select account → "Start Selected" / "Stop Selected" |
| **Start/Stop All** | Bulk start/stop all rejoin configurations | Click "Start All" / "Stop All" buttons |
| **Active Status Display** | See which accounts are actively rejoin monitoring | [ACTIVE] / [INACTIVE] status shown in list |
| **Remove Configuration** | Delete rejoin setup for an account | Select account → "Remove" |

### UI Customization & Settings

| Feature | Description | How to Use |
|---------|-------------|-----------|
| **Dark Theme System** | Full customizable dark theme with color pickers | Settings → Theme tab → adjust colors |
| **Color Customization** | 5 color pickers: Background Dark/Mid/Light, Text, Accent | Settings → Theme tab → click color picker icon |
| **Font Selection** | Choose from preset fonts (Segoe UI, Arial, etc.) | Settings → Theme tab → select font dropdown |
| **Font Size Adjustment** | Adjust font size (8-16px) | Settings → Theme tab → size slider |
| **Always on Top** | Keep window above all other windows | Settings → General tab → "Always on Top" |
| **Multi-Select Mode** | Enable Ctrl+Click multi-selection in account list | Settings → General tab → "Multi-Select Mode" |
| **Max Recent Games** | Configure how many recent games to save (5-50) | Settings → General tab → spinner control |
| **Roblox Launcher Selection** | Choose between Default or Custom launchers (Bloxstrap/Fishstrap) | Settings → General tab → launcher dropdown |
| **Persistent Settings** | All settings auto-save to `ui_settings.json` | Changes auto-save every 0.5s |

### Encryption & Data Security

| Feature | Description | How to Use |
|---------|-------------|-----------|
| **Hardware Encryption** | Automatic encryption tied to your PC's hardware ID | Setup Wizard → choose "Hardware" → no password needed |
| **Password Encryption** | Portable encryption that works on any PC with password | Setup Wizard → choose "Password" → set password |
| **No Encryption** | Store accounts unencrypted (not recommended) | Setup Wizard → choose "No Encryption" |
| **Encryption Status Indicator** | Visual display of encryption method per account | [HARDWARE ENCRYPTED] / [PASSWORD ENCRYPTED] / [NOT ENCRYPTED] |
| **Password Prompt** | Automatic password request on startup for password-encrypted data | Enter password when launching app |
| **Account Storage** | All accounts stored in `AccountManagerData/saved_accounts.json` | Auto-saved on every account change |
| **Settings Storage** | UI preferences saved to `ui_settings.json` | Auto-saved on every setting change |
| **Portable Data** | Move `AccountManagerData` folder to another PC | Works with password encryption (not hardware) |

### Advanced Features

| Feature | Description | How to Use |
|---------|-------------|-----------|
| **Anti-AFK System** | Periodic key presses to prevent AFK detection | Settings → Anti-AFK tab → enable & set interval/key |
| **Anti-AFK Interval** | Configurable time between AFK prevention actions | Settings → Anti-AFK tab → set 1-60 minute intervals |
| **Anti-AFK Key Selection** | Choose which key to press (w, a, s, d, space, etc.) | Settings → Anti-AFK tab → select key |
| **Installer Quarantine** | Auto-move RobloxPlayerInstaller.exe to prevent popups | Automatically handled when Multi Roblox enabled |
| **Installer Restore** | Restore quarantined installers on shutdown | Automatic on app close |
| **Console Output** | Real-time logging of all operations | Built-in console displays all debug info |
| **Update Checker** | Auto-check for new releases on startup | Settings → Auto-update enabled by default |
| **Auto Update** | Download and install latest version automatically | Click "Auto Update" in update notification |
| **Manual Update** | Download latest release from GitHub | Click "Manual Update" → opens GitHub releases |
| **Username from Cookie** | Auto-fetch username from `.ROBLOSECURITY` cookie | Automatic during cookie import |
| **Game Name Lookup API** | Fetch game names from Roblox API using Place ID | Automatic when Place ID changes |
| **User ID Resolution** | Get user ID from username for join user feature | Automatic in join user function |
| **Player Presence Tracking** | Check if user is in-game and get their current game | Used by "Join User" feature |
| **Custom Launcher Detection** | Auto-detect Bloxstrap or Fishstrap installations | Automatic on startup |
