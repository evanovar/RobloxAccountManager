"""
Roblox Account Manager
Main entry point for the application
"""
# hello guys! Do you wanna know how does the Multi Instance work?
# check out utils/ui.py, enable_multi_roblox function. Have a nice day!
# if you find it helpful, consider starring the repo!

import os
import warnings
import tkinter as tk
from tkinter import messagebox, simpledialog

warnings.filterwarnings("ignore")

from classes import RobloxAccountManager
from classes.encryption import EncryptionConfig
from utils.encryption_setup import setup_encryption
from utils.ui import AccountManagerUI


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
    app = AccountManagerUI(root, manager)
    root.mainloop()


if __name__ == "__main__":
    main()
