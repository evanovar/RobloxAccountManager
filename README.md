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
3. Put it in a folder (optional)
4. Double-click to run - that's it!

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
   
## 📋 Requirements

The following Python packages are required:
- `selenium` - Browser automation
- `requests` - HTTP requests for account validation  
- `webdriver-manager` - Automatic ChromeDriver management
- `pycryptodome` - Encryption and cookie handling
- `pywin32` - Windows-specific functionality

## 🔐 Encryption & Security

### First-Time Setup

On first launch, you'll be prompted to choose an encryption method to protect your account data:

**1. Default Encryption (Hardware-Based)** ✅ Available Now
- ✅ Automatic encryption using your computer's unique hardware ID
- ✅ No passwords to remember
- ✅ Zero user interaction needed after setup
- ⚠️ **Data ONLY works on THIS computer**
- ⚠️ **Cannot transfer to another machine or backup to cloud**
- ⚠️ **Hardware changes may make data unrecoverable**

**2. Password Encryption** 🚧 Coming Soon
- Under development
- Will support cloud backup and multi-device sync

### How It Works

1. **First Launch**: Choose encryption method (currently only Hardware-Based available)
2. **Automatic Protection**: All account data in `saved_accounts.json` is encrypted
3. **Transparent Usage**: Encryption/decryption happens automatically in the background
4. **Status Display**: Main menu shows `🔒 [Hardware Encrypted]` when active

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

### Encryption/Decryption Issues
- If you get "Decryption failed" error, your data may have been encrypted on a different computer
- Hardware-based encryption is tied to your specific machine
- Reinstalling Windows or changing hardware (CPU, motherboard) will break decryption
- **There is no recovery method** - always backup your unencrypted data before major system changes

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

**Unencrypted** (if encryption is disabled):
```json
{
  "username": {
    "username": "actual_username",
    "cookie": "roblosecurity_cookie_value",
    "added_date": "2025-01-15 14:30:22"
  }
}
```

**Encrypted** (with hardware-based encryption):
```json
{
  "encrypted": true,
  "data": {
    "nonce": "nonce",
    "tag": "tag",
    "ciphertext": "encrypted_data"
  }
}
```

## 🛡️ Security Best Practices

- ✅ **Always use encryption** - Choose hardware-based encryption on first launch
- ✅ **Keep your system secure** - Use Windows Defender and keep it updated
- ✅ **Don't share the EXE or files** - Your encrypted data is tied to your machine
- ⚠️ **Backup before hardware changes** - Export accounts before upgrading PC
- ⚠️ **Never share `saved_accounts.json`** - Even encrypted, it's tied to your hardware
- ❌ **Don't use on shared computers** - Each user should have their own installation
