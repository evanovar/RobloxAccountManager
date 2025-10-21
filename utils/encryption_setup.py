"""
Encryption setup and configuration utilities
"""

import os
import hashlib
from classes.encryption import EncryptionConfig, PasswordEncryption
from utils.ui_helpers import Colors, colored_text, get_password_with_asterisks


def setup_encryption():
    """First-time encryption setup"""
    encryption_config = EncryptionConfig()
    
    if not encryption_config.is_encryption_enabled():
        os.system('cls' if os.name == 'nt' else 'clear')
        print("="*60)
        print("🔐 FIRST-TIME SETUP: ENCRYPTION CONFIGURATION")
        print("="*60)
        print()
        print("To protect your account data, please choose an encryption method:")
        print()
        print("1. Hardware Encryption (Automatic, Non-Portable)")
        print("   • Automatic encryption using your computer's hardware")
        print("   • No password needed")
        print("   • Data ONLY works on THIS computer")
        print("   • Cannot be transferred or backed up to cloud")
        print()
        print("2. Password Encryption (Recommended, Portable)")
        print("   • Encrypt with a password you create")
        print("   • Can backup to cloud (Google Drive, Dropbox, etc.)")
        print("   • Works on any computer with the password")
        print("   • MUST remember your password - no recovery!")
        print()
        print("3. No Encryption (Not Recommended)")
        print("   • Store accounts without any encryption")
        print("   • Easy to transfer and backup")
        print("   • WARNING: Anyone with access to files can see your data")
        print("   • WARNING: Not secure if computer is compromised")
        print()
        print("-" * 60)
        
        while True:
            choice = input("Select encryption method (1, 2, or 3): ").strip()
            
            if choice == '1':
                encryption_config.enable_hardware_encryption()
                print()
                print(colored_text("[SUCCESS] Hardware-based encryption enabled!", Colors.GREEN))
                print("🔒 Your accounts will be encrypted automatically.")
                print()
                input("Press Enter to continue...")
                os.system('cls' if os.name == 'nt' else 'clear')
                return None
                
            elif choice == '2':
                os.system('cls' if os.name == 'nt' else 'clear')
                print("="*60)
                print("🔐 PASSWORD ENCRYPTION SETUP")
                print("="*60)
                print()
                print(colored_text("[WARNING] IMPORTANT WARNING", Colors.YELLOW))
                print("PLEASE SAVE YOUR PASSWORD. DO NOT FORGET IT!")
                print("There is NO password recovery method.")
                print("Lost password = permanent data loss!")
                print()
                
                while True:
                    try:
                        password1 = get_password_with_asterisks("Enter your password: ")
                    except KeyboardInterrupt:
                        print()
                        return setup_encryption()
                    
                    if len(password1) < 8:
                        print(colored_text("[WARNING] Password must be at least 8 characters long.", Colors.YELLOW))
                        print()
                        continue
                    
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print("="*60)
                    print("🔐 PASSWORD ENCRYPTION SETUP")
                    print("="*60)
                    print()
                    
                    try:
                        password2 = get_password_with_asterisks("Confirm your password: ")
                    except KeyboardInterrupt:
                        print()
                        return setup_encryption()
                    
                    if password1 == password2:
                        temp_encryptor = PasswordEncryption(password1)
                        salt_b64 = temp_encryptor.get_salt_b64()
                        password_hash = hashlib.sha256(password1.encode()).hexdigest()
                        encryption_config.enable_password_encryption(salt_b64, password_hash)
                        
                        os.system('cls' if os.name == 'nt' else 'clear')
                        print()
                        print(colored_text("[SUCCESS] Password encryption enabled successfully!", Colors.GREEN))
                        print("🔒 Your accounts will be encrypted with your password.")
                        print()
                        print(colored_text("[WARNING] Remember: Your password is NOT stored anywhere.", Colors.YELLOW))
                        print("   You will need to enter it every time you start the app.")
                        print()
                        input("Press Enter to continue...")
                        os.system('cls' if os.name == 'nt' else 'clear')
                        return password1
                    else:
                        os.system('cls' if os.name == 'nt' else 'clear')
                        print()
                        print(colored_text("[ERROR] Passwords do not match!", Colors.RED))
                        print(colored_text("[WARNING] Returning to encryption setup...", Colors.YELLOW))
                        print()
                        input("Press Enter to continue...")
                        return setup_encryption()
                        
            elif choice == '3':
                os.system('cls' if os.name == 'nt' else 'clear')
                print()
                print(colored_text("[WARNING] You are about to disable encryption!", Colors.YELLOW))
                print()
                print("Your account data will be stored in PLAIN TEXT.")
                print("Anyone with access to your files can read your cookies.")
                print()
                confirm = input("Are you sure? Type 'YES' to confirm: ").strip()
                
                if confirm == 'YES':
                    encryption_config.disable_encryption()
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print()
                    print(colored_text("[SUCCESS] Encryption disabled.", Colors.GREEN))
                    print("Your accounts will be stored without encryption.")
                    print()
                    input("Press Enter to continue...")
                    os.system('cls' if os.name == 'nt' else 'clear')
                    return None
                else:
                    print()
                    print("Cancelled. Returning to encryption setup...")
                    print()
                    input("Press Enter to continue...")
                    return setup_encryption()
                        
            else:
                print(colored_text("[WARNING] Invalid choice. Please enter 1, 2, or 3.", Colors.YELLOW))
