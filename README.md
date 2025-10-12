# 🚀 Roblox Account Manager

A fast, lightweight console tool for managing multiple Roblox accounts with secure cookie extraction. <br>
Created by evanovar · Contact: Discord (same username as on GitHub). <br>
⭐ If you like this project, please consider starring the repository! ⭐<br>

<img width="1105" height="623" alt="image" src="https://github.com/user-attachments/assets/659feef4-0a41-4dc7-95d3-eaa573d90334" />

## ✨ Features

- **🎮 Game Launching** - Direct game launching with specific Game IDs
- **✅ Account Validation** - Check account status and validity
- **🖥️ Simple Console Interface** - Clean, easy-to-use command-line interface

## 🛠️ Installation

### Method 1: Direct EXE (Recommended for Users)

**Quick & Easy - No Python Required!**

1. Go to [Releases](https://github.com/evanovar/RobloxAccountManagerConsole/releases)
2. Download `RobloxAccountManager.exe` from the latest release
3. Double-click to run - that's it!

**Requirements:**
- **Google Chrome browser**
- **Windows** (currently optimized for Windows)

> ⚠️ Windows Defender may flag the EXE as untrusted since it's not signed. Click "More info" → "Run anyway" to proceed.

### Method 2: Clone Repository (For Developers, or for people that don't trust the EXE)

**Full source code access and customization**
- **Python 3.7+**
- **Google Chrome browser**
- **Windows** (currently optimized for Windows)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/evanovar/RobloxAccountManagerConsole
   cd RobloxAccountManagerConsole
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python roblox_account_manager.py
   ```
   
   Or on Windows, double-click `run_account_manager.bat`

## 📋 Requirements

The following Python packages are required:
- `selenium` - Browser automation
- `requests` - HTTP requests for account validation  
- `webdriver-manager` - Automatic ChromeDriver management
- `pycryptodome` - Cookie decryption
- `pywin32` - Windows-specific functionality

## 🎯 Usage

### How It Works

1. **Add Account**: Select "Add new account" from the menu
2. **Browser Opens**: A clean Chrome browser window opens to Roblox login page
3. **Login**: Log into your Roblox account normally
4. **⚡ Login Detection**: Tool detects successful login
5. **🚀 Auto-Close**: Browser closes immediately after detection
6. **💾 Saved**: Username and authentication cookie are saved locally

### Menu Options

- **1. Add new account** - Ultra-fast browser automation for account addition
- **2. List saved accounts** - View all saved accounts with registration dates  
- **3. Delete account** - Remove accounts from the manager
- **4. Validate account** - Check if saved account cookies are still valid
- **5. Launch Roblox game** - Launch specific games or Roblox directly
- **6. Exit** - Close the application

### Adding an Account

1. Select option 1 from the main menu
2. Chrome browser opens automatically with optimized performance
3. Log into your Roblox account normally
4. Browser automatically closes in **25ms** after login detection
5. Account saved with username and authentication cookie

## ⚠️ Disclaimer

This tool is for educational purposes only. Users are responsible for complying with Roblox's Terms of Service. The developers are not responsible for any consequences resulting from the use of this tool.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## Security Notes

- Accounts are stored locally in `saved_accounts.json`
- Cookies are stored in plain text (consider encrypting for production use)
- Temporary browser profiles are automatically cleaned up
- No data is sent to external servers

## Troubleshooting

### Browser Won't Open
- Ensure Google Chrome is installed
- Check that ChromeDriver is compatible with your Chrome version
- Restart the application (ChromeDriver auto-updates)

### Login Not Detected
- Make sure you complete the full login process
- Wait for the page to fully load after login
- The detection timeout is 5 minutes (300 seconds)

### Import Errors
- Install all requirements: `pip install -r requirements.txt`
- Ensure you're using Python 3.7 or newer

## Security Notes

- Accounts are stored locally in `saved_accounts.json`
- Cookies are stored in plain text
- Temporary browser profiles are automatically cleaned up
- No data is sent to external servers

## Advanced Usage

### Programmatic Access

You can use the `RobloxAccountManager` class in your own scripts:

```python
from roblox_account_manager import RobloxAccountManager

manager = RobloxAccountManager()

# Get a saved cookie
cookie = manager.get_account_cookie("username")

# Validate an account
is_valid = manager.validate_account("username")

# Add account programmatically
success = manager.add_account()
```

### Cookie Format

Saved accounts are stored in this format:
```json
{
  "username": {
    "username": "actual_username",
    "cookie": "roblosecurity_cookie_value",
    "added_date": "2025-01-15 14:30:22"
  }
}
```
