# 🚀 Roblox Account Manager

A fast, lightweight console tool for managing multiple Roblox accounts with secure cookie extraction. <br>
Created by evanovar · Contact: Discord (same username as on GitHub). <br>
⭐ If you like this project, please consider starring the repository! ⭐<br>

<img width="1108" height="616" alt="image" src="https://github.com/user-attachments/assets/c638d36b-671c-4b6b-a023-a2f79c075612" />


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

**1. Default Encryption (Hardware-Based)**
- ✅ Automatic encryption using your computer's unique hardware ID
- ✅ No passwords to remember
- ✅ Zero user interaction needed after setup
- ⚠️ **Data ONLY works on THIS computer**
- ⚠️ **Cannot transfer to another machine or backup to cloud**
- ⚠️ **Hardware changes may make data unrecoverable**
- 
**2. Password Encryption (Reccomended, Portable)**
- ✅ Encrypt with a password you create
- ✅ **Can backup to cloud** (Google Drive, Dropbox, OneDrive, etc.)
- ✅ **Works on any computer** with the password
- ✅ Transfer between devices easily
- ⚠️ **MUST remember your password** - there is NO recovery method!
- ⚠️ Password required every time you launch the app

### How It Works

**Hardware-Based Encryption:**
1. **First Launch**: Choose option 1 for Default Encryption
2. **Automatic Setup**: Encryption enabled instantly with no configuration
3. **Transparent Usage**: Encryption/decryption happens automatically
4. **Status Display**: Main menu shows `🔒 [Hardware Encrypted]`

**Password-Based Encryption:**
1. **First Launch**: Choose option 2 for Password Encryption
2. **Create Password**: Enter a strong password (minimum 8 characters)
3. **Confirm Password**: Re-enter password to confirm
4. **Every Launch**: Enter password to unlock your accounts
5. **Status Display**: Main menu shows `🔐 [Password Encrypted]`

## 🎯 Usage

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
4. Browser automatically closes
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

## 📚 Frequently Asked Questions (FAQ)

### General Questions

**Q: Is this tool safe to use?**  
A: Yes, the tool runs entirely locally on your computer. No data is sent to external servers. However, you're responsible for following Roblox's Terms of Service.

**Q: Do I need Python installed to use the EXE version?**  
A: No! The standalone EXE includes everything you need. Just download and run.

**Q: Can I use this on Mac or Linux?**  
A: Currently, this tool is optimized for Windows only. Some features (like asterisk password input) use Windows-specific modules (`msvcrt`).

**Q: Will you add Multi Instance Support?**  
A: No. Developing Multi Instance is hard, and also breaks Roblox's TOS

### Encryption Questions

**Q: I forgot my password! How do I recover my accounts?**  
A: Unfortunately, there is **NO password recovery method**. This is by design for security. Lost password = permanent data loss. Always remember your password or use hardware-based encryption instead.

**Q: Can I change from hardware encryption to password encryption?**  
A: Currently, there is no safe method. I will add this soon probably

**Q: Which encryption method should I choose?**  
A:
- **Choose Hardware Encryption if**: You only use one computer, want zero hassle, don't need cloud backups
- **Choose Password Encryption if**: You use multiple computers, want cloud backups, need portability

**Q: I changed my computer hardware and now can't access my accounts. What do I do?**  
A: Hardware-based encryption is permanently tied to your original hardware configuration. If you changed CPU/motherboard/UUID, the data is unrecoverable. This is why we recommend password encryption for long-term use.

**Q: Can I access my password-encrypted accounts on another computer?**  
A: Yes! Simply copy `saved_accounts.json` and `encryption_config.json` to the new computer, install the app, and enter your password.

### Account Management Questions

**Q: How many accounts can I save?**  
A: There's no hard limit. You can save as many accounts as you need.

**Q: Do saved accounts expire?**  
A: Roblox cookies can expire after long periods of inactivity or if you change your password on Roblox's website. Use the "Validate account" feature to check if an account is still valid.

**Q: Can I transfer accounts between different instances of the tool?**  
A: 
- **Hardware encryption**: No, tied to one machine only
- **Password encryption**: Yes, copy both `saved_accounts.json` and `encryption_config.json`, then use same password

**Q: What happens if I change my Roblox password?**  
A: Your saved cookie will become invalid. You'll need to delete the old account from the manager and re-add it with the new login.

**Q: When are you gonna develop a UI version?**  
A: Developing a UI version is hard, especially for me. If this repository manages to get enough stars and enough attention, I might consider adding a UI version.

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
