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
    from utils.ui import AccountManagerUI

    root = tk.Tk()
    app = AccountManagerUI(root, manager)
    root.mainloop()

def main():
