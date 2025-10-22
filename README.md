# 🚀 Roblox Account Manager

A powerful tool for managing multiple Roblox accounts with secure cookie extraction, featuring both Console and UI modes. <br>
Created by evanovar · Contact: Discord (same username as on GitHub). <br>
⭐ If you like this project, please consider starring the repository! ⭐<br>

## ✨ Features

### 🎨 Dual Interface
- **Console Mode**: Fast, lightweight text-based interface
- **UI Mode**: Modern graphical interface with advanced features
- Choose your preferred mode on first launch

### 🖥️ UI Mode Features
- **Modern Dark Theme**: Easy on the eyes with a sleek dark interface
- **Account Management**: Visual list of all your accounts with encryption status
- **Game List**: Save up to 10 recently played games with Place IDs
- **Private Server Support**: Save and launch private servers with [P] indicator
- **Real-time Game Names**: Automatically fetches game names from Roblox API
- **Quick Actions**: Validate accounts, refresh lists, and more
- **Launch Options**: 
  - Launch Roblox to home page via Chrome (with account logged in)
  - Join specific games with Place ID
  - Join private servers with link codes
- **Persistent Settings**: Automatically saves Place IDs, Private Server codes, and game list

### 📦 Console Mode Features
- Fast and responsive performance
- Low resource usage
- All core account management features
- Perfect for automation and scripting

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
   python main.py
   ```
   
## 📋 Requirements

The following Python packages are required:
- `selenium` - Browser automation
- `requests` - HTTP requests for account validation and game info
- `webdriver-manager` - Automatic ChromeDriver management
- `pycryptodome` - Encryption and cookie handling
- `tkinter` - GUI interface (usually included with Python)

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

**Q: What's the difference between Console and UI mode?**  
A: 
- **Console Mode**: Fast, text-based interface. Uses less resources, ideal for automation.
- **UI Mode**: Graphical interface with extra features like game list, real-time game names, visual account management, and persistent settings.

**Q: Can I switch between Console and UI mode?**  
A: Yes! Just delete `version_config.json` and restart the program. You'll be asked to choose again.

**Q: What is the Game List feature?**  
A: UI mode automatically saves the last 10 games you've launched (with Place IDs and Private Server codes). Click any game in the list to quickly load it again.

**Q: What does [P] mean in the game list?**  
A: [P] indicates that the game was saved with a private server link code. Clicking it will load both the Place ID and Private Server ID.

**Q: Will you add Multi Instance Support?**  
A: I'll add it if I figure out how to make it work. If I can't, then probably not.

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
