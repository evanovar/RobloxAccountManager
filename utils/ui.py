"""
UI Module for Roblox Account Manager
Contains the main AccountManagerUI class
"""

import os
import json
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import requests
import threading
import msvcrt
import ctypes
from ctypes import wintypes
import webbrowser
import time
import re
import win32event
import win32api
from datetime import datetime
import zipfile
import tempfile
import shutil
import platform
import traceback
from urllib.request import urlretrieve
from classes.roblox_api import RobloxAPI

class AccountManagerUI:
    def __init__(self, root, manager):
        self.root = root
        self.manager = manager
        self.APP_VERSION = "2.3.7"
        self._game_name_after_id = None
        self._save_settings_timer = None
        
        self.console_output = []
        self.console_window = None
        self.console_text_widget = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
        self.tooltip = None
        self.tooltip_timer = None
        
        sys.stdout = self
        sys.stderr = self
        
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass
        
        self.data_folder = "AccountManagerData"
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
        
        self.settings_file = os.path.join(self.data_folder, "ui_settings.json")
        self.load_settings()
        
        self.root.title("Roblox Account Manager - Made by evanovar")
        self.root.geometry("450x520")
        self.root.configure(bg=self.settings.get("theme_bg_dark", "#2b2b2b"))
        self.root.resizable(False, False)
        
        self.multi_roblox_handle = None
        
        self.anti_afk_thread = None
        self.anti_afk_stop_event = threading.Event()
        
        self.auto_rejoin_threads = {}
        self.auto_rejoin_stop_events = {}
        self.auto_rejoin_configs = self.settings.get("auto_rejoin_configs", {})

        self.BG_DARK = self.settings.get("theme_bg_dark", "#2b2b2b")
        self.BG_MID = self.settings.get("theme_bg_mid", "#3a3a3a")
        self.BG_LIGHT = self.settings.get("theme_bg_light", "#4b4b4b")
        self.FG_TEXT = self.settings.get("theme_fg_text", "white")
        self.FG_ACCENT = self.settings.get("theme_fg_accent", "#0078D7")
        self.FONT_FAMILY = self.settings.get("theme_font_family", "Segoe UI")
        self.FONT_SIZE = self.settings.get("theme_font_size", 10)

        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
        style.configure("Dark.TButton", background=self.BG_MID, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE - 1))
        style.map("Dark.TButton", background=[("active", self.BG_LIGHT)])
        style.configure("Dark.TEntry", fieldbackground=self.BG_MID, background=self.BG_MID, foreground=self.FG_TEXT)

        main_frame = ttk.Frame(self.root, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        header_frame = ttk.Frame(left_frame, style="Dark.TFrame")
        header_frame.pack(fill="x", anchor="w")
        
        ttk.Label(header_frame, text="Account List", style="Dark.TLabel").pack(side="left")
        
        encryption_status = ""
        encryption_color = self.FG_TEXT
        if self.manager.encryption_config.is_encryption_enabled():
            method = self.manager.encryption_config.get_encryption_method()
            if method == 'hardware':
                encryption_status = "[HARDWARE ENCRYPTED]"
                encryption_color = "#90EE90"
            elif method == 'password':
                encryption_status = "[PASSWORD ENCRYPTED]"
                encryption_color = "#87CEEB"
        else:
            encryption_status = "[NOT ENCRYPTED]"
            encryption_color = "#FFB6C1"
            
        self.encryption_label = tk.Label(
            header_frame,
            text=encryption_status,
            bg=self.BG_DARK,
            fg=encryption_color,
            font=("Segoe UI", 8, "bold")
        )
        self.encryption_label.pack(side="right", padx=(5, 0))

        list_frame = ttk.Frame(left_frame, style="Dark.TFrame")
        list_frame.pack(fill="both", expand=True)

        selectmode = tk.EXTENDED if self.settings.get("enable_multi_select", False) else tk.SINGLE
        
        self.account_list = tk.Listbox(
            list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 10),
            width=20,
            selectmode=selectmode,
        )
        self.account_list.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, command=self.account_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.account_list.config(yscrollcommand=scrollbar.set)
        
        self.drag_data = {
            "item": None, 
            "index": None, 
            "start_x": 0, 
            "start_y": 0,
            "dragging": False,
            "hold_timer": None
        }
        self.drag_indicator = None
        
        self.account_list.bind("<Button-1>", self.on_drag_start)
        self.account_list.bind("<B1-Motion>", self.on_drag_motion)
        self.account_list.bind("<ButtonRelease-1>", self.on_drag_release)

        right_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        right_frame.pack(side="right", fill="y")
        
        self.game_name_label = ttk.Label(right_frame, text="", style="Dark.TLabel", font=("Segoe UI", 9))
        self.game_name_label.pack(anchor="w", pady=(0, 5))
        
        ttk.Label(right_frame, text="Place ID", style="Dark.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.place_entry = ttk.Entry(right_frame, style="Dark.TEntry")
        self.place_entry.pack(fill="x", pady=(0, 5))
        self.place_entry.insert(0, self.settings.get("last_place_id", ""))
        self.place_entry.bind("<KeyRelease>", self.on_place_id_change)

        ttk.Label(right_frame, text="Private Server ID (Optional)", style="Dark.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.private_server_entry = ttk.Entry(right_frame, style="Dark.TEntry")
        self.private_server_entry.pack(fill="x", pady=(0, 5))
        self.private_server_entry.insert(0, self.settings.get("last_private_server", ""))
        self.private_server_entry.bind("<KeyRelease>", self.on_private_server_change)

        self.join_place_split_btn = ttk.Button(
            right_frame,
            text="Join Place ID",
            style="Dark.TButton"
        )
        self.join_place_split_btn.pack(fill="x", pady=(0, 10))
        self.join_place_split_btn.bind("<Button-1>", self.on_join_place_split_click)
        self.join_place_split_btn.bind("<Button-3>", self.on_join_place_right_click)
        self.join_place_split_btn.bind("<Enter>", self.on_join_place_hover)
        self.join_place_split_btn.bind("<Leave>", self.on_join_place_leave)
        
        recent_games_header = ttk.Frame(right_frame, style="Dark.TFrame")
        recent_games_header.pack(fill="x", anchor="w", pady=(10, 2))
        
        ttk.Label(recent_games_header, text="Recent games", style="Dark.TLabel", font=("Segoe UI", 9, "bold")).pack(side="left")
        
        self.star_btn = tk.Button(
            recent_games_header,
            text="⭐",
            bg=self.BG_DARK,
            fg="#FFD700",
            font=("Segoe UI", 10),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.open_favorites_window
        )
        self.star_btn.pack(side="left", padx=(5, 0))
        
        self.auto_rejoin_btn = tk.Button(
            recent_games_header,
            text="🔁",
            bg=self.BG_DARK,
            fg="#00BFFF",
            font=("Segoe UI", 10),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.open_auto_rejoin
        )
        self.auto_rejoin_btn.pack(side="left", padx=(5, 0))
        
        game_list_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        game_list_frame.pack(fill="both", expand=True)
        
        self.game_list = tk.Listbox(
            game_list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 9),
            height=5,
        )
        self.game_list.pack(side="left", fill="both", expand=True)
        self.game_list.bind("<<ListboxSelect>>", self.on_game_select)
        
        game_scrollbar = ttk.Scrollbar(game_list_frame, command=self.game_list.yview)
        game_scrollbar.pack(side="right", fill="y")
        self.game_list.config(yscrollcommand=game_scrollbar.set)
        
        ttk.Button(right_frame, text="Delete Selected", style="Dark.TButton", command=self.delete_game_from_list).pack(fill="x", pady=(5, 0))

        ttk.Label(right_frame, text="Quick Actions", style="Dark.TLabel").pack(anchor="w", pady=(10, 5))

        action_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        action_frame.pack(fill="x")

        ttk.Button(action_frame, text="Validate Account", style="Dark.TButton", command=self.validate_account).pack(fill="x", pady=2)
        ttk.Button(action_frame, text="Edit Note", style="Dark.TButton", command=self.edit_account_note).pack(fill="x", pady=2)
        ttk.Button(action_frame, text="Refresh List", style="Dark.TButton", command=self.refresh_accounts).pack(fill="x", pady=2)

        bottom_frame = ttk.Frame(self.root, style="Dark.TFrame")
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.add_account_split_btn = ttk.Button(
            bottom_frame,
            text="Add Account  ▼",
            style="Dark.TButton",
        )
        self.add_account_split_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.add_account_split_btn.bind("<Button-1>", self.on_add_account_split_click)
        
        self.add_account_dropdown = None
        self.add_account_dropdown_visible = False
        
        self.join_place_dropdown = None
        self.join_place_dropdown_visible = False
        
        ttk.Button(bottom_frame, text="Remove", style="Dark.TButton", command=self.remove_account).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(bottom_frame, text="Launch Roblox Home", style="Dark.TButton", command=self.launch_home).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(bottom_frame, text="Settings", style="Dark.TButton", command=self.open_settings).pack(side="left", fill="x", expand=True, padx=(2, 0))
        
        self.root.bind("<Button-1>", self.hide_dropdown_on_click_outside)
        self.root.bind("<Configure>", self.on_root_configure)
        self.root.bind("<Delete>", lambda e: self.remove_account())

        self.refresh_accounts()
        self.refresh_game_list()
        self.update_game_name()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        threading.Thread(target=self.check_for_updates, daemon=True).start()
    
    def on_closing(self):
        """Handle application closing - restore installers and exit"""
        
        if hasattr(self, 'anti_afk_stop_event'):
            self.stop_anti_afk()
        
        if hasattr(self, 'auto_rejoin_threads'):
            self.stop_all_auto_rejoin()
        
        RobloxAPI.restore_installers()
        self.root.destroy()

    def load_settings(self):
        """Load UI settings from file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {
                    "last_place_id": "",
                    "last_private_server": "",
                    "game_list": [],
                    "favorite_games": [],
                    "enable_topmost": False,
                    "enable_multi_roblox": False,
                    "confirm_before_launch": False,
                    "max_recent_games": 10,
                    "enable_multi_select": False,
                    "anti_afk_enabled": False,
                    "anti_afk_interval_minutes": 10,
                    "anti_afk_key": "w",
                    "disable_launch_popup": False,
                    "auto_rejoin_configs": {},
                    "multi_roblox_method": "default"
                }
        except:
            self.settings = {
                "last_place_id": "",
                "last_private_server": "",
                "game_list": [],
                "favorite_games": [],
                "enable_topmost": False,
                "enable_multi_roblox": False,
                "confirm_before_launch": False,
                "max_recent_games": 10,
                "enable_multi_select": False,
                "anti_afk_enabled": False,
                "anti_afk_interval_minutes": 10,
                "anti_afk_key": "w",
                "auto_rejoin_configs": {},
                "disable_launch_popup": False,
                "multi_roblox_method": "default"
            }
        
        if self.settings.get("enable_topmost", False):
            self.root.attributes("-topmost", True)
        
        if self.settings.get("enable_multi_roblox", False):
            self.root.after(100, self.initialize_multi_roblox)

    def check_for_updates(self):
        """Check for updates from GitHub releases"""
        try:
            print("[Update Checker] Checking for updates...")
            response = requests.get(
                "https://api.github.com/repos/evanovar/RobloxAccountManager/releases/latest",
                timeout=5
            )
            
            if response.status_code == 200:
                latest_release = response.json()
                latest_version = latest_release.get("tag_name", "").lstrip("v")
                
                current_clean = re.sub(r'(alpha|beta).*$', '', self.APP_VERSION, flags=re.IGNORECASE)
                latest_clean = re.sub(r'(alpha|beta).*$', '', latest_version, flags=re.IGNORECASE)
                
                current_parts = tuple(map(int, current_clean.split(".")))
                latest_parts = tuple(map(int, latest_clean.split(".")))
                
                if latest_parts > current_parts:
                    print(f"[Update Checker] New version available: {latest_version}")
                    self.root.after(0, lambda: self.show_update_notification(latest_version))
                else:
                    print(f"[Update Checker] You are on the latest version ({self.APP_VERSION})")
            else:
                print(f"[Update Checker] Failed to check for updates (Status: {response.status_code})")
                
        except Exception as e:
            print(f"[Update Checker] Error checking for updates: {str(e)}")

    def show_update_notification(self, latest_version):
        """Show update notification dialog"""
        result = messagebox.askyesno(
            "Update Available",
            f"A new version is available!\n\n"
            f"Current version: {self.APP_VERSION}\n"
            f"Latest version: {latest_version}\n\n"
            f"Would you like to download the latest version?",
            icon="info"
        )
        
        if result:
            webbrowser.open("https://github.com/evanovar/RobloxAccountManager/releases/latest")

    def toggle_add_account_dropdown(self):
        """Toggle the Add Account dropdown menu"""
        self.add_account_dropdown_visible = not self.add_account_dropdown_visible
        if self.add_account_dropdown_visible:
            self.show_add_account_dropdown()
        else:
            self.hide_add_account_dropdown()
    
    def on_add_account_split_click(self, event):
        """Handle clicks on the unified split button: left area adds account, right area opens dropdown."""
        try:
            width = event.widget.winfo_width()
        except Exception:
            width = 0
        arrow_zone = 24
        if event.x >= max(0, width - arrow_zone):
            self.toggle_add_account_dropdown()
        else:
            self.add_account()
        return "break"
    
    def show_add_account_dropdown(self):
        """Show the Add Account dropdown menu"""
        if self.add_account_dropdown is not None:
            self.add_account_dropdown.destroy()
        
        self.add_account_dropdown = tk.Toplevel(self.root)
        self.add_account_dropdown.overrideredirect(True)
        self.add_account_dropdown.configure(bg=self.BG_MID, highlightthickness=1, highlightbackground="white")
        
        self.position_add_account_dropdown()
        
        import_cookie_btn = tk.Button(
            self.add_account_dropdown,
            text="Import Cookie",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_add_account_dropdown(), self.import_cookie()]
        )
        import_cookie_btn.pack(fill="x", padx=2, pady=1)
        
        javascript_btn = tk.Button(
            self.add_account_dropdown,
            text="Javascript",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_add_account_dropdown(), self.javascript_import()]
        )
        javascript_btn.pack(fill="x", padx=2, pady=1)
        
        self.position_add_account_dropdown()
        
        if self.settings.get("enable_topmost", False):
            self.add_account_dropdown.attributes("-topmost", True)
        
        self.add_account_dropdown.bind("<FocusOut>", lambda e: self.hide_add_account_dropdown())

    def position_add_account_dropdown(self):
        """Position the dropdown right under the split button and match its width."""
        try:
            if self.add_account_dropdown is None or not self.add_account_dropdown_visible:
                return
            self.root.update_idletasks()
            x = self.add_account_split_btn.winfo_rootx()
            y = self.add_account_split_btn.winfo_rooty() + self.add_account_split_btn.winfo_height()
            width = self.add_account_split_btn.winfo_width()
            req_h = self.add_account_dropdown.winfo_reqheight()
            self.add_account_dropdown.geometry(f"{width}x{req_h}+{x}+{y}")
            if self.settings.get("enable_topmost", False):
                self.add_account_dropdown.attributes("-topmost", True)
        except Exception:
            pass

    def on_root_configure(self, event=None):
        """Called when the main window moves/resizes; keep dropdown attached."""
        if self.add_account_dropdown_visible and self.add_account_dropdown is not None:
            self.position_add_account_dropdown()
        if self.join_place_dropdown_visible and self.join_place_dropdown is not None:
            self.position_join_place_dropdown()
    
    def hide_add_account_dropdown(self):
        """Hide the Add Account dropdown menu"""
        if self.add_account_dropdown is not None:
            self.add_account_dropdown.destroy()
            self.add_account_dropdown = None
        self.add_account_dropdown_visible = False
    
    def is_child_of(self, child, parent):
        """Check if a widget is a child of another widget"""
        while child is not None:
            if child == parent:
                return True
            child = child.master
        return False
    
    def hide_dropdown_on_click_outside(self, event):
        """Hide dropdown when clicking outside of it"""
        widget = event.widget
        if self.add_account_dropdown_visible and self.add_account_dropdown is not None:
            if not self.is_child_of(widget, self.add_account_split_btn):
                try:
                    if not self.is_child_of(widget, self.add_account_dropdown):
                        self.hide_add_account_dropdown()
                except:
                    self.hide_add_account_dropdown()
        
        if self.join_place_dropdown_visible and self.join_place_dropdown is not None:
            if not self.is_child_of(widget, self.join_place_split_btn):
                try:
                    if not self.is_child_of(widget, self.join_place_dropdown):
                        self.hide_join_place_dropdown()
                except:
                    self.hide_join_place_dropdown()

    def toggle_join_place_dropdown(self):
        """Toggle the Join Place dropdown menu"""
        self.join_place_dropdown_visible = not self.join_place_dropdown_visible
        if self.join_place_dropdown_visible:
            self.show_join_place_dropdown()
        else:
            self.hide_join_place_dropdown()
    
    def on_join_place_split_click(self, event):
        """Handle clicks on the button: left click launches game, right click shows dropdown."""
        self.launch_game()
        return "break"
    
    def on_join_place_right_click(self, event):
        """Handle right click on the button: show dropdown menu."""
        self.toggle_join_place_dropdown()
        return "break"
    
    def on_join_place_hover(self, event):
        """Show tooltip when hovering over Join Place ID button"""
        if self.tooltip_timer:
            self.root.after_cancel(self.tooltip_timer)
        
        def show_tooltip():
            if self.tooltip:
                return
            
            x = event.widget.winfo_rootx() + event.widget.winfo_width() // 2
            y = event.widget.winfo_rooty() + event.widget.winfo_height() + 5
            
            self.tooltip = tk.Toplevel(self.root)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            
            label = tk.Label(
                self.tooltip,
                text="Right click to see more options",
                bg="#333333",
                fg="white",
                font=("Segoe UI", 9),
                padx=8,
                pady=4,
                relief="solid",
                borderwidth=1
            )
            label.pack()
            
            self.tooltip.update_idletasks()
            tooltip_width = self.tooltip.winfo_width()
            self.tooltip.wm_geometry(f"+{x - tooltip_width // 2}+{y}")
            
            if self.settings.get("enable_topmost", False):
                self.tooltip.attributes("-topmost", True)
        
        self.tooltip_timer = self.root.after(800, show_tooltip)
    
    def on_join_place_leave(self, event):
        """Hide tooltip when leaving Join Place ID button"""
        if self.tooltip_timer:
            self.root.after_cancel(self.tooltip_timer)
            self.tooltip_timer = None
        
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None
    
    def show_join_place_dropdown(self):
        """Show the Join Place dropdown menu"""
        if self.join_place_dropdown is not None:
            self.join_place_dropdown.destroy()
        
        self.join_place_dropdown = tk.Toplevel(self.root)
        self.join_place_dropdown.overrideredirect(True)
        self.join_place_dropdown.configure(bg=self.BG_MID, highlightthickness=1, highlightbackground="white")
        
        self.position_join_place_dropdown()
        
        join_user_btn = tk.Button(
            self.join_place_dropdown,
            text="Join User",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_join_place_dropdown(), self.join_user()]
        )
        join_user_btn.pack(fill="x", padx=2, pady=1)
        
        job_id_btn = tk.Button(
            self.join_place_dropdown,
            text="Job-ID",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_join_place_dropdown(), self.join_by_job_id()]
        )
        job_id_btn.pack(fill="x", padx=2, pady=1)
        
        self.position_join_place_dropdown()
        
        if self.settings.get("enable_topmost", False):
            self.join_place_dropdown.attributes("-topmost", True)
        
        self.join_place_dropdown.bind("<FocusOut>", lambda e: self.hide_join_place_dropdown())

    def position_join_place_dropdown(self):
        """Position the dropdown right under the split button and match its width."""
        try:
            if self.join_place_dropdown is None or not self.join_place_dropdown_visible:
                return
            self.root.update_idletasks()
            x = self.join_place_split_btn.winfo_rootx()
            y = self.join_place_split_btn.winfo_rooty() + self.join_place_split_btn.winfo_height()
            width = self.join_place_split_btn.winfo_width()
            req_h = self.join_place_dropdown.winfo_reqheight()
            self.join_place_dropdown.geometry(f"{width}x{req_h}+{x}+{y}")
            if self.settings.get("enable_topmost", False):
                self.join_place_dropdown.attributes("-topmost", True)
        except Exception:
            pass
    
    def hide_join_place_dropdown(self):
        """Hide the Join Place dropdown menu"""
        if self.join_place_dropdown is not None:
            self.join_place_dropdown.destroy()
            self.join_place_dropdown = None
        self.join_place_dropdown_visible = False

    def save_settings(self):
        """Save UI settings to file with debouncing"""
        if self._save_settings_timer is not None:
            try:
                self.root.after_cancel(self._save_settings_timer)
            except:
                pass
            self._save_settings_timer = None
        
        def do_save():
            try:
                with open(self.settings_file, 'w') as f:
                    json.dump(self.settings, f, indent=2)
            except Exception as e:
                print(f"Failed to save settings: {e}")
            self._save_settings_timer = None
        
        self._save_settings_timer = self.root.after(500, do_save)

    def is_chrome_installed(self):
        """Best-effort check to see if Google Chrome is installed (Windows)."""
        try:
            candidates = []
            pf = os.environ.get('ProgramFiles')
            pfx86 = os.environ.get('ProgramFiles(x86)')
            localapp = os.environ.get('LOCALAPPDATA')
            if pf:
                candidates.append(os.path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'))
            if pfx86:
                candidates.append(os.path.join(pfx86, 'Google', 'Chrome', 'Application', 'chrome.exe'))
            if localapp:
                candidates.append(os.path.join(localapp, 'Google', 'Chrome', 'Application', 'chrome.exe'))
            for path in candidates:
                if path and os.path.exists(path):
                    return True
        except Exception:
            pass
        return False

    def on_place_id_change(self, event=None):
        """Called when place ID changes"""
        place_id = self.place_entry.get().strip()
        self.settings["last_place_id"] = place_id
        self.save_settings()
        self.update_game_name()

    def on_private_server_change(self, event=None):
        """Called when private server ID changes"""
        private_server = self.private_server_entry.get().strip()
        self.settings["last_private_server"] = private_server
        self.save_settings()

    def update_game_name(self):
        """Debounced, non-blocking update of the game name label"""
        if self._game_name_after_id is not None:
            try:
                self.root.after_cancel(self._game_name_after_id)
            except Exception:
                pass
            self._game_name_after_id = None

        def schedule_fetch():
            place_id = self.place_entry.get().strip()
            if not place_id or not place_id.isdigit():
                self.game_name_label.config(text="")
                return

            def worker(pid):
                name = RobloxAPI.get_game_name(pid)
                if name:
                    max_name_length = 20
                    if len(name) > max_name_length:
                        name = name[:max_name_length-2] + ".."
                    display_text = f"Current: {name}"
                else:
                    display_text = ""
                
                def update_label(text=display_text):
                    try:
                        self.game_name_label.config(text=text)
                    except:
                        pass
                
                self.root.after(0, update_label)

            threading.Thread(target=worker, args=(place_id,), daemon=True).start()

        self._game_name_after_id = self.root.after(350, schedule_fetch)

    def add_game_to_list(self, place_id, game_name, private_server=""):
        """Add a game to the saved list (max based on settings)"""
        for game in self.settings["game_list"]:
            if game["place_id"] == place_id and game.get("private_server", "") == private_server:
                return
        
        self.settings["game_list"].insert(0, {
            "place_id": place_id,
            "name": game_name,
            "private_server": private_server
        })
        
        max_games = self.settings.get("max_recent_games", 10)
        if len(self.settings["game_list"]) > max_games:
            self.settings["game_list"] = self.settings["game_list"][:max_games]
        
        self.save_settings()
        self.refresh_game_list()

    def refresh_game_list(self):
        """Refresh the game list display"""
        self.game_list.delete(0, tk.END)
        for game in self.settings["game_list"]:
            private_server = game.get("private_server", "")
            prefix = "[P] " if private_server else ""
            display_text = f"{prefix}{game['name']} ({game['place_id']})"
            self.game_list.insert(tk.END, display_text)

    def on_game_select(self, event=None):
        """Called when a game is selected from the list"""
        selection = self.game_list.curselection()
        if selection:
            index = selection[0]
            game = self.settings["game_list"][index]
            self.place_entry.delete(0, tk.END)
            self.place_entry.insert(0, game["place_id"])
            self.settings["last_place_id"] = game["place_id"]
            
            private_server = game.get("private_server", "")
            self.private_server_entry.delete(0, tk.END)
            self.private_server_entry.insert(0, private_server)
            self.settings["last_private_server"] = private_server
            
            self.save_settings()
            self.update_game_name()

    def delete_game_from_list(self):
        """Delete selected game from the list"""
        selection = self.game_list.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a game to delete.")
            return
        
        index = selection[0]
        game = self.settings["game_list"][index]
        confirm = messagebox.askyesno("Confirm Delete", f"Delete '{game['name']}' from list?")
        if confirm:
            self.settings["game_list"].pop(index)
            self.save_settings()
            self.refresh_game_list()
            messagebox.showinfo("Success", "Game removed from list!")

    def refresh_accounts(self):
        """Refresh the account list"""
        self.account_list.delete(0, tk.END)
        for username, data in self.manager.accounts.items():
            note = data.get('note', '') if isinstance(data, dict) else ''
            display_text = f"{username}"
            if note:
                display_text += f" • {note}"
            self.account_list.insert(tk.END, display_text)
    
    def on_drag_start(self, event):
        """Initiate drag - store position and wait for hold"""
        widget = event.widget
        index = widget.nearest(event.y)
        
        if self.drag_data["hold_timer"]:
            self.root.after_cancel(self.drag_data["hold_timer"])
        
        if index >= 0:
            self.drag_data["index"] = index
            self.drag_data["item"] = widget.get(index)
            self.drag_data["start_x"] = event.x
            self.drag_data["start_y"] = event.y
            self.drag_data["dragging"] = False
            
            if not self.settings.get("enable_multi_select", False):
                widget.selection_clear(0, tk.END)
                widget.selection_set(index)
            
            self.drag_data["hold_timer"] = self.root.after(500, lambda: self.activate_drag(event))
    
    def activate_drag(self, event):
        """Activate dragging after hold timer"""
        self.drag_data["dragging"] = True
        self.drag_data["hold_timer"] = None
        
        if not self.drag_indicator:
            self.drag_indicator = tk.Toplevel(self.root)
            self.drag_indicator.overrideredirect(True)
            self.drag_indicator.attributes("-alpha", 0.7)
            self.drag_indicator.attributes("-topmost", True)
            
            label = tk.Label(
                self.drag_indicator,
                text=self.drag_data["item"],
                bg=self.BG_LIGHT,
                fg=self.FG_TEXT,
                font=("Segoe UI", 10),
                padx=10,
                pady=5,
                relief="raised",
                borderwidth=2
            )
            label.pack()
            
            x = self.root.winfo_pointerx() + 10
            y = self.root.winfo_pointery() + 10
            self.drag_indicator.geometry(f"+{x}+{y}")
    
    def on_drag_motion(self, event):
        """Handle drag motion, show indicator and highlight drop position"""
        if self.drag_data["hold_timer"] and self.drag_data["index"] is not None:
            dx = abs(event.x - self.drag_data["start_x"])
            dy = abs(event.y - self.drag_data["start_y"])
            if dx > 5 or dy > 5:
                self.root.after_cancel(self.drag_data["hold_timer"])
                self.drag_data["hold_timer"] = None
        
        if not self.drag_data["dragging"] or self.drag_data["index"] is None:
            return
        
        widget = event.widget
        
        if self.drag_indicator:
            x = event.x_root + 10
            y = event.y_root + 10
            self.drag_indicator.geometry(f"+{x}+{y}")
        
        index = widget.nearest(event.y)
        if index >= 0:
            if not self.settings.get("enable_multi_select", False):
                widget.selection_clear(0, tk.END)
            widget.selection_set(index)
    
    def on_drag_release(self, event):
        """Release drag and reorder accounts"""
        try:
            if self.drag_data["hold_timer"]:
                self.root.after_cancel(self.drag_data["hold_timer"])
                self.drag_data["hold_timer"] = None
            
            if not self.drag_data["dragging"] or self.drag_data["index"] is None:
                return
            
            widget = event.widget
            drop_index = widget.nearest(event.y)
            drag_index = self.drag_data["index"]
            
            if drop_index >= 0 and drag_index != drop_index:
                ordered_usernames = list(self.manager.accounts.keys())
                
                username = ordered_usernames.pop(drag_index)
                ordered_usernames.insert(drop_index, username)
                
                new_accounts = {}
                for uname in ordered_usernames:
                    new_accounts[uname] = self.manager.accounts[uname]
                
                self.manager.accounts = new_accounts
                self.manager.save_accounts()
                
                self.refresh_accounts()
                
                if not self.settings.get("enable_multi_select", False):
                    widget.selection_clear(0, tk.END)
                    widget.selection_set(drop_index)
        finally:
            if self.drag_indicator:
                self.drag_indicator.destroy()
                self.drag_indicator = None
            
            self.drag_data = {
                "item": None, 
                "index": None, 
                "start_x": 0, 
                "start_y": 0,
                "dragging": False,
                "hold_timer": None
            }
    
    def get_selected_username(self):
        """Get the currently selected username"""
        selection = self.account_list.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an account first.")
            return None
        
        display_text = self.account_list.get(selection[0])
        username = display_text.split(' • ')[0]
        return username
    
    def get_selected_usernames(self):
        """Get all selected usernames (for multi-select mode)"""
        selections = self.account_list.curselection()
        if not selections:
            messagebox.showwarning("No Selection", "Please select at least one account first.")
            return []
        
        usernames = []
        for index in selections:
            display_text = self.account_list.get(index)
            username = display_text.split(' • ')[0]
            usernames.append(username)
        return usernames

    def add_account(self):
        """
        Add a new account using browser automation
        """
        if not self.is_chrome_installed():
            messagebox.showwarning(
                "Google Chrome Required",
                "Add Account requires Google Chrome to be installed.\n"
                "Please install Google Chrome and try again."
            )
            return

        messagebox.showinfo("Add Account", "Browser will open for account login.\nPlease log in and wait for the process to complete.")
        
        def add_account_thread():
            """
            Thread function to add account without blocking UI
            """
            try:
                success = self.manager.add_account(1, "https://www.roblox.com/login", "")
                self.root.after(0, lambda: self._add_account_complete(success))
            except Exception as e:
                self.root.after(0, lambda: self._add_account_error(str(e)))
        
        thread = threading.Thread(target=add_account_thread, daemon=True)
        thread.start()
    
    def _add_account_complete(self, success):
        """
        Called when account addition completes (on main thread)
        """
        if success:
            self.refresh_accounts()
            messagebox.showinfo("Success", "Account added successfully!")
        else:
            messagebox.showerror("Error", "Failed to add account.\nPlease make sure you completed the login process.")
    
    def _add_account_error(self, error_msg):
        """
        Called when account addition encounters an error (on main thread)
        """
        messagebox.showerror("Error", f"Failed to add account: {error_msg}")
    
    def import_cookie(self):
        """
        Import an account using a .ROBLOSECURITY cookie
        """
        import_window = tk.Toplevel(self.root)
        import_window.title("Import Cookie")
        import_window.geometry("450x250")
        import_window.configure(bg=self.BG_DARK)
        import_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 250) // 2
        import_window.geometry(f"450x250+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            import_window.attributes("-topmost", True)
        
        import_window.transient(self.root)
        import_window.grab_set()
        
        main_frame = ttk.Frame(import_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Import Account from Cookie",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 15))
        
        ttk.Label(main_frame, text="Cookie (.ROBLOSECURITY):", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        cookie_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        cookie_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        cookie_text = tk.Text(
            cookie_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Segoe UI", 9),
            height=5,
            wrap="word"
        )
        cookie_text.pack(side="left", fill="both", expand=True)
        
        cookie_scrollbar = ttk.Scrollbar(cookie_frame, command=cookie_text.yview)
        cookie_scrollbar.pack(side="right", fill="y")
        cookie_text.config(yscrollcommand=cookie_scrollbar.set)
        
        def do_import():
            cookie = cookie_text.get("1.0", "end-1c").strip()
            
            if not cookie:
                messagebox.showwarning("Missing Information", "Please enter the cookie.")
                return
            
            try:
                success, username = self.manager.import_cookie_account(cookie)
                if success:
                    self.refresh_accounts()
                    messagebox.showinfo("Success", f"Account '{username}' imported successfully!")
                    import_window.destroy()
                else:
                    messagebox.showerror("Error", "Failed to import account. Please check the cookie.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import account: {str(e)}")
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Import",
            style="Dark.TButton",
            command=do_import
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=import_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def javascript_import(self):
        """
        Launch multiple Chrome instances with custom Javascript execution
        """
        amount_window = tk.Toplevel(self.root)
        amount_window.title("Javascript Import - Amount")
        amount_window.geometry("350x150")
        amount_window.configure(bg=self.BG_DARK)
        amount_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 350) // 2
        y = main_y + (main_height - 150) // 2
        amount_window.geometry(f"350x150+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            amount_window.attributes("-topmost", True)
        
        amount_window.transient(self.root)
        
        main_frame = ttk.Frame(amount_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Amount to open (max 10):",
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        amount_entry = ttk.Entry(main_frame, style="Dark.TEntry")
        amount_entry.pack(fill="x", pady=(0, 15))
        amount_entry.insert(0, "1")
        amount_entry.focus_set()
        
        def proceed_to_website():
            try:
                amount = int(amount_entry.get().strip())
                if amount < 1 or amount > 10:
                    messagebox.showwarning("Invalid Amount", "Please enter a number between 1 and 10.")
                    return
                amount_window.destroy()
                self.javascript_import_website(amount)
            except ValueError:
                messagebox.showwarning("Invalid Input", "Please enter a valid number.")
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Yes",
            style="Dark.TButton",
            command=proceed_to_website
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=amount_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def javascript_import_website(self, amount):
        """
        Get website URL for Javascript import
        """
        website_window = tk.Toplevel(self.root)
        website_window.title("Javascript Import - Website")
        website_window.geometry("450x150")
        website_window.configure(bg=self.BG_DARK)
        website_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 150) // 2
        website_window.geometry(f"450x150+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            website_window.attributes("-topmost", True)
        
        website_window.transient(self.root)
        
        main_frame = ttk.Frame(website_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Website link to launch:",
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        website_entry = ttk.Entry(main_frame, style="Dark.TEntry")
        website_entry.pack(fill="x", pady=(0, 15))
        website_entry.insert(0, "https://www.roblox.com/CreateAccount")
        website_entry.focus_set()
        
        def proceed_to_javascript():
            website = website_entry.get().strip()
            if not website:
                messagebox.showwarning("Missing Information", "Please enter a website URL.")
                return
            if not website.startswith(('http://', 'https://')):
                messagebox.showwarning("Invalid URL", "Please enter a valid URL starting with http:// or https://")
                return
            website_window.destroy()
            self.javascript_import_code(amount, website)
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Yes",
            style="Dark.TButton",
            command=proceed_to_javascript
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=website_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def javascript_import_code(self, amount, website):
        """
        Get Javascript code to execute and launch Chrome instances
        """
        js_window = tk.Toplevel(self.root)
        js_window.title("Javascript Import - Code")
        js_window.geometry("500x300")
        js_window.configure(bg=self.BG_DARK)
        js_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 500) // 2
        y = main_y + (main_height - 300) // 2
        js_window.geometry(f"500x300+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            js_window.attributes("-topmost", True)
        
        js_window.transient(self.root)
        
        main_frame = ttk.Frame(js_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Javascript:",
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        js_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        js_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        js_text = tk.Text(
            js_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Consolas", 9),
            height=10,
            wrap="word"
        )
        js_text.pack(side="left", fill="both", expand=True)
        
        js_scrollbar = ttk.Scrollbar(js_frame, command=js_text.yview)
        js_scrollbar.pack(side="right", fill="y")
        js_text.config(yscrollcommand=js_scrollbar.set)
        js_text.focus_set()
        
        def execute_javascript():
            javascript = js_text.get("1.0", "end-1c").strip()
            if not javascript:
                messagebox.showwarning("Missing Information", "Please enter Javascript code.")
                return
            js_window.destroy()
            self.launch_javascript_browsers(amount, website, javascript)
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Yes",
            style="Dark.TButton",
            command=execute_javascript
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=js_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def launch_javascript_browsers(self, amount, website, javascript):
        """
        Launch account addition with Javascript execution
        """
        def launch_thread():
            try:
                success = self.manager.add_account(amount, website, javascript)
                
                if success:
                    self.root.after(0, lambda: [
                        self.refresh_accounts(),
                        messagebox.showinfo(
                            "Success",
                            f"Account(s) added successfully with Javascript execution!"
                        )
                    ])
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        "Failed to add accounts. Please check the console for details."
                    ))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Error",
                    f"Failed to launch browsers: {str(e)}"
                ))
        
        thread = threading.Thread(target=launch_thread, daemon=True)
        thread.start()

    def remove_account(self):
        """Remove the selected account(s)"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
            
            if len(usernames) == 1:
                confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{usernames[0]}'?")
            else:
                confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {len(usernames)} accounts?\n\n" + "\n".join(usernames))
            
            if confirm:
                for username in usernames:
                    self.manager.delete_account(username)
                self.refresh_accounts()
                messagebox.showinfo("Success", f"{len(usernames)} account(s) deleted successfully!")
        else:
            username = self.get_selected_username()
            if username:
                confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{username}'?")
                if confirm:
                    self.manager.delete_account(username)
                    self.refresh_accounts()
                    messagebox.showinfo("Success", f"Account '{username}' deleted successfully!")

    def validate_account(self):
        """Validate the selected account"""
        username = self.get_selected_username()
        if username:
            is_valid = self.manager.validate_account(username)
            if is_valid:
                messagebox.showinfo("Validation", f"Account '{username}' is valid! ✓")
            else:
                messagebox.showwarning("Validation", f"Account '{username}' is invalid or expired.")
    
    def edit_account_note(self):
        """Edit note for the selected account(s)"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
            
            if len(usernames) == 1:
                username = usernames[0]
                current_note = self.manager.get_account_note(username)
                title_text = f"Edit Note - {username}"
            else:
                username = None
                current_note = ""
                title_text = f"Edit Note - {len(usernames)} accounts"
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]
            current_note = self.manager.get_account_note(username)
            title_text = f"Edit Note - {username}"
        
        note_window = tk.Toplevel(self.root)
        note_window.title(title_text)
        note_window.geometry("450x220")
        note_window.configure(bg=self.BG_DARK)
        note_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 220) // 2
        note_window.geometry(f"450x220+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            note_window.attributes("-topmost", True)
        
        note_window.transient(self.root)
        note_window.grab_set()
        
        main_frame = ttk.Frame(note_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        if len(usernames) == 1:
            label_text = f"Edit note for '{usernames[0]}'"
        else:
            label_text = f"Edit note for {len(usernames)} accounts"
        
        ttk.Label(
            main_frame,
            text=label_text,
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(main_frame, text="Note:", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        note_text = tk.Text(
            main_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Segoe UI", 9),
            height=3,
            wrap="word"
        )
        note_text.pack(fill="both", expand=True, pady=(0, 15))
        note_text.insert("1.0", current_note)
        note_text.focus_set()
        
        def save_note():
            new_note = note_text.get("1.0", "end-1c").strip()
            for uname in usernames:
                self.manager.set_account_note(uname, new_note)
            self.refresh_accounts()
            if len(usernames) == 1:
                messagebox.showinfo("Success", f"Note updated for '{usernames[0]}'!")
            else:
                messagebox.showinfo("Success", f"Note updated for {len(usernames)} accounts!")
            note_window.destroy()
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Save",
            style="Dark.TButton",
            command=save_note
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=note_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def launch_home(self):
        """Launch Roblox application to home page with the selected account(s) logged in (non-blocking)"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
            if len(usernames) >= 3:
                confirm = messagebox.askyesno(
                    "Confirm Launch",
                    f"Are you sure you want to launch {len(usernames)} Roblox instances to home?\n\nThis will open multiple Roblox windows."
                )
                if not confirm:
                    return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]

        def worker(selected_usernames):
            launcher_pref = self.settings.get("roblox_launcher", "default")
            success_count = 0
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, "", "", launcher_pref):
                        success_count += 1
                except Exception as e:
                    print(f"Failed to launch Roblox home for {uname}: {e}")
            
            def on_done():
                if success_count > 0:
                    if not self.settings.get("disable_launch_popup", False):
                        if len(selected_usernames) == 1:
                            messagebox.showinfo("Success", "Roblox is launching to home! Check your desktop.")
                        else:
                            messagebox.showinfo("Success", f"Roblox is launching to home for {success_count} account(s)! Check your desktop.")
                else:
                    messagebox.showerror("Error", "Failed to launch Roblox.")
            
            self.root.after(0, on_done)

        threading.Thread(target=worker, args=(usernames,), daemon=True).start()

    def launch_game(self):
        """Launch Roblox game with the selected account(s) (non-blocking)"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]

        game_id = self.place_entry.get().strip()
        if not game_id:
            messagebox.showwarning("Missing Info", "Please enter a Place ID.")
            return
        if not game_id.isdigit():
            messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
            return
        private_server = self.private_server_entry.get().strip()

        if self.settings.get("confirm_before_launch", False):
            game_name = RobloxAPI.get_game_name(game_id)
            if not game_name:
                game_name = f"Place {game_id}"
            if len(usernames) == 1:
                confirm = messagebox.askyesno("Confirm Launch", f"Are you sure you want to join {game_name}?")
            else:
                confirm = messagebox.askyesno("Confirm Launch", f"Are you sure you want to join {game_name} with {len(usernames)} accounts?")
            if not confirm:
                return

        def worker(selected_usernames, pid, psid):
            launcher_pref = self.settings.get("roblox_launcher", "default")
            success_count = 0
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, pid, psid, launcher_pref):
                        success_count += 1
                except Exception as e:
                    print(f"Failed to launch game for {uname}: {e}")

            def on_done():
                if success_count > 0:
                    gname = RobloxAPI.get_game_name(pid)
                    if gname:
                        self.add_game_to_list(pid, gname, psid)
                    else:
                        self.add_game_to_list(pid, f"Place {pid}", psid)
                    if not self.settings.get("disable_launch_popup", False):
                        if len(selected_usernames) == 1:
                            messagebox.showinfo("Success", "Roblox is launching! Check your desktop.")
                        else:
                            messagebox.showinfo("Success", f"Roblox is launching for {success_count} account(s)! Check your desktop.")
                else:
                    messagebox.showerror("Error", "Failed to launch Roblox.")

            self.root.after(0, on_done)

        threading.Thread(target=worker, args=(usernames, game_id, private_server), daemon=True).start()

    def open_auto_rejoin(self):
        """Open the auto-rejoin management window (like favorites window)"""
        auto_rejoin_window = tk.Toplevel(self.root)
        auto_rejoin_window.title("Auto-Rejoin")
        auto_rejoin_window.configure(bg=self.BG_DARK)
        auto_rejoin_window.resizable(False, False)
        
        self.root.update_idletasks()
        x = self.root.winfo_x() + 50
        y = self.root.winfo_y() + 50
        auto_rejoin_window.geometry(f"450x400+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            auto_rejoin_window.attributes("-topmost", True)
        
        auto_rejoin_window.transient(self.root)
        auto_rejoin_window.focus_force()
        
        main_frame = ttk.Frame(auto_rejoin_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        ttk.Label(
            main_frame,
            text="Auto-Rejoin Accounts",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        list_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        rejoin_list = tk.Listbox(
            list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 9)
        )
        rejoin_list.grid(row=0, column=0, sticky="nsew")
        
        v_scrollbar = ttk.Scrollbar(list_frame, command=rejoin_list.yview, orient="vertical")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        rejoin_list.config(yscrollcommand=v_scrollbar.set)
        
        def refresh_rejoin_list():
            rejoin_list.delete(0, tk.END)
            for account, config in self.auto_rejoin_configs.items():
                is_active = account in self.auto_rejoin_threads and self.auto_rejoin_threads[account].is_alive()
                status = "[ACTIVE]" if is_active else "[INACTIVE]"
                place_id = config.get('place_id', 'Unknown')
                display = f"{account} - {status} - Place: {place_id}"
                rejoin_list.insert(tk.END, display)
        
        refresh_rejoin_list()
        
        btn_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        btn_frame.pack(fill="x")
        
        def add_auto_rejoin():
            """Open dialog to add a new auto-rejoin account"""
            add_window = tk.Toplevel(auto_rejoin_window)
            add_window.title("Add Auto-Rejoin")
            add_window.configure(bg=self.BG_DARK)
            add_window.resizable(False, False)
            
            auto_rejoin_window.update_idletasks()
            x = auto_rejoin_window.winfo_x() + 50
            y = auto_rejoin_window.winfo_y() + 50
            add_window.geometry(f"400x350+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                add_window.attributes("-topmost", True)
            
            add_window.transient(auto_rejoin_window)
            add_window.focus_force()
            
            form_frame = ttk.Frame(add_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            ttk.Label(form_frame, text="Account:", style="Dark.TLabel").pack(anchor="w")
            account_combo = ttk.Combobox(form_frame, values=list(self.manager.accounts.keys()), state="readonly")
            account_combo.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Place ID:", style="Dark.TLabel").pack(anchor="w")
            place_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            place_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Private Server ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            private_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            private_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Job ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            job_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            job_entry.pack(fill="x", pady=(0, 10))
            
            interval_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            interval_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(interval_frame, text="Check Interval (seconds):", style="Dark.TLabel").pack(side="left")
            interval_spinbox = ttk.Spinbox(interval_frame, from_=5, to=300, increment=5, width=8)
            interval_spinbox.set(10)
            interval_spinbox.pack(side="left", padx=(10, 0))
            
            retry_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            retry_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(retry_frame, text="Max Rejoin Attempts:", style="Dark.TLabel").pack(side="left")
            retry_spinbox = ttk.Spinbox(retry_frame, from_=1, to=50, increment=1, width=8)
            retry_spinbox.set(5)
            retry_spinbox.pack(side="left", padx=(10, 0))
            
            def save_and_add():
                account = account_combo.get()
                if not account:
                    messagebox.showwarning("Missing Info", "Please select an account.")
                    return
                
                place_id = place_entry.get().strip()
                if not place_id:
                    messagebox.showwarning("Missing Info", "Please enter a Place ID.")
                    return
                if not place_id.isdigit():
                    messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
                    return
                
                job_id = job_entry.get().strip()
                
                self.auto_rejoin_configs[account] = {
                    'place_id': place_id,
                    'private_server': private_entry.get().strip(),
                    'job_id': job_id,
                    'check_interval': int(interval_spinbox.get()),
                    'max_retries': int(retry_spinbox.get())
                }
                
                self.settings['auto_rejoin_configs'] = self.auto_rejoin_configs
                self.save_settings()
                
                add_window.destroy()
                refresh_rejoin_list()
                messagebox.showinfo("Success", f"Added auto-rejoin for {account}!")
                auto_rejoin_window.lift()
                auto_rejoin_window.focus_force()
            
            button_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            button_frame.pack(fill="x", pady=(10, 0))
            
            ttk.Button(button_frame, text="Save", style="Dark.TButton", command=save_and_add).pack(side="left", fill="x", expand=True, padx=(0, 5))
            ttk.Button(button_frame, text="Cancel", style="Dark.TButton", command=add_window.destroy).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def edit_auto_rejoin():
            """Edit selected auto-rejoin config"""
            selection = rejoin_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an account to edit.")
                return
            
            accounts_list = list(self.auto_rejoin_configs.keys())
            account = accounts_list[selection[0]]
            config = self.auto_rejoin_configs[account]
            
            edit_window = tk.Toplevel(auto_rejoin_window)
            edit_window.title("Edit Auto-Rejoin")
            edit_window.configure(bg=self.BG_DARK)
            edit_window.resizable(False, False)
            
            auto_rejoin_window.update_idletasks()
            x = auto_rejoin_window.winfo_x() + 50
            y = auto_rejoin_window.winfo_y() + 50
            edit_window.geometry(f"400x350+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                edit_window.attributes("-topmost", True)
            
            edit_window.transient(auto_rejoin_window)
            edit_window.focus_force()
            
            form_frame = ttk.Frame(edit_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            ttk.Label(form_frame, text=f"Account: {account}", style="Dark.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 10))
            
            ttk.Label(form_frame, text="Place ID:", style="Dark.TLabel").pack(anchor="w")
            place_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            place_entry.insert(0, config.get('place_id', ''))
            place_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Private Server ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            private_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            private_entry.insert(0, config.get('private_server', ''))
            private_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Job ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            job_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            job_entry.insert(0, config.get('job_id', ''))
            job_entry.pack(fill="x", pady=(0, 10))
            
            interval_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            interval_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(interval_frame, text="Check Interval (seconds):", style="Dark.TLabel").pack(side="left")
            interval_spinbox = ttk.Spinbox(interval_frame, from_=5, to=300, increment=5, width=8)
            interval_spinbox.set(config.get('check_interval', 10))
            interval_spinbox.pack(side="left", padx=(10, 0))
            
            retry_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            retry_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(retry_frame, text="Max Rejoin Attempts:", style="Dark.TLabel").pack(side="left")
            retry_spinbox = ttk.Spinbox(retry_frame, from_=1, to=50, increment=1, width=8)
            retry_spinbox.set(config.get('max_retries', 5))
            retry_spinbox.pack(side="left", padx=(10, 0))
            
            def save_edit():
                place_id = place_entry.get().strip()
                if not place_id:
                    messagebox.showwarning("Missing Info", "Please enter a Place ID.")
                    return
                if not place_id.isdigit():
                    messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
                    return
                
                job_id = job_entry.get().strip()
                
                self.auto_rejoin_configs[account] = {
                    'place_id': place_id,
                    'private_server': private_entry.get().strip(),
                    'job_id': job_id,
                    'check_interval': int(interval_spinbox.get()),
                    'max_retries': int(retry_spinbox.get())
                }
                
                self.settings['auto_rejoin_configs'] = self.auto_rejoin_configs
                self.save_settings()
                
                edit_window.destroy()
                refresh_rejoin_list()
                auto_rejoin_window.lift()
                auto_rejoin_window.focus_force()
            
            button_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            button_frame.pack(fill="x", pady=(10, 0))
            
            ttk.Button(button_frame, text="Save", style="Dark.TButton", command=save_edit).pack(side="left", fill="x", expand=True, padx=(0, 5))
            ttk.Button(button_frame, text="Cancel", style="Dark.TButton", command=edit_window.destroy).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def remove_auto_rejoin():
            """Remove selected auto-rejoin config"""
            selection = rejoin_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an account to remove.")
                return
            
            accounts_list = list(self.auto_rejoin_configs.keys())
            account = accounts_list[selection[0]]
            
            if messagebox.askyesno("Confirm", f"Remove auto-rejoin for {account}?"):
                self.stop_auto_rejoin_for_account(account)
                del self.auto_rejoin_configs[account]
                self.settings['auto_rejoin_configs'] = self.auto_rejoin_configs
                self.save_settings()
                refresh_rejoin_list()
        
        def start_selected():
            """Start auto-rejoin for selected account"""
            selection = rejoin_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an account to start.")
                return
            
            accounts_list = list(self.auto_rejoin_configs.keys())
            account = accounts_list[selection[0]]
            self.start_auto_rejoin_for_account(account)
            refresh_rejoin_list()
            messagebox.showinfo("Started", f"Auto-rejoin started for {account}!")
        
        def stop_selected():
            """Stop auto-rejoin for selected account"""
            selection = rejoin_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an account to stop.")
                return
            
            accounts_list = list(self.auto_rejoin_configs.keys())
            account = accounts_list[selection[0]]
            self.stop_auto_rejoin_for_account(account)
            refresh_rejoin_list()
            messagebox.showinfo("Stopped", f"Auto-rejoin stopped for {account}!")
        
        def start_all():
            """Start auto-rejoin for all accounts"""
            for account in self.auto_rejoin_configs.keys():
                self.start_auto_rejoin_for_account(account)
            refresh_rejoin_list()
            messagebox.showinfo("Started", f"Auto-rejoin started for all {len(self.auto_rejoin_configs)} account(s)!")
        
        def stop_all():
            """Stop auto-rejoin for all accounts"""
            for account in list(self.auto_rejoin_threads.keys()):
                self.stop_auto_rejoin_for_account(account)
            refresh_rejoin_list()
            messagebox.showinfo("Stopped", "Auto-rejoin stopped for all accounts!")
        
        row1_frame = ttk.Frame(btn_frame, style="Dark.TFrame")
        row1_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Button(row1_frame, text="Add", style="Dark.TButton", command=add_auto_rejoin).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row1_frame, text="Edit", style="Dark.TButton", command=edit_auto_rejoin).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row1_frame, text="Remove", style="Dark.TButton", command=remove_auto_rejoin).pack(side="left", fill="x", expand=True, padx=(2, 0))
        
        row2_frame = ttk.Frame(btn_frame, style="Dark.TFrame")
        row2_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Button(row2_frame, text="Start Selected", style="Dark.TButton", command=start_selected).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row2_frame, text="Stop Selected", style="Dark.TButton", command=stop_selected).pack(side="left", fill="x", expand=True, padx=(2, 0))
        
        row3_frame = ttk.Frame(btn_frame, style="Dark.TFrame")
        row3_frame.pack(fill="x")
        
        ttk.Button(row3_frame, text="Start All", style="Dark.TButton", command=start_all).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row3_frame, text="Stop All", style="Dark.TButton", command=stop_all).pack(side="left", fill="x", expand=True, padx=(2, 0))

    def join_user(self):
        """Join a user's current game"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]
        
        join_window = tk.Toplevel(self.root)
        join_window.title("Join User")
        join_window.geometry("450x220")
        join_window.configure(bg=self.BG_DARK)
        join_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 220) // 2
        join_window.geometry(f"450x220+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            join_window.attributes("-topmost", True)
        
        join_window.transient(self.root)
        join_window.grab_set()
        
        main_frame = ttk.Frame(join_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Join User's Game",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(
            main_frame,
            text="⚠️ User must have their joins enabled!",
            style="Dark.TLabel",
            font=("Segoe UI", 9, "italic"),
            foreground="#FFA500"
        ).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(main_frame, text="Username to join:", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        username_entry = ttk.Entry(main_frame, style="Dark.TEntry")
        username_entry.pack(fill="x", pady=(0, 15))
        username_entry.focus_set()
        
        def do_join():
            target_username = username_entry.get().strip()
            
            if not target_username:
                messagebox.showwarning("Missing Information", "Please enter a username.")
                return
            
            join_window.destroy()
            
            def worker(selected_usernames, target_user):
                
                user_id = RobloxAPI.get_user_id_from_username(target_user)
                if not user_id:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        f"User '{target_user}' not found."
                    ))
                    return
                
                account_cookie = self.manager.accounts.get(selected_usernames[0])
                if isinstance(account_cookie, dict):
                    account_cookie = account_cookie.get('cookie')
                
                if not account_cookie:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        "Failed to get account cookie."
                    ))
                    return
                
                presence = RobloxAPI.get_player_presence(user_id, account_cookie)
                
                if not presence:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        f"Failed to get presence for '{target_user}'. Please try again."
                    ))
                    return
                
                if not presence.get('in_game'):
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Not In Game",
                        f"'{target_user}' is not currently in a game.\n\nStatus: {presence.get('last_location', 'Unknown')}"
                    ))
                    return
                
                place_id = str(presence.get('place_id', ''))
                game_id = str(presence.get('game_id', ''))
                
                if not place_id:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        f"Could not get game info for '{target_user}'."
                    ))
                    return
                
                launcher_pref = self.settings.get("roblox_launcher", "default")
                success_count = 0
                
                for uname in selected_usernames:
                    try:
                        if self.manager.launch_roblox(uname, place_id, "", launcher_pref, game_id):
                            success_count += 1
                    except Exception as e:
                        print(f"Failed to launch game for {uname}: {e}")
                
                def on_done():
                    if success_count > 0:
                        game_name = RobloxAPI.get_game_name(place_id)
                        if game_name:
                            self.add_game_to_list(place_id, game_name, "")
                        else:
                            self.add_game_to_list(place_id, f"Place {place_id}", "")
                        
                        if len(selected_usernames) == 1:
                            messagebox.showinfo(
                                "Success",
                                f"Joining '{target_user}' in their game! Check your desktop."
                            )
                        else:
                            messagebox.showinfo(
                                "Success",
                                f"Joining '{target_user}' with {success_count} account(s)! Check your desktop."
                            )
                    else:
                        messagebox.showerror("Error", "Failed to launch Roblox.")
                
                self.root.after(0, on_done)
            
            threading.Thread(target=worker, args=(usernames, target_username), daemon=True).start()
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Join",
            style="Dark.TButton",
            command=do_join
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=join_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def join_by_job_id(self):
        """Join a game by Job ID"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]
        
        job_id_window = tk.Toplevel(self.root)
        job_id_window.title("Join by Job-ID")
        job_id_window.geometry("450x220")
        job_id_window.configure(bg=self.BG_DARK)
        job_id_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 220) // 2
        job_id_window.geometry(f"450x220+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            job_id_window.attributes("-topmost", True)
        
        job_id_window.transient(self.root)
        job_id_window.grab_set()
        
        main_frame = ttk.Frame(job_id_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Join by Job-ID",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(main_frame, text="Job-ID:", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        job_id_entry = ttk.Entry(main_frame, style="Dark.TEntry")
        job_id_entry.pack(fill="x", pady=(0, 15))
        job_id_entry.focus_set()
        
        def do_join_job():
            place_id = self.place_entry.get().strip()
            if not place_id:
                messagebox.showwarning("Missing Information", "Please enter a Place ID first.")
                return
            
            job_id = job_id_entry.get().strip()
            if not job_id:
                messagebox.showwarning("Missing Information", "Please enter a Job-ID.")
                return
            
            job_id_window.destroy()
            
            def worker(selected_usernames, pid, jid):
                launcher_pref = self.settings.get("roblox_launcher", "default")
                success_count = 0
                
                for uname in selected_usernames:
                    try:
                        if self.manager.launch_roblox(uname, pid, "", launcher_pref, jid):
                            success_count += 1
                    except Exception as e:
                        print(f"Failed to launch game for {uname}: {e}")
                
                def on_done():
                    if success_count > 0:
                        game_name = RobloxAPI.get_game_name(pid)
                        if game_name:
                            self.add_game_to_list(pid, game_name, "")
                        else:
                            self.add_game_to_list(pid, f"Place {pid}", "")
                        
                        messagebox.showinfo(
                            "Success",
                            f"Joining Job-ID {jid} with {success_count} account(s)! Check your desktop."
                        )
                    else:
                        messagebox.showerror("Error", "Failed to launch Roblox.")
                
                self.root.after(0, on_done)
            
            threading.Thread(target=worker, args=(usernames, place_id, job_id), daemon=True).start()
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Join",
            style="Dark.TButton",
            command=do_join_job
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=job_id_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def _close_roblox_handles(self, handle_path):
        """Close ROBLOX_singletonEvent handles for all running Roblox processes using handle64.exe"""
        # thx multiblox
        try:
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq RobloxPlayerBeta.exe'], 
                                  capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
            
            if not (result.stdout and 'RobloxPlayerBeta.exe' in result.stdout):
                return True
            
            pids = []
            for line in result.stdout.split('\n'):
                match = re.search(r'RobloxPlayerBeta\.exe\s+(\d+)', line)
                if match:
                    pids.append(match.group(1))
            
            for pid in pids:
                try:
                    cmd = f'"{handle_path}" -accepteula -p {pid} -a'
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        stdin=subprocess.DEVNULL, text=True, shell=True, timeout=5)
                    
                    for line in proc.stdout.splitlines():
                        if "ROBLOX_singletonEvent" in line:
                            m = re.search(r'([0-9A-F]+):\s.*ROBLOX_singletonEvent', line, re.IGNORECASE)
                            if m:
                                handle_id = m.group(1)
                                close_cmd = f'"{handle_path}" -accepteula -p {pid} -c {handle_id} -y'
                                subprocess.run(close_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            stdin=subprocess.DEVNULL, shell=True, timeout=5)
                                print(f"[INFO] Closed ROBLOX_singletonEvent handle for PID:{pid}")
                                break
                except Exception as e:
                    print(f"[WARNING] Could not close handle for PID:{pid} - {str(e)}")
            
            return True
        except Exception as e:
            print(f"[WARNING] Error closing handles: {str(e)}")
            return False

    def _download_handle64_exe(self, local_path):
        """Download handle64.exe from Sysinternals and extract it"""
        try:
            handle_url = "https://download.sysinternals.com/files/Handle.zip"
            handle_exe_name = "handle64.exe" if platform.architecture()[0] == "64bit" else "handle.exe"
            
            with tempfile.TemporaryDirectory() as tmpdirname:
                zip_path = os.path.join(tmpdirname, "Handle.zip")
                
                urlretrieve(handle_url, zip_path)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extract(handle_exe_name, tmpdirname)
                    extracted_path = os.path.join(tmpdirname, handle_exe_name)
                    shutil.move(extracted_path, local_path)
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to download handle64.exe: {str(e)}")
            return False

    def _find_handle64_exe(self):
        """Find handle64.exe in AccountManagerData, same directory as executable, or 'tools' subfolder"""
        try:
            handle_path = os.path.join(self.data_folder, 'handle64.exe')
            if os.path.exists(handle_path):
                return handle_path
            
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            
            handle_path = os.path.join(base_dir, 'handle64.exe')
            if os.path.exists(handle_path):
                return handle_path
            
            handle_path = os.path.join(base_dir, 'tools', 'handle64.exe')
            if os.path.exists(handle_path):
                return handle_path
            
            return None
        except Exception as e:
            print(f"[WARNING] Error finding handle64.exe: {str(e)}")
            return None

    def enable_multi_roblox(self):
        """Enable Multi Roblox + 773 fix"""
        
        if self.multi_roblox_handle is not None:
            self.disable_multi_roblox()
        
        try:
            selected_method = self.settings.get("multi_roblox_method", "default")
            use_handle64 = selected_method == "handle64"
            
            if use_handle64:
                handle64_path = self._find_handle64_exe()
                if handle64_path:
                    print("[INFO] handle64.exe found. Using advanced multi-roblox mode.")
                    if not self._close_roblox_handles(handle64_path):
                        print("[WARNING] Failed to close some handles, attempting fallback.")
                        time.sleep(2)
                else:
                    print("[INFO] handle64.exe not found. Falling back to default method.")
                    use_handle64 = False
            
            if not use_handle64:
                print("[INFO] Using default multi-roblox mode.")
                result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq RobloxPlayerBeta.exe'], 
                                      capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                
                if result.stdout and 'RobloxPlayerBeta.exe' in result.stdout:
                    response = messagebox.askquestion(
                        "Roblox Already Running",
                        "A Roblox instance is already running.\n\n"
                        "To use Multi Roblox, you need to close all instances first.\n\n"
                        "Do you want to close all Roblox instances now?",
                        icon='warning'
                    )
                    
                    if response == 'yes':
                        subprocess.run(['taskkill', '/F', '/IM', 'RobloxPlayerBeta.exe'], 
                                     capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                        time.sleep(1)
                        messagebox.showinfo("Success", "All Roblox instances have been closed.")
                    else:
                        return False
            
            mutex = win32event.CreateMutex(None, True, "ROBLOX_singletonEvent")
            print("[INFO] Multi Roblox activated.")
            
            if win32api.GetLastError() == 183:
                print("[INFO] Mutex already exists. Took ownership.")
            
            cookies_path = os.path.join(
                os.getenv('LOCALAPPDATA'),
                r'Roblox\LocalStorage\RobloxCookies.dat'
            )
            
            cookie_file = None
            if os.path.exists(cookies_path):
                try:
                    cookie_file = open(cookies_path, 'r+b')
                    msvcrt.locking(cookie_file.fileno(), msvcrt.LK_NBLCK, os.path.getsize(cookies_path))
                    print("[INFO] Error 773 fix applied.")
                except OSError:
                    print("[WARNING] Could not lock RobloxCookies.dat. It may already be locked.")
            else:
                print("[INFO] Cookies file not found. 773 fix skipped.")

            self.multi_roblox_handle = {'mutex': mutex, 'file': cookie_file}
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to enable Multi Roblox: {str(e)}")
            return False
    
    def disable_multi_roblox(self):
        """Disable Multi Roblox and release resources"""
        try:
            if self.multi_roblox_handle:
                if self.multi_roblox_handle.get('file'):
                    try:
                        cookie_file = self.multi_roblox_handle['file']
                        cookies_path = os.path.join(
                            os.getenv('LOCALAPPDATA'),
                            r'Roblox\LocalStorage\RobloxCookies.dat'
                        )
                        if os.path.exists(cookies_path):
                            try:
                                msvcrt.locking(cookie_file.fileno(), msvcrt.LK_UNLCK, os.path.getsize(cookies_path))
                                print("[INFO] Cookie file unlocked.")
                            except Exception as unlock_error:
                                print(f"[ERROR] Failed to unlock cookie file: {unlock_error}")
                        cookie_file.close()
                    except Exception as file_error:
                        print(f"[ERROR] Failed to close cookie file: {file_error}")
                
                if self.multi_roblox_handle.get('mutex'):
                    try:
                        mutex_handle = self.multi_roblox_handle['mutex']
                        win32event.ReleaseMutex(mutex_handle)
                        win32api.CloseHandle(mutex_handle)
                        print("[INFO] Multi Roblox mutex released and closed.")
                    except Exception as mutex_error:
                        print(f"[ERROR] Failed to release mutex: {mutex_error}")
                
                self.multi_roblox_handle = None
        except Exception as e:
            print(f"Error disabling Multi Roblox: {e}")
    
    def initialize_multi_roblox(self):
        """Initialize Multi Roblox on startup if enabled in settings"""
        success = self.enable_multi_roblox()
        if not success:
            self.settings["enable_multi_roblox"] = False
            self.save_settings()

    def open_multi_roblox_method_settings(self):
        """Open Multi Roblox method selection window"""
        method_window = tk.Toplevel(self.root)
        method_window.title("Multi Roblox Method Settings")
        method_window.geometry("400x320")
        method_window.configure(bg=self.BG_DARK)
        method_window.resizable(False, False)
        method_window.transient(self.root)
        
        if self.settings.get("enable_topmost", False):
            method_window.attributes("-topmost", True)
        
        method_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (method_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (method_window.winfo_height() // 2)
        method_window.geometry(f"+{x}+{y}")
        
        current_method = self.settings.get("multi_roblox_method", "default")
        method_var = tk.StringVar(value=current_method)
        
        handle64_path = os.path.join(self.data_folder, "handle64.exe")
        handle64_exists = os.path.exists(handle64_path)
        
        container = ttk.Frame(method_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        header_frame = ttk.Frame(container, style="Dark.TFrame")
        header_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            header_frame,
            text="Select Multi Roblox Method",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text="Choose how to enable multiple Roblox instances",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(2, 0))
        
        separator = ttk.Frame(container, style="Dark.TFrame", height=1)
        separator.pack(fill="x", pady=(0, 15))
        separator.configure(relief="solid", borderwidth=1)
        
        methods_frame = ttk.Frame(container, style="Dark.TFrame")
        methods_frame.pack(fill="both", expand=True)
        
        tooltip_window = None
        tooltip_timer = None
        
        def show_tooltip(event, text):
            """Show tooltip with the same style as existing tooltips"""
            nonlocal tooltip_window, tooltip_timer
            
            if tooltip_timer:
                method_window.after_cancel(tooltip_timer)
            
            def create_tooltip():
                nonlocal tooltip_window
                if tooltip_window:
                    return
                
                x_pos = event.x_root
                y_pos = event.y_root + 20
                
                tooltip_window = tk.Toplevel(method_window)
                tooltip_window.wm_overrideredirect(True)
                tooltip_window.wm_geometry(f"+{x_pos}+{y_pos}")
                
                label = tk.Label(
                    tooltip_window,
                    text=text,
                    bg="#333333",
                    fg="white",
                    font=(self.FONT_FAMILY, 9),
                    padx=8,
                    pady=4,
                    relief="solid",
                    borderwidth=1
                )
                label.pack()
                
                if self.settings.get("enable_topmost", False):
                    tooltip_window.attributes("-topmost", True)
            
            tooltip_timer = method_window.after(500, create_tooltip)
        
        def hide_tooltip(event=None):
            """Hide tooltip"""
            nonlocal tooltip_window, tooltip_timer
            
            if tooltip_timer:
                method_window.after_cancel(tooltip_timer)
                tooltip_timer = None
            
            if tooltip_window:
                tooltip_window.destroy()
                tooltip_window = None
        
        radio_style = ttk.Style()
        radio_style.configure(
            "Dark.TRadiobutton",
            background=self.BG_DARK,
            foreground=self.FG_TEXT,
            font=(self.FONT_FAMILY, 10)
        )
        radio_style.map(
            "Dark.TRadiobutton",
            background=[("active", self.BG_DARK)],
            foreground=[("active", self.FG_TEXT)]
        )
        
        default_radio = ttk.Radiobutton(
            methods_frame,
            text="Default Method",
            variable=method_var,
            value="default",
            style="Dark.TRadiobutton"
        )
        default_radio.pack(anchor="w", pady=(0, 8))
        default_radio.bind("<Enter>", lambda e: show_tooltip(e, "Pre-create mutex. Requires closing\nexisting Roblox instances first."))
        default_radio.bind("<Leave>", hide_tooltip)
        
        handle_radio = ttk.Radiobutton(
            methods_frame,
            text="Handle64 Method (Advanced)",
            variable=method_var,
            value="handle64",
            style="Dark.TRadiobutton"
        )
        handle_radio.pack(anchor="w", pady=(0, 15))
        handle_radio.bind("<Enter>", lambda e: show_tooltip(e, "Uses handle64.exe to close handles.\nAllows multi-roblox with running instances."))
        handle_radio.bind("<Leave>", hide_tooltip)
        
        status_frame = tk.Frame(
            methods_frame,
            bg=self.BG_MID,
            relief="solid",
            borderwidth=1
        )
        status_frame.pack(fill="x", pady=(0, 10))
        
        status_inner = tk.Frame(status_frame, bg=self.BG_MID)
        status_inner.pack(fill="x", padx=10, pady=8)
        
        tk.Label(
            status_inner,
            text="handle64.exe Status:",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9),
            anchor="w"
        ).pack(side="left")
        
        status_text = "✓ Installed" if handle64_exists else "✗ Not Installed"
        status_color = "#90EE90" if handle64_exists else "#FFB6C1"
        
        status_label = tk.Label(
            status_inner,
            text=status_text,
            bg=self.BG_MID,
            fg=status_color,
            font=(self.FONT_FAMILY, 9, "bold"),
            anchor="e"
        )
        status_label.pack(side="right")
        
        download_btn = None
        if not handle64_exists:
            def download_handle64():
                """Download handle64.exe"""
                download_btn.config(state="disabled", text="Downloading...")
                method_window.update()
                
                success = self._download_handle64_exe(handle64_path)
                
                if success:
                    messagebox.showinfo("Success", "handle64.exe downloaded successfully!")
                    status_label.config(text="✓ Installed", fg="#90EE90")
                    download_btn.config(state="disabled", text="✓ Downloaded")
                else:
                    messagebox.showerror("Download Failed", "Failed to download handle64.exe. Check your internet connection.")
                    download_btn.config(state="normal", text="Download handle64.exe")
            
            download_btn = ttk.Button(
                methods_frame,
                text="Download handle64.exe",
                style="Dark.TButton",
                command=download_handle64
            )
            download_btn.pack(fill="x", pady=(0, 15))
        
        btn_container = ttk.Frame(container, style="Dark.TFrame")
        btn_container.pack(fill="x", pady=(15, 0))
        
        def save_method():
            selected = method_var.get()
            if selected == "handle64" and not os.path.exists(handle64_path):
                messagebox.showwarning(
                    "handle64 Not Available",
                    "Please download handle64.exe first."
                )
                return
            
            self.settings["multi_roblox_method"] = selected
            try:
                with open(self.settings_file, 'w') as f:
                    json.dump(self.settings, f, indent=2)
            except Exception as e:
                print(f"Failed to save settings: {e}")
            
            messagebox.showinfo("Success", f"Multi Roblox method set to: {selected.title()}")
            method_window.destroy()
        
        save_btn = ttk.Button(
            btn_container,
            text="Save",
            style="Dark.TButton",
            command=save_method
        )
        save_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        cancel_btn = ttk.Button(
            btn_container,
            text="Cancel",
            style="Dark.TButton",
            command=method_window.destroy
        )
        cancel_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))



    def open_settings(self):
        """Open the Settings window"""
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus()
            return
        
        settings_window = tk.Toplevel(self.root)
        self.settings_window = settings_window
        settings_window.title("Settings")
        settings_window.configure(bg=self.BG_DARK)
        settings_window.resizable(False, False)
        
        settings_window.transient(self.root)
        
        def on_close():
            self.settings_window = None
            settings_window.destroy()
        
        settings_window.protocol("WM_DELETE_WINDOW", on_close)
        
        if self.settings.get("enable_topmost", False):
            settings_window.attributes("-topmost", True)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        settings_width = 300
        settings_height = 385
        
        x = main_x + (main_width - settings_width) // 2
        y = main_y + (main_height - settings_height) // 2
        
        settings_window.geometry(f"{settings_width}x{settings_height}+{x}+{y}")
        
        tabs = ttk.Notebook(settings_window)
        tabs.pack(fill=tk.BOTH, expand=True)
        
        general_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(general_tab, text="General")
        
        themes_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(themes_tab, text="Themes")
        
        roblox_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(roblox_tab, text="Roblox")
        
        about_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(about_tab, text="About")
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=self.BG_DARK, borderwidth=0)
        style.configure('TNotebook.Tab', background=self.BG_MID, foreground=self.FG_TEXT, font=("Segoe UI", 9), focuscolor='none')
        style.map('TNotebook.Tab', background=[('selected', self.BG_LIGHT)], focuscolor=[('!focus', 'none')])
        
        main_frame = ttk.Frame(general_tab, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        topmost_var = tk.BooleanVar(value=self.settings.get("enable_topmost", False))
        multi_roblox_var = tk.BooleanVar(value=self.settings.get("enable_multi_roblox", False))
        confirm_launch_var = tk.BooleanVar(value=self.settings.get("confirm_before_launch", False))
        multi_select_var = tk.BooleanVar(value=self.settings.get("enable_multi_select", False))
        
        checkbox_style = ttk.Style()
        checkbox_style.configure(
            "Dark.TCheckbutton",
            background=self.BG_DARK,
            foreground="white",
            font=("Segoe UI", 10)
        )
        
        def auto_save_setting(setting_name, var):
            def save():
                self.settings[setting_name] = var.get()
                
                if setting_name == "enable_topmost":
                    self.root.attributes("-topmost", var.get())
                    settings_window.attributes("-topmost", var.get())
                
                self.save_settings()
            return save
        
        def on_multi_roblox_toggle():
            if multi_roblox_var.get():
                success = self.enable_multi_roblox()
                if not success:
                    multi_roblox_var.set(False)
                    self.settings["enable_multi_roblox"] = False
                else:
                    self.settings["enable_multi_roblox"] = True
            else:
                self.disable_multi_roblox()
                self.settings["enable_multi_roblox"] = False
            
            self.save_settings()
        
        def on_multi_select_toggle():
            self.settings["enable_multi_select"] = multi_select_var.get()
            if multi_select_var.get():
                self.account_list.config(selectmode=tk.EXTENDED)
            else:
                self.account_list.config(selectmode=tk.SINGLE)
            self.save_settings()
        
        topmost_check = ttk.Checkbutton(
            main_frame,
            text="Enable Topmost",
            variable=topmost_var,
            style="Dark.TCheckbutton",
            command=auto_save_setting("enable_topmost", topmost_var)
        )
        topmost_check.pack(anchor="w", pady=2)
        
        multi_roblox_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        multi_roblox_frame.pack(anchor="w", fill="x", pady=2)
        
        multi_roblox_check = ttk.Checkbutton(
            multi_roblox_frame,
            text="Enable Multi Roblox + 773 fix",
            variable=multi_roblox_var,
            style="Dark.TCheckbutton",
            command=on_multi_roblox_toggle
        )
        multi_roblox_check.pack(side="left", anchor="w")
        
        def open_method_settings():
            """Open Multi Roblox method selection window"""
            self.open_multi_roblox_method_settings()
        
        settings_btn = tk.Button(
            multi_roblox_frame,
            text="⚙️",
            bg=self.BG_DARK,
            fg=self.FG_TEXT,
            font=("Segoe UI", 10),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=open_method_settings,
            padx=5
        )
        settings_btn.pack(side="right", padx=(5, 0))
        
        confirm_check = ttk.Checkbutton(
            main_frame,
            text="Confirm Before Launch",
            variable=confirm_launch_var,
            style="Dark.TCheckbutton",
            command=auto_save_setting("confirm_before_launch", confirm_launch_var)
        )
        confirm_check.pack(anchor="w", pady=2)
        
        multi_select_check = ttk.Checkbutton(
            main_frame,
            text="Multi Select (Ctrl + Click)",
            variable=multi_select_var,
            style="Dark.TCheckbutton",
            command=on_multi_select_toggle
        )
        multi_select_check.pack(anchor="w", pady=2)
        
        disable_launch_popup_var = tk.BooleanVar(value=self.settings.get("disable_launch_popup", False))
        disable_launch_popup_check = ttk.Checkbutton(
            main_frame,
            text="Disable Launch Success Popup",
            variable=disable_launch_popup_var,
            style="Dark.TCheckbutton",
            command=auto_save_setting("disable_launch_popup", disable_launch_popup_var)
        )
        disable_launch_popup_check.pack(anchor="w", pady=2)
        
        ttk.Label(main_frame, text="", style="Dark.TLabel").pack(pady=5)
        
        max_games_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        max_games_frame.pack(fill="x", pady=2)
        
        ttk.Label(
            max_games_frame, 
            text="Max Recent Games:", 
            style="Dark.TLabel",
            font=("Segoe UI", 10)
        ).pack(side="left")
        
        max_games_var = tk.IntVar(value=self.settings.get("max_recent_games", 10))
        
        def on_max_games_change():
            try:
                new_value = max_games_var.get()
                self.settings["max_recent_games"] = new_value
                self.save_settings()
                if len(self.settings["game_list"]) > new_value:
                    self.settings["game_list"] = self.settings["game_list"][:new_value]
                    self.save_settings()
                    self.refresh_game_list()
            except:
                pass
        
        max_games_spinner = tk.Spinbox(
            max_games_frame,
            from_=5,
            to=50,
            textvariable=max_games_var,
            width=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_LIGHT,
            font=(self.FONT_FAMILY, 9),
            command=on_max_games_change,
            readonlybackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            selectforeground=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=0
        )
        max_games_spinner.pack(side="right")
        
        max_games_spinner.bind("<KeyRelease>", lambda e: on_max_games_change())
        max_games_spinner.bind("<FocusOut>", lambda e: on_max_games_change())
        
        ttk.Label(main_frame, text="", style="Dark.TLabel").pack(pady=3)
        
        console_button = ttk.Button(
            main_frame,
            text="Console Output",
            style="Dark.TButton",
            command=self.open_console_window
        )
        console_button.pack(fill="x", pady=(0, 5))
        
        close_button = ttk.Button(
            main_frame,
            text="Close",
            style="Dark.TButton",
            command=settings_window.destroy
        )
        close_button.pack(fill="x", pady=(5, 5))
        
        is_unstable = bool(re.search(r'(alpha|beta)', self.APP_VERSION, re.IGNORECASE))
        version_text = f"Version: {self.APP_VERSION}"
        if is_unstable:
            version_text += "\nThis is an unstable version"
        
        version_label = ttk.Label(
            main_frame,
            text=version_text,
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        )
        version_label.pack(anchor="e", pady=(6, 0))
        
        roblox_frame = ttk.Frame(roblox_tab, style="Dark.TFrame")
        roblox_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        launcher_label = ttk.Label(
            roblox_frame,
            text="Roblox Launcher:",
            style="Dark.TLabel",
            font=("Segoe UI", 10, "bold")
        )
        launcher_label.pack(anchor="w", pady=(0, 10))
        
        launcher_var = tk.StringVar(value=self.settings.get("roblox_launcher", "default"))
        
        radio_style = ttk.Style()
        radio_style.configure(
            "Dark.TRadiobutton",
            background=self.BG_DARK,
            foreground=self.FG_TEXT,
            font=("Segoe UI", 9)
        )
        radio_style.map(
            "Dark.TRadiobutton",
            background=[('active', self.BG_DARK)],
            foreground=[('active', self.FG_TEXT)]
        )
        
        def on_launcher_change():
            self.settings["roblox_launcher"] = launcher_var.get()
            self.save_settings()
        
        ttk.Radiobutton(
            roblox_frame,
            text="Default",
            variable=launcher_var,
            value="default",
            style="Dark.TRadiobutton",
            command=on_launcher_change
        ).pack(anchor="w", pady=2)
        
        ttk.Radiobutton(
            roblox_frame,
            text="Bloxstrap",
            variable=launcher_var,
            value="bloxstrap",
            style="Dark.TRadiobutton",
            command=on_launcher_change
        ).pack(anchor="w", pady=2)
        
        ttk.Radiobutton(
            roblox_frame,
            text="Fishstrap",
            variable=launcher_var,
            value="fishstrap",
            style="Dark.TRadiobutton",
            command=on_launcher_change
        ).pack(anchor="w", pady=2)
        
        ttk.Radiobutton(
            roblox_frame,
            text="Roblox Client (RobloxPlayerBeta.exe)",
            variable=launcher_var,
            value="client",
            style="Dark.TRadiobutton",
            command=on_launcher_change
        ).pack(anchor="w", pady=2)
        
        def force_close_roblox():
            try:
                result = subprocess.run(
                    ['taskkill', '/F', '/IM', 'RobloxPlayerBeta.exe'],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                if result.returncode == 0:
                    messagebox.showinfo("Success", "All Roblox instances have been closed.")
                else:
                    messagebox.showinfo("Info", "No Roblox instances were found running.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to close Roblox: {e}")
        
        force_close_btn = ttk.Button(
            roblox_frame,
            text="Force Close All Roblox",
            style="Dark.TButton",
            command=force_close_roblox
        )
        force_close_btn.pack(fill="x", pady=(15, 0))
        
        ttk.Label(
            roblox_frame,
            text="Anti-AFK Settings:",
            style="Dark.TLabel",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(10, 10))
        
        anti_afk_var = tk.BooleanVar(value=self.settings.get("anti_afk_enabled", False))
        
        def on_anti_afk_toggle():
            enabled = anti_afk_var.get()
            self.settings["anti_afk_enabled"] = enabled
            self.save_settings()
            
            if enabled:
                self.start_anti_afk()
            else:
                self.stop_anti_afk()
        
        ttk.Checkbutton(
            roblox_frame,
            text="Enable Anti-AFK",
            variable=anti_afk_var,
            style="Dark.TCheckbutton",
            command=on_anti_afk_toggle
        ).pack(anchor="w", pady=2)
        
        settings_frame = ttk.Frame(roblox_frame, style="Dark.TFrame")
        settings_frame.pack(fill="x", pady=(5, 0))
        
        action_frame = ttk.Frame(settings_frame, style="Dark.TFrame")
        action_frame.pack(fill="x", pady=2)
        
        ttk.Label(
            action_frame,
            text="Action:",
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        ).pack(side="left")
        
        action_options = ["w", "a", "s", "d", "space", "LMB", "RMB"]
        action_var = tk.StringVar(value=self.settings.get("anti_afk_key", "w"))
        
        def on_action_change(*args):
            self.settings["anti_afk_key"] = action_var.get()
            self.save_settings()
        
        action_var.trace('w', on_action_change)
        
        action_dropdown = ttk.Combobox(
            action_frame,
            textvariable=action_var,
            values=action_options,
            state="readonly",
            width=10,
            font=(self.FONT_FAMILY, 9)
        )
        action_dropdown.pack(side="right")
        
        interval_frame = ttk.Frame(settings_frame, style="Dark.TFrame")
        interval_frame.pack(fill="x", pady=2)
        
        ttk.Label(
            interval_frame,
            text="Interval (minutes):",
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        ).pack(side="left")
        
        interval_var = tk.IntVar(value=self.settings.get("anti_afk_interval_minutes", 10))
        
        def on_interval_change():
            try:
                new_value = interval_var.get()
                self.settings["anti_afk_interval_minutes"] = new_value
                self.save_settings()
            except:
                pass
        
        interval_spinner = tk.Spinbox(
            interval_frame,
            from_=1,
            to=60,
            textvariable=interval_var,
            width=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_LIGHT,
            font=(self.FONT_FAMILY, 9),
            command=on_interval_change,
            readonlybackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            selectforeground=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=0
        )
        interval_spinner.pack(side="right")
        
        interval_spinner.bind("<KeyRelease>", lambda e: on_interval_change())
        interval_spinner.bind("<FocusOut>", lambda e: on_interval_change())
        
        if self.settings.get("anti_afk_enabled", False):
            self.root.after(1000, self.start_anti_afk)
        
        themes_frame = ttk.Frame(themes_tab, style="Dark.TFrame")
        themes_frame.pack(fill="both", expand=True, padx=20, pady=15)
    
        def create_color_picker(parent, label_text, current_color, setting_key):
            frame = ttk.Frame(parent, style="Dark.TFrame")
            frame.pack(fill="x", pady=3)
            
            ttk.Label(
                frame,
                text=label_text,
                style="Dark.TLabel",
                font=("Segoe UI", 9)
            ).pack(side="left")
            
            color_display = tk.Frame(frame, bg=current_color, width=30, height=20, relief="solid", borderwidth=1)
            color_display.pack(side="right", padx=(5, 0))
            
            def pick_color():
                color = colorchooser.askcolor(initialcolor=current_color, title=f"Choose {label_text}")
                if color[1]:
                    color_display.config(bg=color[1])
                    self.settings[setting_key] = color[1]
                    self.save_settings()
            
            color_display.bind("<Button-1>", lambda e: pick_color())
            
            return frame
        
        create_color_picker(themes_frame, "Background Dark:", self.BG_DARK, "theme_bg_dark")
        create_color_picker(themes_frame, "Background Mid:", self.BG_MID, "theme_bg_mid")
        create_color_picker(themes_frame, "Background Light:", self.BG_LIGHT, "theme_bg_light")
        create_color_picker(themes_frame, "Text Color:", self.FG_TEXT, "theme_fg_text")
        create_color_picker(themes_frame, "Accent Color:", self.FG_ACCENT, "theme_fg_accent")
        
        ttk.Label(themes_frame, text="", style="Dark.TLabel").pack(pady=5)
        
        font_frame = ttk.Frame(themes_frame, style="Dark.TFrame")
        font_frame.pack(fill="x", pady=3)
        
        ttk.Label(
            font_frame,
            text="Font Family:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        ).pack(side="left")
        
        font_var = tk.StringVar(value=self.FONT_FAMILY)
        font_options = ["Segoe UI", "Arial", "Calibri", "Consolas", "Courier New", "Times New Roman", "Verdana"]
        
        font_menu = ttk.Combobox(
            font_frame,
            textvariable=font_var,
            values=font_options,
            state="readonly",
            width=15,
            font=(self.FONT_FAMILY, 9)
        )
        font_menu.pack(side="right")
        
        def on_font_change(event=None):
            self.settings["theme_font_family"] = font_var.get()
            self.save_settings()
        
        font_menu.bind("<<ComboboxSelected>>", on_font_change)
        
        size_frame = ttk.Frame(themes_frame, style="Dark.TFrame")
        size_frame.pack(fill="x", pady=3)
        
        ttk.Label(
            size_frame,
            text="Font Size:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        ).pack(side="left")
        
        size_var = tk.IntVar(value=self.FONT_SIZE)
        
        def on_size_change():
            try:
                new_size = size_var.get()
                if new_size < 8:
                    size_var.set(8)
                    new_size = 8
                elif new_size > 16:
                    size_var.set(16)
                    new_size = 16
                self.settings["theme_font_size"] = new_size
                self.save_settings()
            except:
                pass
        
        self.size_spinner = tk.Spinbox(
            size_frame,
            from_=8,
            to=16,
            textvariable=size_var,
            width=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_LIGHT,
            font=(self.FONT_FAMILY, 9),
            command=on_size_change,
            readonlybackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            selectforeground=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=0
        )
        self.size_spinner.pack(side="right")
        
        self.size_spinner.bind("<FocusOut>", lambda e: on_size_change())
        self.size_spinner.bind("<Return>", lambda e: on_size_change())
        
        
        ttk.Label(themes_frame, text="", style="Dark.TLabel").pack(pady=5)
        
        def apply_theme():
            self.BG_DARK = self.settings.get("theme_bg_dark", "#2b2b2b")
            self.BG_MID = self.settings.get("theme_bg_mid", "#3a3a3a")
            self.BG_LIGHT = self.settings.get("theme_bg_light", "#4b4b4b")
            self.FG_TEXT = self.settings.get("theme_fg_text", "white")
            self.FG_ACCENT = self.settings.get("theme_fg_accent", "#0078D7")
            self.FONT_FAMILY = self.settings.get("theme_font_family", "Segoe UI")
            self.FONT_SIZE = self.settings.get("theme_font_size", 10)
            
            self.root.configure(bg=self.BG_DARK)
            if hasattr(self, 'settings_window') and self.settings_window:
                self.settings_window.configure(bg=self.BG_DARK)
            if hasattr(self, 'star_btn') and self.star_btn:
                self.star_btn.config(bg=self.BG_DARK)
            if hasattr(self, 'auto_rejoin_btn') and self.auto_rejoin_btn:
                self.auto_rejoin_btn.config(bg=self.BG_DARK)
            
            style = ttk.Style()
            style.configure("Dark.TFrame", background=self.BG_DARK)
            style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
            style.configure("Dark.TButton", background=self.BG_MID, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE - 1))
            style.map("Dark.TButton", background=[("active", self.BG_LIGHT)])
            style.configure("Dark.TEntry", fieldbackground=self.BG_MID, background=self.BG_MID, foreground=self.FG_TEXT)
            style.configure("Dark.TCheckbutton", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
            style.configure("Dark.TRadiobutton", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
            style.map("Dark.TRadiobutton", background=[('active', self.BG_DARK)], foreground=[('active', self.FG_TEXT)])
            
            style.configure('TNotebook', background=self.BG_DARK, borderwidth=0)
            style.configure('TNotebook.Tab', background=self.BG_MID, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, 9), focuscolor='none')
            style.map('TNotebook.Tab', background=[('selected', self.BG_LIGHT)], focuscolor=[('!focus', 'none')])
            
            settings_window.configure(bg=self.BG_DARK)
            
            self.account_list.configure(
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                selectbackground=self.FG_ACCENT
            )
            
            self.game_list.configure(
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                selectbackground=self.FG_ACCENT
            )
            
            self.encryption_label.configure(bg=self.BG_DARK)
            
            self.size_spinner.configure(
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                buttonbackground=self.BG_LIGHT,
                readonlybackground=self.BG_MID,
                selectbackground=self.FG_ACCENT,
                insertbackground=self.FG_TEXT
            )
            
            max_games_spinner.configure(
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                buttonbackground=self.BG_LIGHT,
                readonlybackground=self.BG_MID,
                selectbackground=self.FG_ACCENT,
                insertbackground=self.FG_TEXT
            )
            
            messagebox.showinfo("Theme Applied", "Theme has been updated successfully!")
        
        def reset_theme():
            confirm = messagebox.askyesno(
                "Reset Theme",
                "Are you sure you want to reset all theme settings to default?"
            )
            if confirm:
                self.settings["theme_bg_dark"] = "#2b2b2b"
                self.settings["theme_bg_mid"] = "#3a3a3a"
                self.settings["theme_bg_light"] = "#4b4b4b"
                self.settings["theme_fg_text"] = "white"
                self.settings["theme_fg_accent"] = "#0078D7"
                self.settings["theme_font_family"] = "Segoe UI"
                self.settings["theme_font_size"] = 10
                self.save_settings()
                apply_theme()
                
                for widget in themes_frame.winfo_children():
                    widget.destroy()
                
                settings_window.destroy()
                self.open_settings()
        
        button_frame = ttk.Frame(themes_frame, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(5, 0))
        
        ttk.Button(
            button_frame,
            text="Save & Apply",
            style="Dark.TButton",
            command=apply_theme
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        
        ttk.Button(
            button_frame,
            text="Reset to Default",
            style="Dark.TButton",
            command=reset_theme
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))
        
        about_frame = ttk.Frame(about_tab, style="Dark.TFrame")
        about_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        ttk.Label(
            about_frame,
            text="Roblox Account Manager",
            style="Dark.TLabel",
            font=("Segoe UI", 14, "bold")
        ).pack(anchor="center", pady=(10, 5))
        
        is_unstable = bool(re.search(r'(alpha|beta)', self.APP_VERSION, re.IGNORECASE))
        version_text = f"Version {self.APP_VERSION}"
        
        ttk.Label(
            about_frame,
            text=version_text,
            style="Dark.TLabel",
            font=("Segoe UI", 10)
        ).pack(anchor="center", pady=(0, 5))
        
        if is_unstable:
            ttk.Label(
                about_frame,
                text="⚠️ This is an unstable version",
                style="Dark.TLabel",
                font=("Segoe UI", 9, "italic"),
                foreground="#FFA500"
            ).pack(anchor="center", pady=(0, 10))
        else:
            ttk.Label(about_frame, text="", style="Dark.TLabel").pack(pady=(0, 10))
        
        ttk.Label(
            about_frame,
            text="Made by evanovar",
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        ).pack(anchor="center", pady=(5, 15))
        
        def copy_discord():
            discord_server = "https://discord.gg/SZaZU8zwZA"
            self.root.clipboard_clear()
            self.root.clipboard_append(discord_server)
            self.root.update()
            messagebox.showinfo("Copied!", f"Discord server '{discord_server}' copied to clipboard!")
        
        ttk.Button(
            about_frame,
            text="Copy Discord Server",
            style="Dark.TButton",
            command=copy_discord
        ).pack(fill="x", pady=(0, 10))
        
        def open_github():
            webbrowser.open("https://github.com/evanovar/RobloxAccountManager")

        
        ttk.Button(
            about_frame,
            text="Open GitHub Repository",
            style="Dark.TButton",
            command=open_github
        ).pack(fill="x", pady=(0, 10))
        
        
    
    def write(self, text):
        """Redirect stdout/stderr writes to console"""
        if text.strip():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_to_console(f"[{timestamp}] {text}\n")
        if self.original_stdout:
            self.original_stdout.write(text)
    
    def flush(self):
        """Flush stdout"""
        if self.original_stdout:
            self.original_stdout.flush()
    
    def log_to_console(self, message):
        """Log message to console output buffer"""
        self.console_output.append(message)
        
        if self.console_text_widget:
            try:
                self.console_text_widget.config(state="normal")
                self.console_text_widget.insert(tk.END, message)
                self.console_text_widget.see(tk.END)
                self.console_text_widget.config(state="disabled")
            except:
                pass
    
    def open_console_window(self):
        """Open the Console Output window"""
        if self.console_window and tk.Toplevel.winfo_exists(self.console_window):
            self.console_window.focus()
            return
        
        self.console_window = tk.Toplevel(self.root)
        self.console_window.title("Console Output")
        self.console_window.geometry("700x500")
        self.console_window.configure(bg=self.BG_DARK)
        self.console_window.minsize(500, 450)
        
        if self.settings.get("enable_topmost", False):
            self.console_window.attributes("-topmost", True)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 700) // 2
        y = main_y + (main_height - 500) // 2
        self.console_window.geometry(f"700x500+{x}+{y}")
        
        main_frame = ttk.Frame(self.console_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(
            main_frame,
            text="Console Output",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        )
        title_label.pack(anchor="w", pady=(0, 10))
        
        text_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        text_frame.pack(fill="both", expand=True)
        
        self.console_text_widget = tk.Text(
            text_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Consolas", 9),
            wrap="word",
            state="disabled"
        )
        self.console_text_widget.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame, command=self.console_text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.console_text_widget.config(yscrollcommand=scrollbar.set)
        
        self.console_text_widget.config(state="normal")
        for message in self.console_output:
            self.console_text_widget.insert(tk.END, message)
        self.console_text_widget.config(state="disabled")
        
        self.console_text_widget.see(tk.END)
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(10, 0))
        
        def clear_console():
            self.console_output.clear()
            self.console_text_widget.config(state="normal") 
            self.console_text_widget.delete(1.0, tk.END)
            self.console_text_widget.config(state="disabled") 
        
        def copy_all():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.console_text_widget.get(1.0, tk.END))
            messagebox.showinfo("Copied", "Console output copied to clipboard!")
        
        ttk.Button(
            button_frame,
            text="Clear",
            style="Dark.TButton",
            command=clear_console
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Copy All",
            style="Dark.TButton",
            command=copy_all
        ).pack(side="left", fill="x", expand=True, padx=5)
        
        ttk.Button(
            button_frame,
            text="Close",
            style="Dark.TButton",
            command=self.console_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def on_close():
            self.console_text_widget = None
            self.console_window.destroy()
            self.console_window = None
        
        self.console_window.protocol("WM_DELETE_WINDOW", on_close)
    
    def open_favorites_window(self):
        """Open the favorites management window"""
        favorites_window = tk.Toplevel(self.root)
        favorites_window.title("Favorite Games")
        favorites_window.configure(bg=self.BG_DARK)
        favorites_window.resizable(False, False)
        
        self.root.update_idletasks()
        x = self.root.winfo_x() + 50
        y = self.root.winfo_y() + 50
        favorites_window.geometry(f"400x350+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            favorites_window.attributes("-topmost", True)
        
        favorites_window.transient(self.root)
        favorites_window.focus_force()
        
        main_frame = ttk.Frame(favorites_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        ttk.Label(
            main_frame,
            text="Favorite Games",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        list_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        favorites_list = tk.Listbox(
            list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 9)
        )
        favorites_list.grid(row=0, column=0, sticky="nsew")
        
        v_scrollbar = ttk.Scrollbar(list_frame, command=favorites_list.yview, orient="vertical")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        favorites_list.config(yscrollcommand=v_scrollbar.set)
        
        h_scrollbar = ttk.Scrollbar(list_frame, command=favorites_list.xview, orient="horizontal")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        favorites_list.config(xscrollcommand=h_scrollbar.set)
        
        def refresh_favorites():
            favorites_list.delete(0, tk.END)
            for fav in self.settings.get("favorite_games", []):
                private_server = fav.get("private_server", "")
                note = fav.get("note", "")
                prefix = "[P] " if private_server else ""
                display = f"{prefix}{fav['name']}"
                if note:
                    display += f" • {note}"
                favorites_list.insert(tk.END, display)
        
        refresh_favorites()
        
        def on_favorite_click(event):
            """Load selected favorite into main UI when clicked"""
            selection = favorites_list.curselection()
            if not selection:
                return
            
            index = selection[0]
            fav = self.settings["favorite_games"][index]
            
            self.place_entry.delete(0, tk.END)
            self.place_entry.insert(0, fav["place_id"])
            self.settings["last_place_id"] = fav["place_id"]
            
            private_server = fav.get("private_server", "")
            self.private_server_entry.delete(0, tk.END)
            self.private_server_entry.insert(0, private_server)
            self.settings["last_private_server"] = private_server
            
            self.save_settings()
            self.update_game_name()
        
        favorites_list.bind("<<ListboxSelect>>", on_favorite_click)
        
        btn_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        btn_frame.pack(fill="x")
        
        def add_favorite():
            """Open dialog to add a new favorite"""
            add_window = tk.Toplevel(favorites_window)
            add_window.title("Add Favorite")
            add_window.configure(bg=self.BG_DARK)
            add_window.resizable(False, False)
            
            favorites_window.update_idletasks()
            x = favorites_window.winfo_x() + 50
            y = favorites_window.winfo_y() + 50
            add_window.geometry(f"400x250+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                add_window.attributes("-topmost", True)
            
            add_window.transient(favorites_window)
            add_window.focus_force()
            
            form_frame = ttk.Frame(add_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            ttk.Label(form_frame, text="Place ID:", style="Dark.TLabel").pack(anchor="w")
            place_id_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            place_id_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Private Server ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            ps_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            ps_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Note (Optional):", style="Dark.TLabel").pack(anchor="w")
            note_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            note_entry.pack(fill="x", pady=(0, 10))
            
            def save_favorite():
                place_id = place_id_entry.get().strip()
                
                if not place_id:
                    messagebox.showerror("Error", "Place ID is required!")
                    return
                
                name = RobloxAPI.get_game_name(place_id)
                if not name:
                    messagebox.showerror("Error", "Could not fetch game name. Please check the Place ID.")
                    return
                
                favorite = {
                    "place_id": place_id,
                    "name": name,
                    "private_server": ps_entry.get().strip(),
                    "note": note_entry.get().strip()
                }
                
                if "favorite_games" not in self.settings:
                    self.settings["favorite_games"] = []
                
                self.settings["favorite_games"].append(favorite)
                self.save_settings()
                refresh_favorites()
                add_window.destroy()
                messagebox.showinfo("Success", f"Added '{name}' to favorites!")
                favorites_window.lift()
                favorites_window.focus_force()
            
            button_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            button_frame.pack(fill="x", pady=(10, 0))
            
            ttk.Button(
                button_frame,
                text="Save",
                style="Dark.TButton",
                command=save_favorite
            ).pack(side="left", fill="x", expand=True, padx=(0, 5))
            
            ttk.Button(
                button_frame,
                text="Cancel",
                style="Dark.TButton",
                command=add_window.destroy
            ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def edit_favorite():
            """Edit selected favorite"""
            selection = favorites_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a favorite to edit.")
                return
            
            index = selection[0]
            fav = self.settings["favorite_games"][index]
            
            edit_window = tk.Toplevel(favorites_window)
            edit_window.title("Edit Favorite")
            edit_window.configure(bg=self.BG_DARK)
            edit_window.resizable(False, False)
            
            favorites_window.update_idletasks()
            x = favorites_window.winfo_x() + 50
            y = favorites_window.winfo_y() + 50
            edit_window.geometry(f"400x250+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                edit_window.attributes("-topmost", True)
            
            edit_window.transient(favorites_window)
            edit_window.focus_force()
            
            form_frame = ttk.Frame(edit_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            ttk.Label(form_frame, text="Place ID:", style="Dark.TLabel").pack(anchor="w")
            place_id_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            place_id_entry.insert(0, fav["place_id"])
            place_id_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Private Server ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            ps_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            ps_entry.insert(0, fav.get("private_server", ""))
            ps_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Note (Optional):", style="Dark.TLabel").pack(anchor="w")
            note_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            note_entry.insert(0, fav.get("note", ""))
            note_entry.pack(fill="x", pady=(0, 10))
            
            def save_edit():
                place_id = place_id_entry.get().strip()
                
                if not place_id:
                    messagebox.showerror("Error", "Place ID is required!")
                    return
                
                if place_id != fav["place_id"]:
                    name = RobloxAPI.get_game_name(place_id)
                    if not name:
                        messagebox.showerror("Error", "Could not fetch game name. Please check the Place ID.")
                        return
                else:
                    name = fav["name"]
                
                self.settings["favorite_games"][index] = {
                    "place_id": place_id,
                    "name": name,
                    "private_server": ps_entry.get().strip(),
                    "note": note_entry.get().strip()
                }
                
                self.save_settings()
                refresh_favorites()
                edit_window.destroy()
                messagebox.showinfo("Success", "Favorite updated!")
                favorites_window.lift()
                favorites_window.focus_force()
            
            
            button_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            button_frame.pack(fill="x", pady=(10, 0))
            
            ttk.Button(
                button_frame,
                text="Save",
                style="Dark.TButton",
                command=save_edit
            ).pack(side="left", fill="x", expand=True, padx=(0, 5))
            
            ttk.Button(
                button_frame,
                text="Cancel",
                style="Dark.TButton",
                command=edit_window.destroy
            ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def remove_favorite():
            """Remove selected favorite"""
            selection = favorites_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a favorite to remove.")
                return
            
            index = selection[0]
            fav = self.settings["favorite_games"][index]
            
            confirm = messagebox.askyesno(
                "Confirm Delete",
                f"Remove '{fav['name']}' from favorites?"
            )
            
            if confirm:
                self.settings["favorite_games"].pop(index)
                self.save_settings()
                refresh_favorites()
                messagebox.showinfo("Success", "Favorite removed!")
                favorites_window.lift()
                favorites_window.focus_force()
        
        ttk.Button(
            btn_frame,
            text="Add Favorite",
            style="Dark.TButton",
            command=add_favorite
        ).pack(side="left", fill="x", expand=True, padx=(0, 2))
        
        ttk.Button(
            btn_frame,
            text="Edit",
            style="Dark.TButton",
            command=edit_favorite
        ).pack(side="left", fill="x", expand=True, padx=2)
        
        ttk.Button(
            btn_frame,
            text="Remove",
            style="Dark.TButton",
            command=remove_favorite
        ).pack(side="left", fill="x", expand=True, padx=2)
        
        ttk.Button(
            btn_frame,
            text="Close",
            style="Dark.TButton",
            command=favorites_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(2, 0))
    
    def start_anti_afk(self):
        """Start the Anti-AFK background thread"""
        if self.anti_afk_thread and self.anti_afk_thread.is_alive():
            return
        
        self.anti_afk_stop_event.clear()
        self.anti_afk_thread = threading.Thread(target=self.anti_afk_worker, daemon=True)
        self.anti_afk_thread.start()
        print("[Anti-AFK] Started")
    
    def stop_anti_afk(self):
        """Stop the Anti-AFK background thread"""
        if self.anti_afk_thread and self.anti_afk_thread.is_alive():
            self.anti_afk_stop_event.set()
            self.anti_afk_thread.join(timeout=2)
            print("[Anti-AFK] Stopped")
    
    def start_auto_rejoin_for_account(self, account):
        """Start the auto-rejoin background thread for a specific account"""
        if account in self.auto_rejoin_threads and self.auto_rejoin_threads[account].is_alive():
            return
        
        if account not in self.auto_rejoin_configs:
            print(f"[Auto-Rejoin] No config found for {account}")
            return
        
        stop_event = threading.Event()
        self.auto_rejoin_stop_events[account] = stop_event
        
        thread = threading.Thread(
            target=self.auto_rejoin_worker_for_account,
            args=(account,),
            daemon=True
        )
        self.auto_rejoin_threads[account] = thread
        thread.start()
        print(f"[Auto-Rejoin] Started for {account}")
    
    def stop_auto_rejoin_for_account(self, account):
        """Stop the auto-rejoin background thread for a specific account"""
        if account in self.auto_rejoin_stop_events:
            self.auto_rejoin_stop_events[account].set()
        
        if account in self.auto_rejoin_threads:
            thread = self.auto_rejoin_threads[account]
            if thread.is_alive():
                thread.join(timeout=2)
            del self.auto_rejoin_threads[account]
        
        if account in self.auto_rejoin_stop_events:
            del self.auto_rejoin_stop_events[account]
        
        print(f"[Auto-Rejoin] Stopped for {account}")
    
    def stop_all_auto_rejoin(self):
        """Stop all auto-rejoin threads"""
        for account in list(self.auto_rejoin_threads.keys()):
            self.stop_auto_rejoin_for_account(account)
    
    def is_roblox_running(self):
        """Check if any Roblox window exists"""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Roblox")
            return hwnd != 0
        except:
            return False
    
    def is_player_in_game(self, user_id, cookie, expected_place_id):
        """Check if player is still in the same game using Presence API"""
        try:
            presence = RobloxAPI.get_player_presence(user_id, cookie)
            
            if presence:
                in_game = presence.get('in_game', False)
                place_id = presence.get('place_id')
                
                if in_game and place_id == int(expected_place_id):
                    return True, place_id, presence.get('game_id')
            
            return False, None, None
        except Exception as e:
            print(f"[Auto-Rejoin] Error checking player status: {e}")
            return False, None, None
    
    def auto_rejoin_worker_for_account(self, account):
        """Background worker that monitors for disconnection and rejoins for a specific account"""        
        config = self.auto_rejoin_configs.get(account, {})
        stop_event = self.auto_rejoin_stop_events.get(account)
        
        if not stop_event:
            return
        
        retry_count = 0
        max_retries = config.get('max_retries', 5)
        check_interval = config.get('check_interval', 10)
        place_id = config.get('place_id')
        private_server = config.get('private_server', '')
        job_id = config.get('job_id', '')
        
        if not place_id:
            print(f"[Auto-Rejoin] Invalid configuration for {account}")
            return
        
        if account not in self.manager.accounts:
            print(f"[Auto-Rejoin] Account {account} not found")
            return
        
        account_data = self.manager.accounts[account]
        cookie = account_data.get('cookie')
        
        user_id = RobloxAPI.get_user_id_from_username(account)
        if not user_id:
            print(f"[Auto-Rejoin] Could not get user ID for {account}")
            return
        
        print(f"[Auto-Rejoin] Started monitoring {account} for game {place_id}")
        
        while not stop_event.is_set():
            try:
                if not self.is_roblox_running():
                    print(f"[Auto-Rejoin] [{account}] Roblox not running - launching game...")
                    
                    launcher_pref = self.settings.get("roblox_launcher", "default")
                    success = self.manager.launch_roblox(account, place_id, private_server, launcher_pref, job_id)
                    
                    if success:
                        print(f"[Auto-Rejoin] [{account}] Game launched successfully")
                        time.sleep(10)
                    else:
                        retry_count += 1
                        if retry_count >= max_retries:
                            print(f"[Auto-Rejoin] [{account}] Max retries ({max_retries}) reached. Stopping.")
                            break
                        time.sleep(check_interval)
                    continue
                
                in_game, current_place_id, game_id = self.is_player_in_game(user_id, cookie, place_id)
                
                if not in_game:
                    print(f"[Auto-Rejoin] [{account}] Disconnection detected! Rejoining... (Attempt {retry_count + 1}/{max_retries})")
                    
                    rejoin_job_id = job_id if job_id else (game_id if game_id else '')
                    
                    launcher_pref = self.settings.get("roblox_launcher", "default")
                    success = self.manager.launch_roblox(account, place_id, private_server, launcher_pref, rejoin_job_id)
                    
                    if success:
                        retry_count = 0
                        print(f"[Auto-Rejoin] [{account}] Rejoin attempt successful")
                        time.sleep(5)
                    else:
                        retry_count += 1
                        if retry_count >= max_retries:
                            print(f"[Auto-Rejoin] [{account}] Max retries ({max_retries}) reached. Stopping.")
                            break
                        time.sleep(check_interval)
                else:
                    print(f"[Auto-Rejoin] [{account}] Still in game {place_id}")
                    retry_count = 0
                    time.sleep(check_interval)
                    
            except Exception as e:
                print(f"[Auto-Rejoin] [{account}] Error: {e}")
                time.sleep(check_interval)
      
    def anti_afk_worker(self):
        """Background worker that sends key presses to Roblox windows"""
        last_window_count = 0
        window_timers = {}
        
        while not self.anti_afk_stop_event.is_set():
            try:
                interval_minutes = self.settings.get("anti_afk_interval_minutes", 10)
                key = self.settings.get("anti_afk_key", "w")
                current_time = time.time()
                
                for _ in range(interval_minutes * 60):
                    if self.anti_afk_stop_event.wait(1):
                        return
                
                self.send_key_to_roblox_windows_staggered(key, window_timers, current_time)
                
            except Exception as e:
                print(f"[Anti-AFK] Error: {e}")
                time.sleep(5)
    
    def send_key_to_roblox_windows(self, action):
        """Send a key press or mouse click to all Roblox windows using Windows API"""
        try:
            WM_KEYDOWN = 0x0100
            WM_KEYUP = 0x0101
            WM_LBUTTONDOWN = 0x0201
            WM_LBUTTONUP = 0x0202
            WM_RBUTTONDOWN = 0x0204
            WM_RBUTTONUP = 0x0205
            
            vk_codes = {
                'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44,
                'space': 0x20, ' ': 0x20,
                'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12
            }
            
            is_mouse = action.upper() in ['LMB', 'RMB']
            
            if not is_mouse:
                action_lower = action.lower()
                if action_lower in vk_codes:
                    vk_code = vk_codes[action_lower]
                elif len(action) == 1:
                    vk_code = ord(action.upper())
                else:
                    print(f"[Anti-AFK] Unknown action: {action}")
                    return
            
            user32 = ctypes.windll.user32
            
            def is_roblox_game_window(title):
                """Check if window is an actual Roblox game instance"""
                return title.strip() == "Roblox"
            
            def enum_windows_callback(hwnd, lParam):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        
                        if is_roblox_game_window(title):
                            if is_mouse:
                                if action.upper() == 'LMB':
                                    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, 0)
                                    time.sleep(0.05)
                                    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, 0)
                                    print(f"[Anti-AFK] Sent LMB click")
                                elif action.upper() == 'RMB':
                                    user32.PostMessageW(hwnd, WM_RBUTTONDOWN, 2, 0)
                                    time.sleep(0.05)
                                    user32.PostMessageW(hwnd, WM_RBUTTONUP, 0, 0)
                                    print(f"[Anti-AFK] Sent RMB click")
                            else:
                                user32.PostMessageW(hwnd, WM_KEYDOWN, vk_code, 0)
                                time.sleep(0.05)
                                user32.PostMessageW(hwnd, WM_KEYUP, vk_code, 0)
                                print(f"[Anti-AFK] Sent '{action}'")
                return True
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
            
        except Exception as e:
            print(f"[Anti-AFK] Failed to send action: {e}")
    
    def send_key_to_roblox_windows_staggered(self, action, window_timers, current_time):
        """Send key presses to Roblox windows"""
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            vk_codes = {
                'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44,
                'space': 0x20, ' ': 0x20,
                'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12
            }
            
            KEYEVENTF_KEYUP = 0x0002
            SW_RESTORE = 9
            SW_MINIMIZE = 6
            
            is_mouse = action.upper() in ['LMB', 'RMB']
            
            if not is_mouse:
                action_lower = action.lower()
                if action_lower in vk_codes:
                    vk_code = vk_codes[action_lower]
                elif len(action) == 1:
                    vk_code = ord(action.upper())
                else:
                    print(f"[Anti-AFK] Unknown action: {action}")
                    return
            
            roblox_windows = []
            
            def is_roblox_game_window(title):
                return title.strip() == "Roblox"
            
            def enum_windows_callback(hwnd, lParam):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        if is_roblox_game_window(title):
                            roblox_windows.append(hwnd)
                return True
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
            
            if not roblox_windows:
                print("[Anti-AFK] No Roblox game windows found")
                return
            
            original_hwnd = user32.GetForegroundWindow()
            current_thread_id = kernel32.GetCurrentThreadId()
            
            print(f"[Anti-AFK] Found {len(roblox_windows)} Roblox instance(s)")
            
            for idx, hwnd in enumerate(roblox_windows):
                try:
                    print(f"[Anti-AFK] Processing instance {idx + 1}...")
                    
                    was_minimized = user32.IsIconic(hwnd)
                    if was_minimized:
                        user32.ShowWindow(hwnd, SW_RESTORE)
                        time.sleep(0.05)
                    
                    user32.SetForegroundWindow(hwnd)
                    time.sleep(0.05)
                    
                    for repeat in range(3):
                        if is_mouse:
                            MOUSEEVENTF_LEFTDOWN = 0x0002
                            MOUSEEVENTF_LEFTUP = 0x0004
                            MOUSEEVENTF_RIGHTDOWN = 0x0008
                            MOUSEEVENTF_RIGHTUP = 0x0010
                            
                            if action.upper() == 'LMB':
                                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                time.sleep(0.015)
                                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            elif action.upper() == 'RMB':
                                user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                                time.sleep(0.015)
                                user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                        else:
                            scan_code = user32.MapVirtualKeyW(vk_code, 0)
                            user32.keybd_event(vk_code, scan_code, 0, 0)
                            time.sleep(0.015)
                            user32.keybd_event(vk_code, scan_code, KEYEVENTF_KEYUP, 0)
                    
                    print(f"[Anti-AFK] Sent '{action}' to Roblox instance {idx + 1}")
                    
                    if was_minimized:
                        user32.ShowWindow(hwnd, SW_MINIMIZE)
                    
                except Exception as e:
                    print(f"[Anti-AFK] Error on instance {idx + 1}: {e}")
            
            if original_hwnd:
                prev_thread_id = user32.GetWindowThreadProcessId(original_hwnd, None)
                user32.AttachThreadInput(current_thread_id, prev_thread_id, True)
                user32.BringWindowToTop(original_hwnd)
                user32.SetForegroundWindow(original_hwnd)
                user32.AttachThreadInput(current_thread_id, prev_thread_id, False)
            
            print(f"[Anti-AFK] Completed for {len(roblox_windows)} instance(s)")
            
        except Exception as e:
            print(f"[Anti-AFK] Failed: {e}")
            traceback.print_exc()
