"""
Encryption setup
"""

import sys
import os
import json
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox
from classes.encryption import EncryptionConfig, PasswordEncryption


class ToolTip:
    """
    Create a tooltip for a given widget
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
    
    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.text:
            return
        
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(
            tw,
            text=self.text,
            justify='left',
            background="#2b2b2b",
            foreground="white",
            relief='solid',
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=10,
            pady=5
        )
        label.pack()
    
    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class EncryptionSetupUI:
    """UI for encryption setup"""
    
    def __init__(self):
        self.result = None
        self.data_folder = "AccountManagerData"
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
        self.encryption_config = EncryptionConfig(os.path.join(self.data_folder, "encryption_config.json"))
        self.should_exit = False
        
        settings_file = os.path.join(self.data_folder, "ui_settings.json")
        settings = {}
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
            except:
                pass
        
        self.BG_DARK = settings.get("theme_bg_dark", "#2b2b2b")
        self.BG_MID = settings.get("theme_bg_mid", "#3a3a3a")
        self.BG_LIGHT = settings.get("theme_bg_light", "#4b4b4b")
        self.FG_TEXT = settings.get("theme_fg_text", "white")
        self.FG_ACCENT = settings.get("theme_fg_accent", "#0078D7")
    
    def setup_encryption_ui(self):
        """Show encryption setup UI and return password if needed"""
        if self.encryption_config.is_setup_complete():
            return None
        
        root = tk.Tk()
        root.title("Encryption Setup")
        root.geometry("500x300")
        root.configure(bg=self.BG_DARK)
        root.resizable(False, False)
        
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        def on_close():
            self.should_exit = True
            root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_close)
        
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        
        main_frame = ttk.Frame(root, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        title_label = ttk.Label(
            main_frame,
            text="Please choose your encryption method:",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        )
        title_label.pack(pady=(0, 30))
        
        button_style = {
            'width': 35,
            'height': 2,
            'font': ('Segoe UI', 10),
            'bg': self.BG_MID,
            'fg': self.FG_TEXT,
            'activebackground': self.BG_LIGHT,
            'activeforeground': self.FG_TEXT,
            'relief': 'flat',
            'bd': 1,
            'highlightthickness': 1,
            'highlightbackground': self.BG_LIGHT,
            'highlightcolor': self.FG_ACCENT
        }
        
        btn_hardware = tk.Button(
            main_frame,
            text="Hardware Encryption (Not Portable)",
            command=lambda: self.select_hardware_encryption(root),
            **button_style
        )
        btn_hardware.pack(pady=8)
        ToolTip(btn_hardware, "Encrypted with your computer's hardware\nNo password required • Fully automatic\nNot portable to other computers")
        
        btn_password = tk.Button(
            main_frame,
            text="Password Encryption (Recommended)",
            command=lambda: self.select_password_encryption(root),
            **button_style
        )
        btn_password.pack(pady=8)
        ToolTip(btn_password, "Encrypted with your password\nPortable across computers\nNo password recovery available")
        
        btn_none = tk.Button(
            main_frame,
            text="No Encryption (Not Recommended)",
            command=lambda: self.select_no_encryption(root),
            **button_style
        )
        btn_none.pack(pady=8)
        ToolTip(btn_none, "No encryption applied\nEasy to transfer files\nNot secure - cookies stored in plain text")
        
        root.mainloop()
        
        if self.should_exit:
            sys.exit(0)
        
        return self.result
    
    def select_hardware_encryption(self, root):
        """Handle hardware encryption selection"""
        confirm = messagebox.askyesno(
            "⚠️ Confirm Hardware Encryption",
            "This method is tied to your computer's hardware and does not require a password.\n"
            "It is NOT portable to other computers.\n\n"
            "Are you sure you want to enable hardware-based encryption?"
        )

        if confirm:
            self.encryption_config.enable_hardware_encryption()
            messagebox.showinfo(
                "Success",
                "Hardware-based encryption enabled!\n\n🔒 Your accounts will be encrypted automatically."
            )
            self.result = None
            root.destroy()
    
    def select_password_encryption(self, root):
        """Handle password encryption selection - Step 1: Enter Password"""
        root.withdraw()
        
        password_window = tk.Toplevel()
        password_window.title("Password Setup - Enter Password")
        password_window.geometry("450x240")
        password_window.configure(bg=self.BG_DARK)
        password_window.resizable(False, False)
        
        password_window.update_idletasks()
        width = password_window.winfo_width()
        height = password_window.winfo_height()
        x = (password_window.winfo_screenwidth() // 2) - (width // 2)
        y = (password_window.winfo_screenheight() // 2) - (height // 2)
        password_window.geometry(f'{width}x{height}+{x}+{y}')
        
        style = ttk.Style()
        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        style.configure("Dark.TEntry", fieldbackground=self.BG_MID, background=self.BG_MID, foreground=self.FG_TEXT)
        
        frame = ttk.Frame(password_window, style="Dark.TFrame")
        frame.pack(fill="both", expand=True, padx=30, pady=20)
        
        warning_label = ttk.Label(
            frame,
            text="⚠️ IMPORTANT WARNING",
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold"),
            foreground="#FFD700"
        )
        warning_label.pack(pady=(0, 8))
        
        info_label = ttk.Label(
            frame,
            text="Please save your password. There is NO recovery method!\nLost password = permanent data loss!",
            style="Dark.TLabel",
            justify="center"
        )
        info_label.pack(pady=(0, 15))
        
        ttk.Label(frame, text="Enter your password:", style="Dark.TLabel").pack(anchor="w")
        password_entry = ttk.Entry(frame, show="*", style="Dark.TEntry", font=("Segoe UI", 10))
        password_entry.pack(fill="x", pady=(5, 15))
        
        def next_step():
            password1 = password_entry.get()
            
            if len(password1) < 8:
                messagebox.showwarning("Invalid Password", "Password must be at least 8 characters long.")
                return
            
            password_window.destroy()
            self.confirm_password_step(root, password1)
        
        def cancel_password():
            password_window.destroy()
            root.deiconify()
        
        button_frame = ttk.Frame(frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        button_style = {
            'width': 12,
            'font': ('Segoe UI', 10),
            'bg': self.BG_MID,
            'fg': self.FG_TEXT,
            'activebackground': self.BG_LIGHT,
            'activeforeground': self.FG_TEXT,
            'relief': 'flat',
            'bd': 1
        }
        
        tk.Button(button_frame, text="Next", command=next_step, **button_style).pack(side="left", expand=True, padx=5)
        tk.Button(button_frame, text="Cancel", command=cancel_password, **button_style).pack(side="right", expand=True, padx=5)
        
        password_entry.focus()
        password_window.protocol("WM_DELETE_WINDOW", cancel_password)
        
        password_window.mainloop()
    
    def confirm_password_step(self, root, password1):
        """Step 2: Confirm Password"""
        confirm_window = tk.Toplevel()
        confirm_window.title("Password Setup - Confirm Password")
        confirm_window.geometry("450x200")
        confirm_window.configure(bg=self.BG_DARK)
        confirm_window.resizable(False, False)
        
        confirm_window.update_idletasks()
        width = confirm_window.winfo_width()
        height = confirm_window.winfo_height()
        x = (confirm_window.winfo_screenwidth() // 2) - (width // 2)
        y = (confirm_window.winfo_screenheight() // 2) - (height // 2)
        confirm_window.geometry(f'{width}x{height}+{x}+{y}')
        
        style = ttk.Style()
        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        style.configure("Dark.TEntry", fieldbackground=self.BG_MID, background=self.BG_MID, foreground=self.FG_TEXT)
        
        frame = ttk.Frame(confirm_window, style="Dark.TFrame")
        frame.pack(fill="both", expand=True, padx=30, pady=20)
        
        title_label = ttk.Label(
            frame,
            text="Confirm Your Password",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        )
        title_label.pack(pady=(0, 15))
        
        ttk.Label(frame, text="Re-enter your password:", style="Dark.TLabel").pack(anchor="w")
        password_confirm_entry = ttk.Entry(frame, show="*", style="Dark.TEntry", font=("Segoe UI", 10))
        password_confirm_entry.pack(fill="x", pady=(5, 15))
        
        def final_confirm():
            password2 = password_confirm_entry.get()
            
            if password1 != password2:
                messagebox.showerror("Password Mismatch", "Passwords do not match!")
                password_confirm_entry.delete(0, tk.END)
                password_confirm_entry.focus()
                return
            
            confirm_window.destroy()
            self.final_confirmation_step(root, password1)
        
        def cancel_confirm():
            confirm_window.destroy()
            root.deiconify()
        
        button_frame = ttk.Frame(frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        button_style = {
            'width': 12,
            'font': ('Segoe UI', 10),
            'bg': self.BG_MID,
            'fg': self.FG_TEXT,
            'activebackground': self.BG_LIGHT,
            'activeforeground': self.FG_TEXT,
            'relief': 'flat',
            'bd': 1
        }
        
        tk.Button(button_frame, text="Confirm", command=final_confirm, **button_style).pack(side="left", expand=True, padx=5)
        tk.Button(button_frame, text="Cancel", command=cancel_confirm, **button_style).pack(side="right", expand=True, padx=5)
        
        password_confirm_entry.focus()
        confirm_window.protocol("WM_DELETE_WINDOW", cancel_confirm)
        
        confirm_window.mainloop()
    
    def final_confirmation_step(self, root, password):
        """Step 3: Final confirmation before saving"""
        final_window = tk.Toplevel()
        final_window.title("Password Setup - Final Confirmation")
        final_window.geometry("450x180")
        final_window.configure(bg=self.BG_DARK)
        final_window.resizable(False, False)
        
        final_window.update_idletasks()
        width = final_window.winfo_width()
        height = final_window.winfo_height()
        x = (final_window.winfo_screenwidth() // 2) - (width // 2)
        y = (final_window.winfo_screenheight() // 2) - (height // 2)
        final_window.geometry(f'{width}x{height}+{x}+{y}')
        
        style = ttk.Style()
        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        
        frame = ttk.Frame(final_window, style="Dark.TFrame")
        frame.pack(fill="both", expand=True, padx=30, pady=20)
        
        title_label = ttk.Label(
            frame,
            text="Confirm Password Setup",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        )
        title_label.pack(pady=(0, 12))
        
        message_label = ttk.Label(
            frame,
            text="Are you ready to enable password encryption?\nMake sure you have saved your password!",
            style="Dark.TLabel",
            justify="center"
        )
        message_label.pack(pady=(0, 15))
        
        def save_encryption():
            temp_encryptor = PasswordEncryption(password)
            salt_b64 = temp_encryptor.get_salt_b64()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            self.encryption_config.enable_password_encryption(salt_b64, password_hash)
            
            messagebox.showinfo(
                "Success",
                "Password encryption enabled successfully!\n\n🔒 Your accounts will be encrypted with your password."
            )
            self.result = password
            final_window.destroy()
            root.destroy()
        
        def cancel_final():
            final_window.destroy()
            root.deiconify()
        
        button_frame = ttk.Frame(frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        button_style = {
            'width': 12,
            'font': ('Segoe UI', 10),
            'bg': self.BG_MID,
            'fg': self.FG_TEXT,
            'activebackground': self.BG_LIGHT,
            'activeforeground': self.FG_TEXT,
            'relief': 'flat',
            'bd': 1
        }
        
        tk.Button(button_frame, text="Confirm", command=save_encryption, **button_style).pack(side="left", expand=True, padx=5)
        tk.Button(button_frame, text="Cancel", command=cancel_final, **button_style).pack(side="right", expand=True, padx=5)
        
        final_window.protocol("WM_DELETE_WINDOW", cancel_final)
        
        final_window.mainloop()
    
    def select_no_encryption(self, root):
        """Handle no encryption selection"""
        confirm = messagebox.askyesno(
            "⚠️ Warning",
            "Your account data will be stored in PLAIN TEXT.\n"
            "Anyone with access to your files can read your cookies.\n\n"
            "Are you sure you want to continue without encryption?"
        )
        
        if confirm:
            self.encryption_config.disable_encryption()
            messagebox.showinfo(
                "Success",
                "Encryption disabled.\nYour accounts will be stored without encryption."
            )
            self.result = None
            root.destroy()


def setup_encryption():
    """First-time encryption setup"""
    ui = EncryptionSetupUI()
    return ui.setup_encryption_ui()
