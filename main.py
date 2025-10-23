"""
Roblox Account Manager
Main entry point for the application

A secure account manager for Roblox with encryption support,
browser automation for account addition, and game launching capabilities.
"""

import os
import ctypes
import warnings
import tkinter as tk
from tkinter import messagebox, simpledialog

warnings.filterwarnings("ignore")
os.environ['WDM_LOG_LEVEL'] = '0'

try:
    ctypes.windll.kernel32.SetConsoleTitleW("Roblox Account Manager")
except:
    pass

from classes import RobloxAccountManager
from classes.encryption import EncryptionConfig
from utils.encryption_setup import setup_encryption
from utils.version_selector import VersionSelector
from utils.ui_helpers import Colors, colored_text, get_password_with_asterisks


def main_console(manager):
    """Console version main loop"""
    encryption_status = ""
    if manager.encryption_config.is_encryption_enabled():
        method = manager.encryption_config.get_encryption_method()
        if method == 'hardware':
            encryption_status = " 🔒 [Hardware Encrypted]"
        elif method == 'password':
            encryption_status = " 🔐 [Password Encrypted]"
    
    while True:
        print("\n" + "="*50)
        print(f"🚀 ROBLOX ACCOUNT MANAGER{encryption_status}")
        print("="*50)
        print("1. Add new account")
        print("2. List saved accounts")
        print("3. Delete account")
        print("4. Validate account")
        print("5. Launch Roblox game")
        print("6. Exit")
        print("-" * 50)
        
        choice = input("Select an option (1-6): ").strip()
        
        if choice == '1':
            print("\n🚀 Adding new account...")
            manager.add_account()
            
        elif choice == '2':
            manager.list_accounts()
            
        elif choice == '3':
            manager.list_accounts()
            if manager.accounts:
                account_num = input("\n🔢 Enter account number to delete: ").strip()
                username = manager.get_account_by_number(account_num)
                if username:
                    confirm = input(f"⚠️ Are you sure you want to delete '{username}'? (y/n): ").strip().lower()
                    if confirm == 'y':
                        manager.delete_account(username)
                    else:
                        print("❌ Deletion cancelled.")
                else:
                    print(colored_text("[ERROR] Invalid account number", Colors.RED))
            
        elif choice == '4':
            manager.list_accounts()
            if manager.accounts:
                account_num = input("\n🔢 Enter account number to validate: ").strip()
                username = manager.get_account_by_number(account_num)
                if username:
                    is_valid = manager.validate_account(username)
                else:
                    print(colored_text("[ERROR] Invalid account number", Colors.RED))
            else:
                print("No accounts to validate.")
            
        elif choice == '5':
            manager.list_accounts()
            if manager.accounts:
                account_num = input("\n🔢 Enter account number to launch with: ").strip()
                username = manager.get_account_by_number(account_num)
                if username:
                    game_id = input("🎮 Enter Game/Place ID: ").strip()
                    private_server = input("🔑 Enter Private Server ID (leave blank for public): ").strip()
                    
                    if game_id.isdigit():
                        success = manager.launch_roblox(username, game_id, private_server)
                        if success:
                            print("🎮 Check your desktop - Roblox should be launching!")
                    else:
                        print(colored_text("[ERROR] Invalid Game ID. Please enter a valid number.", Colors.RED))
                else:
                    print(colored_text("[ERROR] Invalid account number", Colors.RED))
            else:
                print("No accounts available to launch with.")
            
        elif choice == '6':
            print("Goodbye!")
            break
            
        else:
            print(colored_text("[ERROR] Invalid option. Please try again.", Colors.RED))


def main_ui(manager):
    """UI version main loop"""
    from utils.ui import AccountManagerUI
    
    root = tk.Tk()
    app = AccountManagerUI(root, manager)
    root.mainloop()


def main():
    """Main application entry point"""
    password = setup_encryption()
    
    version_selector = VersionSelector()
    
    if not version_selector.has_preference():
        version = version_selector.prompt_version_choice()
    else:
        version = version_selector.get_preference()
        print(f"\n✓ Launching {version.upper()} mode...")
    
    encryption_config = EncryptionConfig()
    
    if encryption_config.is_encryption_enabled() and encryption_config.get_encryption_method() == 'password':
        if password is None:
            if version == 'console':
                print()
                print("🔐 Password-encrypted accounts detected")
                print()
                try:
                    password = get_password_with_asterisks("Enter your password to unlock: ")
                except KeyboardInterrupt:
                    print()
                    print(colored_text("[ERROR] Cancelled by user", Colors.RED))
                    return
                print()
            else:
                root = tk.Tk()
                root.withdraw()
                password = simpledialog.askstring("Password Required", "Enter your password to unlock:", show='*')
                root.destroy()
                
                if password is None:
                    messagebox.showerror("Error", "Password is required to access encrypted accounts.")
                    return
    
    try:
        manager = RobloxAccountManager(password=password)
    except ValueError as e:
        if version == 'console':
            print()
            print(colored_text("[ERROR] Password is invalid. Please try again.", Colors.RED))
            print()
            input("Press Enter to exit...")
        else:
            messagebox.showerror("Error", "Password is invalid. Please try again.")
        return
    except Exception as e:
        if version == 'console':
            print()
            print(colored_text(f"[ERROR] Failed to initialize: {e}", Colors.RED))
            print()
            input("Press Enter to exit...")
        else:
            messagebox.showerror("Error", f"Failed to initialize: {e}")
        return
    
    if version == 'console':
        main_console(manager)
    else:
        main_ui(manager)


if __name__ == "__main__":
    main()
