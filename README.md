[![Version](https://img.shields.io/github/v/release/evanovar/RobloxAccountManager)](https://github.com/evanovar/RobloxAccountManager/releases/latest)
![License](https://img.shields.io/github/license/evanovar/RobloxAccountManager)
[![Discord](https://img.shields.io/discord/1436930121897476140?label=Discord)](https://discord.gg/TYnJXyEhgY)
![DownloadCount](https://img.shields.io/github/downloads/evanovar/RobloxAccountManager/total)<br>
[![Download](https://img.shields.io/badge/Download-280ab?style=for-the-badge)](https://github.com/evanovar/RobloxAccountManager/releases/latest/download/RobloxAccountManager.exe)


# 🚀 Roblox Account Manager

A powerful tool for managing multiple Roblox accounts with secure cookie extraction and modern UI interface. <br>
Created by evanovar · Contact: [Discord Server](https://discord.gg/TYnJXyEhgY) <br>
⭐ If you like this project, please consider starring the repository! ⭐<br>

<img width="447" height="542" alt="image" src="https://github.com/user-attachments/assets/d005e780-96ef-4130-97f7-d192b1629a01" />
<img width="297" height="411" alt="image" src="https://github.com/user-attachments/assets/95ba25f5-035b-4618-a56b-9920dd7953a4" />




## ✨ Features

### 🎨 Modern UI & Theme System
- **Customizable Dark Theme**: Full theme customization with 5 color pickers (Background Dark/Mid/Light, Text, Accent)
- **Font Personalization**: Choose from 7 preset fonts and adjust size (8-16px)
- **Clean Interface:** A modern, compact design that keeps everything clear and easy to navigate.

### 🔐 Account Management
- **Multiple Addition Methods**:
  - Browser automation (login manually in Chrome)
  - Cookie import (paste `.ROBLOSECURITY` cookie)
  - JavaScript automation (bulk account creation with custom scripts)
- **Encryption Options**:
  - Hardware-based (automatic, tied to your PC)
  - Password-based (portable, works on any PC)
  - No encryption (easy transfer but insecure)
- **Account Organization**:
  - Add custom notes to accounts
  - Drag-and-drop reordering
  - Multi-select mode
- **Visual Status Indicators**: See encryption status at a glance ([HARDWARE ENCRYPTED] / [PASSWORD ENCRYPTED] / [NOT ENCRYPTED])

### 🎮 Game Launch Features
- **Multi Roblox + 773 Fix**: Run multiple Roblox instances simultaneously with automatic Error 773 prevention
- **Smart Game List**: Save up to 50 recently played games (configurable 5-50)
- **Private Server Support**: Save and launch private servers with [P] indicator
- **Launch Confirmation**: Optional confirmation dialog before launching games

### 🔧 Quality of Life Features
- **Persistent Settings**: All preferences, game history, and Place IDs auto-save
- **Live Game Name Lookup**: Automatically fetches game names from Place IDs
- **Always on Top Setting**: Keep window on top of other applications (can be enabled/disabled)
- **Console Output**: View detailed logs and debug information
- **Auto-Update Checker**: Notifies you when new versions are available

### ⚙️ Developer Features
- **JavaScript Automation**: Launch up to 10 Chrome instances with custom JavaScript execution
- **Manual Account Import**: Import account manually using .ROBLOSECURITY cookie.

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

## 🔐 Encryption & Security

**1. Hardware Encryption (Not Portable)**
- ✅ Automatic encryption using your computer's unique hardware ID
- ✅ No password needed, completely automatic
- ⚠️ **Data ONLY works on THIS computer**
  
**2. Password Encryption (Portable, Recommended)**
- ✅ Encrypt with a password you create
- ✅ **Works on any computer** with the password
- ⚠️ **MUST remember your password** - there is NO recovery method!

**3. No Encryption (Not Recommended)**
- ✅ Store accounts without any encryption
- ✅ Easy to transfer and backup
- ⚠️ **NOT SECURE** - Anyone with access to files can see your data

## ⚠️ Disclaimer

This tool is for educational purposes only. Users are responsible for complying with Roblox's Terms of Service. The developers are not responsible for any consequences resulting from the use of this tool.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [GPL 3.0 License](LICENSE).

## 📚 Frequently Asked Questions (FAQ)

### General Questions

**Q: Is this tool safe to use?**  
A: Yes, the tool runs entirely locally on your computer. No data is sent to external servers. However, you're responsible for following Roblox's Terms of Service.

**Q: Can I use this on Mac or Linux?**  
A: Currently, this tool is optimized for Windows only.

**Q: What does [P] mean in the game list?**  
A: [P] indicates that the game was saved with a private server link code. Clicking it will load both the Place ID and Private Server ID.

**Q: What is Multi Roblox?**  
A: Multi Roblox allows you to run multiple Roblox instances simultaneously on the same machine. You can enable it in Settings → General tab.

**Q: Does Multi Roblox work automatically?**  
A: If you enable it in Settings, it will activate on startup. If Roblox is already running when you enable it, the tool will ask permission to close all Roblox instances first.

**Q: Where are my data files stored?**  
A: All configuration and account data are stored in the `AccountManagerData` folder:
- `saved_accounts.json` - Your encrypted account data
- `encryption_config.json` - Encryption settings
- `ui_settings.json` - Theme preferences and UI settings

### Encryption Questions

**Q: I forgot my password! How do I recover my accounts?**  
A: Unfortunately, there is **NO password recovery method**. This is by design for security. Lost password = permanent data loss. Always remember your password or use hardware-based encryption instead.

**Q: Can I change from hardware encryption to password encryption?**  
A: Currently, there is no built-in migration tool. You would need to manually re-add your accounts. A safe migration feature is planned for a future update.

**Q: Which encryption method should I choose?**  
A:
- **Hardware Encryption**: Best if you only use one computer, want zero hassle, and don't need cloud backups
- **Password Encryption**: Best if you use multiple computers, want cloud backups, or need portability
- **No Encryption**: You don't care about security at all.

**Q: Can I access my password-encrypted accounts on another computer?**  
A: Yes! Simply copy the entire `AccountManagerData` folder to the new computer, install the app, and enter your password. This folder contains `saved_accounts.json` and `encryption_config.json`.

### Account Management Questions

**Q: How many accounts can I save?**  
A: There's no hard limit. You can save as many accounts as you need.

**Q: How do I select multiple accounts?**  
A: Enable "Multi Select" in Settings, then use Ctrl+Click to select multiple accounts. You can then launch games, edit notes, or delete multiple accounts at once.

**Q: Why is my token invalid?**  
A: Roblox cookies can expire after long periods of inactivity or if you change your account password. Use the "Validate Account" feature to check if an account is still valid.

**Q: If I update the .exe, will it cause data loss?**  
A: No. Updating the `.exe` will not delete your data. All data is stored inside the `AccountManagerData` folder. Just make sure the new `.exe` is placed in the same location as that folder.
