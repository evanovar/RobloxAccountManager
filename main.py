"""
Roblox Account Manager
Main entry point for the application

A secure account manager for Roblox with encryption support,
browser automation for account addition, and game launching capabilities.
"""

import os
import ctypes
import warnings

warnings.filterwarnings("ignore")
os.environ['WDM_LOG_LEVEL'] = '0'

try:
    ctypes.windll.kernel32.SetConsoleTitleW("Roblox Account Manager")
except:
    pass

from classes import RobloxAccountManager
from classes.encryption import EncryptionConfig
from utils.ui_helpers import Colors, colored_text, get_password_with_asterisks
from utils.encryption_setup import setup_encryption


def main():
    """Main application loop"""
    password = setup_encryption()
    
    encryption_config = EncryptionConfig()
    
    if encryption_config.is_encryption_enabled() and encryption_config.get_encryption_method() == 'password':
        if password is None:
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
    
    try:
        manager = RobloxAccountManager(password=password)
    except ValueError as e:
        print()
        print(colored_text("[ERROR] Password is invalid. Please try again.", Colors.RED))
        print()
        input("Press Enter to exit...")
        return
    except Exception as e:
        print()
        print(colored_text(f"[ERROR] Failed to initialize: {e}", Colors.RED))
        print()
        input("Press Enter to exit...")
        return
    
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
                username = input("\nEnter username to delete: ").strip()
                manager.delete_account(username)
            
        elif choice == '4':
            manager.list_accounts()
            if manager.accounts:
                username = input("\nEnter username to validate: ").strip()
                is_valid = manager.validate_account(username)
            else:
                print("No accounts to validate.")
            
        elif choice == '5':
            manager.list_accounts()
            if manager.accounts:
                username = input("\nEnter username to launch with: ").strip()
                if username in manager.accounts:
                    game_id = input("Enter Game/Place ID: ").strip()
                    private_server = input("Enter Private Server ID (leave blank for public): ").strip()
                    
                    if game_id.isdigit():
                        success = manager.launch_roblox(username, game_id, private_server)
                        if success:
                            print("🎮 Check your desktop - Roblox should be launching!")
                    else:
                        print("✗ Invalid Game ID. Please enter a valid number.")
                else:
                    print(f"✗ Account '{username}' not found")
            else:
                print("No accounts available to launch with.")
            
        elif choice == '6':
            print("Goodbye!")
            break
            
        else:
            print(colored_text("[ERROR] Invalid option. Please try again.", Colors.RED))


if __name__ == "__main__":
    main()
