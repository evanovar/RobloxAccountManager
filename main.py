"""
Roblox Account Manager
Main entry point for the application
"""

# if you find this tool helpful, consider starring the repo!

import os
import warnings
import tkinter as tk
from tkinter import messagebox, simpledialog
import requests
import threading

warnings.filterwarnings("ignore")

from classes import RobloxAccountManager
from classes.encryption import EncryptionConfig
from utils.encryption_setup import setup_encryption
from utils.ui import AccountManagerUI


def setup_icon(data_folder):
    icon_path = os.path.join(data_folder, "icon.ico")
    
    if os.path.exists(icon_path):
        return icon_path
    
    try:
        print("[INFO] Downloading application icon...")
        icon_url = "https://github.com/evanovar/RobloxAccountManager/raw/main/icon.ico"
        response = requests.get(icon_url, timeout=5)
        
        if response.status_code == 200:
            with open(icon_path, 'wb') as f:
                f.write(response.content)
                print("[SUCCESS] Icon downloaded successfully.")
            return icon_path
        else:
            print(f"[ERROR] Failed to download icon: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"[ERROR] Error downloading icon: {e}")
        return None


def apply_icon_to_window(window, icon_path):
    if icon_path and os.path.exists(icon_path):
        try:
            window.iconbitmap(icon_path)
        except Exception as e:
            print(f"[ERROR] Could not set window icon: {e}")


def apply_icon_async(root, data_folder):
    icon_path = os.path.join(data_folder, "icon.ico")
    
    if os.path.exists(icon_path):
        apply_icon_to_window(root, icon_path)
        return icon_path
    
    def download_icon():
        try:
            setup_icon(data_folder)
        except:
            pass
    
    thread = threading.Thread(target=download_icon, daemon=True)
    thread.start()
    
    return None


def main():
    """Main application entry point"""
    password = setup_encryption()
    
    data_folder = "AccountManagerData"
    if not os.path.exists(data_folder):
        os.makedirs(data_folder)
        
    encryption_config = EncryptionConfig(os.path.join(data_folder, "encryption_config.json"))
    
    if encryption_config.is_encryption_enabled() and encryption_config.get_encryption_method() == 'password':
        if password is None:
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
        messagebox.showerror("Error", "Password is invalid. Please try again.")
        return
    except Exception as e:
        messagebox.showerror("Error", f"Failed to initialize: {e}")
        return
    
    root = tk.Tk()
    root.withdraw()
    
    icon_path = apply_icon_async(root, data_folder)
    app = AccountManagerUI(root, manager, icon_path=icon_path)
    
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()