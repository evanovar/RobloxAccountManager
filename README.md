# 🚀 Roblox Account Manager

A fast, lightweight console-based tool for managing multiple Roblox accounts with **ultra-fast browser detection** and secure cookie extraction.

## ✨ Features

- **⚡ Ultra-Fast Detection** - 25ms login detection speed
- **🔒 Secure Storage** - Local JSON storage of account credentials
- **🎮 Game Launching** - Direct game launching with specific Game IDs
- **✅ Account Validation** - Check account status and validity
- **🖥️ Simple Console Interface** - Clean, easy-to-use command-line interface
- **🚀 Instant Browser Closure** - Browser closes immediately after login detection

## 🛠️ Installation

### Prerequisites
- **Python 3.7+**
- **Google Chrome browser**
- **Windows** (currently optimized for Windows)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/evanovar/roblox-account-manager.git
   cd roblox-account-manager
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
4. **⚡ Instant Detection**: Tool detects successful login in **25ms**
5. **🚀 Auto-Close**: Browser closes immediately after detection
6. **💾 Saved**: Username and authentication cookie are saved locally

### Menu Options

- **1. Add new account** - Ultra-fast browser automation for account addition
- **2. List saved accounts** - View all saved accounts with registration dates  
- **3. Delete account** - Remove accounts from the manager
- **4. Validate account** - Check if saved account cookies are still valid
- **5. Launch Roblox game** - Launch specific games or Roblox directly
- **6. Exit** - Close the application

## ⚠️ Disclaimer

This tool is for educational purposes only. Users are responsible for complying with Roblox's Terms of Service. The developers are not responsible for any consequences resulting from the use of this tool.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## 🔧 Troubleshooting

### Common Issues

- **ChromeDriver not found**: The tool automatically downloads ChromeDriver, ensure you have an internet connection
- **Browser doesn't open**: Make sure Chrome is installed and accessible
- **Login not detected**: Ensure you complete the login process fully before the browser closes

### Support

If you encounter any issues, please open an issue on GitHub with:
- Your operating system
- Python version
- Error message (if any)
- Steps to reproduce the problem
5. **Exit**: Close the application

### Adding an Account

1. Select option 1 from the main menu
2. Chrome browser opens automatically with optimized performance
3. Log into your Roblox account normally
4. Browser automatically closes in **25ms** after login detection
5. Account saved with username and authentication cookie

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
- Cookies are stored in plain text (consider encrypting for production use)
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

## Contributing

Feel free to submit issues, fork the repository, and create pull requests for any improvements.

## Disclaimer

This tool is for educational and personal use only. Always comply with Roblox's Terms of Service. The developers are not responsible for any misuse of this tool.
