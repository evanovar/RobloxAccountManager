# 🚀 Roblox Account Manager

A powerful tool for managing multiple Roblox accounts with secure cookie extraction and modern UI interface. <br>
Created by evanovar · Contact: Discord (same username as on GitHub). <br>
⭐ If you like this project, please consider starring the repository! ⭐<br>

<img width="446" height="528" alt="image" src="https://github.com/user-attachments/assets/e01fabc2-473a-4da8-9853-1729ebbf5561" />
<img width="298" height="347" alt="image" src="https://github.com/user-attachments/assets/686747b4-1caf-47db-a1f6-8f06469c65d2" />


## ✨ Features

### 🎨 Modern UI Interface
- **Dark Theme**: Sleek, modern interface easy on the eyes
- **Encryption Status Display**: Color-coded status showing your security level
  - 🔐 **[PASSWORD ENCRYPTED]** - Light blue
  - 🔒 **[HARDWARE ENCRYPTED]** - Light green
  - ⚠️ **[NOT ENCRYPTED]** - Light pink
- **Visual Account Management**: See all your accounts at a glance

### 🖥️ Feature-Rich Interface
- **Account Management**: Visual list of all your accounts with encryption status
- **Multi Roblox Support**: Run multiple Roblox instances on the same device
- **Import Cookie Feature**: Add accounts quickly using `.ROBLOSECURITY` cookie
- **Game List**: Save up to 50 recently played games with Place IDs (configurable)
- **Private Server Support**: Save and launch private servers with [P] indicator
- **Persistent Settings**: Automatically saves Place IDs, Private Server codes, game list, and preferences

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

### Method 2: Clone Repository (For Developers)

**Full source code access and customization**

**Requirements:**
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

On first launch, you'll be prompted to choose an encryption method through a modern UI:

### Encryption Methods

**1. Hardware Encryption (Not Portable)**
- ✅ Automatic encryption using your computer's unique hardware ID
- ✅ No password needed - completely automatic
- ⚠️ **Data ONLY works on THIS computer**
- ⚠️ **Cannot be backed up to cloud**
  
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

**Q: Do I need Python installed to use the EXE version?**  
A: No! The standalone EXE includes everything you need. Just download and run.

**Q: Can I use this on Mac or Linux?**  
A: Currently, this tool is optimized for Windows only.

**Q: What does [P] mean in the game list?**  
A: [P] indicates that the game was saved with a private server link code. Clicking it will load both the Place ID and Private Server ID.

**Q: What is Multi Roblox?**  
A: Multi Roblox allows you to run multiple Roblox instances simultaneously on the same machine. Enable it in Settings, and you can launch multiple games at once.

**Q: How do I import accounts using cookies?**  
A: Open Settings window and click "Import Cookie". Paste your `.ROBLOSECURITY` cookie from Chrome/browser, and the tool will automatically get the username and add the account. The cookie is encrypted and stored securely.

**Q: Where are my data files stored?**  
A: All configuration and account data are stored in the `AccountManagerData` folder in the same directory as the program. This includes:
- `saved_accounts.json` - Your encrypted account data
- `encryption_config.json` - Encryption settings
- `ui_settings.json` - UI preferences and game list

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
A: Yes! Simply copy the entire `AccountManagerData` folder to the new computer, install the app, and enter your password. This folder contains `saved_accounts.json` and `encryption_config.json`.

### Account Management Questions

**Q: How many accounts can I save?**  
A: There's no hard limit. You can save as many accounts as you need.

**Q: Do saved accounts expire?**  
A: Roblox cookies can expire after long periods of inactivity or if you change your password on Roblox's website. Use the "Validate account" feature to check if an account is still valid.

**Q: Can I transfer accounts between different instances of the tool?**  
A: 
- **Hardware encryption**: No, tied to one machine only
- **Password encryption**: Yes, copy the entire `AccountManagerData` folder, then use same password

**Q: What happens if I change my Roblox password?**  
A: Your saved cookie will become invalid. You'll need to delete the old account from the manager and re-add it with the new login.
