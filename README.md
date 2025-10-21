# 🚀 Roblox Account Manager

A fast, lightweight console tool for managing multiple Roblox accounts with secure cookie extraction. <br>
Created by evanovar · Contact: Discord (same username as on GitHub). <br>
⭐ If you like this project, please consider starring the repository! ⭐<br>

<img width="1108" height="616" alt="image" src="https://github.com/user-attachments/assets/c638d36b-671c-4b6b-a023-a2f79c075612" />


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

## 🔐 Encryption & Security

There are 3 Encryption methods:

**1. Hardware Encryption (Hardware-Based)**
- ✅ Automatic encryption using your computer's unique hardware ID
- ⚠️ **Data ONLY works on THIS computer**
- ⚠️ **Hardware changes may make data unrecoverable**
  
**2. Password Encryption (Reccomended, Portable)**
- ✅ Encrypt with a password you create
- ✅ **Can backup to cloud** (Google Drive, Dropbox, OneDrive, etc.)
- ⚠️ **MUST remember your password** - there is NO recovery method!

**3. No Encryption (Not Reccomended)**
- ✅ Store accounts without any encryption
- ✅ Easy to transfer and backup
- ⚠️ **NOT SECURE** - Anyone with access to files can see your data

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

This project is open source and available under the [GPL 3.0 License](LICENSE).

## 📚 Frequently Asked Questions (FAQ)

### General Questions

**Q: Is this tool safe to use?**  
A: Yes, the tool runs entirely locally on your computer. No data is sent to external servers. However, you're responsible for following Roblox's Terms of Service.

**Q: Do I need Python installed to use the EXE version?**  
A: No! The standalone EXE includes everything you need. Just download and run.

**Q: Can I use this on Mac or Linux?**  
A: Currently, this tool is optimized for Windows only. Some features (like asterisk password input) use Windows-specific modules (`msvcrt`).

**Q: Will you add Multi Instance Support?**  
A: I’ll add it if I figure out how to make it work. If I can’t, then probably not.

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
