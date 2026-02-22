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
import win32gui
from datetime import datetime, timedelta, timezone
import zipfile
import tempfile
import shutil
import platform
import traceback
import psutil
import random
import stat
import math
import win32process
from urllib.request import urlretrieve
from classes.roblox_api import RobloxAPI
from classes.account_manager import RobloxAccountManager
from utils.encryption_setup import EncryptionSetupUI

class AccountManagerUI:
    def __init__(self, root, manager, icon_path=None, discord_logo_path=None):
        self.root = root
        self.manager = manager
        self.icon_path = icon_path
        self.discord_logo_path = discord_logo_path
        self.discord_logo_img = None
        self.APP_VERSION = "2.4.5"
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
        
        saved_pos = self.settings.get('main_window_position')
        if saved_pos:
            self.root.geometry(f"450x520+{saved_pos['x']}+{saved_pos['y']}")
        else:
            self.root.geometry("450x520")
        self.root.configure(bg=self.settings.get("theme_bg_dark", "#2b2b2b"))
        self.root.resizable(False, False)
        
        self.multi_roblox_handle = None
        self.handle64_monitoring = False
        self.handle64_monitor_thread = None
        self.handle64_path = None
        
        self.anti_afk_thread = None
        self.anti_afk_stop_event = threading.Event()
        
        self.rename_thread = None
        self.rename_stop_event = threading.Event()
        self.renamed_pids = set()
        
        self.instances_monitor_thread = None
        self.instances_monitor_stop = threading.Event()
        self.instances_data = []
        self.instances_pids = set()
        self.instances_failed_pids = {} 
        self.instances_data_updated = False
        self.instances_cache = {
            "user_id_to_username": {},
            "user_id_to_avatar": {},
            "user_id_to_photo": {}
        }
        
        self.auto_rejoin_threads = {}
        self.auto_rejoin_stop_events = {}
        self.auto_rejoin_configs = self.settings.get("auto_rejoin_configs", {})
        self.auto_rejoin_pids = {}
        self.auto_rejoin_launch_lock = threading.Lock()
        self._webhook_screenshot_thread = None
        
        self.cookie_status = {}
        for _u, _d in self.manager.accounts.items():
            if isinstance(_d, dict):
                self.cookie_status[_u] = _d.get('cookie_valid', None)
        self.account_tooltip = None
        self.account_tooltip_timer = None
        self.account_tooltip_last_index = None


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
        style.configure("Dark.TCheckbutton", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
        style.map("Dark.TCheckbutton", background=[("active", self.BG_DARK)], foreground=[("active", self.FG_TEXT)])

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
        self.account_list.bind("<Button-3>", self.show_account_context_menu)
        self.account_list.bind("<Motion>", self.on_account_list_hover)
        self.account_list.bind("<Leave>", self.on_account_list_leave)

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

        quick_actions_row = ttk.Frame(right_frame, style="Dark.TFrame")
        quick_actions_row.pack(fill="x", pady=(10, 5))
        ttk.Label(quick_actions_row, text="Quick Actions", style="Dark.TLabel").pack(side="left")
        self.quick_actions_row = quick_actions_row
        self.discord_btn = None

        _discord_img = None
        if self.discord_logo_path and os.path.exists(self.discord_logo_path):
            try:
                _discord_img = tk.PhotoImage(file=self.discord_logo_path)
                _w, _h = _discord_img.width(), _discord_img.height()
                _factor = max(1, max(_w, _h) // 20)
                if _factor > 1:
                    _discord_img = _discord_img.subsample(_factor, _factor)
                self.discord_logo_img = _discord_img
            except Exception:
                _discord_img = None

        if _discord_img:
            self.discord_btn = tk.Button(
                quick_actions_row,
                image=_discord_img,
                bg=self.BG_DARK,
                activebackground=self.BG_DARK,
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=0,
                pady=0,
                highlightthickness=0,
                command=lambda: webbrowser.open("https://discord.gg/SZaZU8zwZA")
            )
            self.discord_btn.pack(side="right")

        action_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        action_frame.pack(fill="x")

        ttk.Button(action_frame, text="Donate", style="Dark.TButton", command=lambda: webbrowser.open("https://www.roblox.com/games/718090786/donation#!/store")).pack(fill="x", pady=2)
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
        self.update_game_name_on_startup()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        threading.Thread(target=self.check_for_updates, daemon=True).start()
        threading.Thread(target=self._silent_check_cookies_worker, daemon=True).start()
        threading.Thread(target=self._watch_discord_logo, daemon=True).start()
        
        if self.settings.get("lock_roblox_settings", False):
            self.root.after(1000, self.apply_and_lock_roblox_settings)
    
    def on_closing(self):
        """Handle application closing - restore installers and exit"""
        
        self.settings['main_window_position'] = {
            'x': self.root.winfo_x(),
            'y': self.root.winfo_y()
        }
        self.save_settings(force_immediate=True)
        
        if hasattr(self, 'anti_afk_stop_event'):
            self.stop_anti_afk()
        
        if hasattr(self, 'rename_stop_event'):
            self.stop_rename_monitoring()
        
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
                    "multi_roblox_method": "default",
                    "last_joined_user": "",
                    "auto_tile_windows": True,
                    "rejoin_webhook": {}
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
                "multi_roblox_method": "default",
                "last_joined_user": "",
                "auto_tile_windows": True,
                "rejoin_webhook": {}
            }
        
        if self.settings.get("enable_topmost", False):
            self.root.attributes("-topmost", True)
        
        if self.settings.get("enable_multi_roblox", False):
            self.root.after(100, self.initialize_multi_roblox)

    def apply_window_icon(self, window):
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                window.iconbitmap(self.icon_path)
            except Exception as e:
                print(f"[ERROR] Could not set window icon: {e}")

    def check_for_updates(self):
        """Check for updates from GitHub releases"""
        try:
            print("[INFO] Checking for updates...")
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
                    print(f"[WARNING] New version available: {latest_version}")
                    self.root.after(0, lambda: self.show_update_notification(latest_version))
                else:
                    print(f"[SUCCESS] You are on the latest version ({self.APP_VERSION})")
            else:
                print(f"[ERROR] Failed to check for updates (Status: {response.status_code})")
                
        except Exception as e:
            print(f"[ERROR] Error checking for updates: {str(e)}")

    def show_update_notification(self, latest_version):
        """Show update notification dialog with download options"""
        update_window = tk.Toplevel(self.root)
        self.apply_window_icon(update_window)
        update_window.title("Update Available")
        update_window.geometry("450x280")
        update_window.configure(bg=self.BG_DARK)
        update_window.resizable(False, False)
        update_window.transient(self.root)
        
        if self.settings.get("enable_topmost", False):
            update_window.attributes("-topmost", True)
        
        update_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (update_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (update_window.winfo_height() // 2)
        update_window.geometry(f"+{x}+{y}")
        
        container = ttk.Frame(update_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            container,
            text="🎉 New Update Available!",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 12, "bold")
        ).pack(anchor="w", pady=(0, 15))
        
        info_frame = ttk.Frame(container, style="Dark.TFrame", relief="solid", borderwidth=0)
        info_frame.pack(fill="x", pady=(0, 15))
        
        info_inner = ttk.Frame(info_frame, style="Dark.TFrame")
        info_inner.pack(fill="x", padx=15, pady=12)
        
        ttk.Label(
            info_inner,
            text=f"Current Version: {self.APP_VERSION}",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        ).pack(fill="x")
        
        ttk.Label(
            info_inner,
            text=f"Latest Version: {latest_version}",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9, "bold")
        ).pack(fill="x", pady=(5, 0))
        
        progress_outer = tk.Frame(container, bg=self.BG_LIGHT, relief="solid", borderwidth=1)
        progress_outer.pack(fill="x", pady=(0, 10))
        
        progress_inner = tk.Frame(progress_outer, bg=self.BG_MID, height=22)
        progress_inner.pack(fill="x", padx=1, pady=1)
        progress_inner.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_inner, bg=self.BG_LIGHT, width=0)
        progress_fill.place(x=0, y=0, relheight=1)
        
        progress_label = tk.Label(
            progress_inner,
            text="0%",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        progress_label.place(relx=0.5, rely=0.5, anchor="center")
        
        status_label = ttk.Label(
            container,
            text="Choose how to update:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        )
        status_label.pack(anchor="w", pady=(5, 8))
        
        btn_frame = ttk.Frame(container, style="Dark.TFrame")
        btn_frame.pack(side="bottom", fill="x")
        
        def update_progress(percent):
            """Update the custom progress bar"""
            progress_inner.update_idletasks()
            total_width = progress_inner.winfo_width()
            fill_width = int((percent / 100) * total_width)
            progress_fill.place(x=0, y=0, relheight=1, width=fill_width)
            
            label_x = total_width // 2
            if fill_width >= label_x:
                progress_label.config(bg=self.BG_LIGHT, fg=self.BG_DARK)
            else:
                progress_label.config(bg=self.BG_MID, fg=self.FG_TEXT)
            
            progress_label.config(text=f"{int(percent)}%")
            update_window.update()
        
        def download_update():
            """Download and replace current executable using batch script"""
            try:
                auto_btn.config(state="disabled")
                manual_btn.config(state="disabled")
                close_btn.config(state="disabled")
                
                status_label.config(text="Downloading update...")
                update_progress(0)
                
                response = requests.get(
                    "https://api.github.com/repos/evanovar/RobloxAccountManager/releases/latest",
                    timeout=10
                )
                
                if response.status_code != 200:
                    raise Exception("Failed to fetch release information")
                
                release_data = response.json()
                assets = release_data.get("assets", [])
                
                exe_asset = None
                for asset in assets:
                    if asset["name"].endswith(".exe"):
                        exe_asset = asset
                        break
                
                if not exe_asset:
                    raise Exception("No .exe file found in release")
                
                download_url = exe_asset["browser_download_url"]
                file_name = exe_asset["name"]
                
                current_exe = sys.executable
                if current_exe.lower().endswith("python.exe") or current_exe.lower().endswith("pythonw.exe"):
                    current_exe = os.path.abspath(sys.argv[0])
                
                temp_dir = tempfile.gettempdir()
                temp_file = os.path.join(temp_dir, file_name)
                
                status_label.config(text=f"Downloading {file_name}...")
                
                response = requests.get(download_url, stream=True, timeout=30)
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(temp_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                update_progress(progress)
                
                update_progress(100)
                status_label.config(text="Preparing update...")
                update_window.update()
                
                batch_file = os.path.join(temp_dir, "ram_update.bat")
                batch_content = f'''@echo off
setlocal enabledelayedexpansion

if not exist "{temp_file}" (
    exit /b 1
)

for /F %%A in ('dir /b "{temp_file}"') do set size=%%~zA
if !size! LSS 1000000 (
    exit /b 1
)

:wait_loop
copy /Y "{temp_file}" "{current_exe}" >nul 2>&1
if errorlevel 1 (
    timeout /t 0 /nobreak >nul
    goto wait_loop
)

if exist "{temp_file}" del /f /q "{temp_file}"

del /f /q "%~f0"
'''
                with open(batch_file, 'w') as f:
                    f.write(batch_content)
                
                status_label.config(text="Update complete! Please relaunch.")
                update_window.update()
                
                messagebox.showinfo(
                    "Update Complete",
                    "Update has been installed successfully!\n\nPlease close this window and wait a second before launching the application again.",
                    parent=update_window
                )
                
                subprocess.Popen([batch_file], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.root.quit()
                
            except Exception as e:
                status_label.config(text="Download failed. Try manual update.")
                update_progress(0)
                messagebox.showerror(
                    "Update Failed",
                    f"Failed to update:\n{str(e)}\n\nPlease use Manual Update instead.",
                    parent=update_window
                )
                auto_btn.config(state="normal")
                manual_btn.config(state="normal")
                close_btn.config(state="normal")
        
        def manual_update():
            """Open GitHub releases page"""
            webbrowser.open("https://github.com/evanovar/RobloxAccountManager/releases/latest")
            update_window.destroy()
        
        auto_btn = ttk.Button(
            btn_frame,
            text="Auto Update",
            style="Dark.TButton",
            command=download_update
        )
        auto_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        manual_btn = ttk.Button(
            btn_frame,
            text="Manual Update",
            style="Dark.TButton",
            command=manual_update
        )
        manual_btn.pack(side="left", fill="x", expand=True, padx=(2.5, 2.5))
        
        close_btn = ttk.Button(
            btn_frame,
            text="Close",
            style="Dark.TButton",
            command=update_window.destroy
        )
        close_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

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
        
        small_server_btn = tk.Button(
            self.join_place_dropdown,
            text="Small Server",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_join_place_dropdown(), self.join_small_server()]
        )
        small_server_btn.pack(fill="x", padx=2, pady=1)
        
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

    def save_settings(self, force_immediate=False):
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
                print(f"[ERROR] Failed to save settings: {e}")
            self._save_settings_timer = None
        
        if force_immediate:
            do_save()
        else:
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

    def get_browser_path(self):
        """Get path to the selected browser (Chrome or Chromium)."""
        browser_type = self.settings.get("browser_type", "chrome")
        
        if browser_type == "chromium":
            chromium_path = os.path.join(self.data_folder, "Chromium", "chrome-win64", "chrome.exe")
            if os.path.exists(chromium_path):
                return chromium_path, "Chromium"
            browser_type = "chrome"
        
        if browser_type == "chrome":
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
                    return path, "Google Chrome"
        
        return None, None

    def update_game_name_on_startup(self):
        """Check both Place ID and Private Server fields to update game name on startup"""
        place_id = self.place_entry.get().strip()
        private_server = self.private_server_entry.get().strip()

        if place_id:
            self.update_game_name()
        elif private_server:
            vip_match = re.search(r'roblox\.com/games/(\d+)', private_server)
            if vip_match:
                self.update_game_name_from_id(vip_match.group(1))
            else:
                share_match = re.search(r'roblox\.com/share\?[^#]*code=([A-Za-z0-9]+)', private_server)
                if share_match:
                    def _resolve_startup(ps=private_server):
                        ck = next((d.get('cookie') for d in self.manager.accounts.values() if isinstance(d, dict) and d.get('cookie')), None)
                        resolved_pid, _ = RobloxAPI.resolve_share_url(ps, cookie=ck)
                        if resolved_pid:
                            self.root.after(0, lambda: self.update_game_name_from_id(resolved_pid))
                    threading.Thread(target=_resolve_startup, daemon=True).start()

    def on_place_id_change(self, event=None):
        place_id = self.place_entry.get().strip()
        self.settings["last_place_id"] = place_id
        self.save_settings()
        self.update_game_name()

    def on_private_server_change(self, event=None):        
        private_server = self.private_server_entry.get().strip()
        place_id_input = self.place_entry.get().strip()

        self.settings["last_private_server"] = private_server
        self.save_settings()

        if not place_id_input and private_server:
            vip_match = re.search(r'roblox\.com/games/(\d+)', private_server)
            if vip_match:
                self.update_game_name_from_id(vip_match.group(1))
            else:
                share_match = re.search(r'roblox\.com/share\?[^#]*code=([A-Za-z0-9]+)', private_server)
                if share_match:
                    def _resolve_and_update(ps=private_server):
                        ck = next((d.get('cookie') for d in self.manager.accounts.values() if isinstance(d, dict) and d.get('cookie')), None)
                        resolved_pid, _ = RobloxAPI.resolve_share_url(ps, cookie=ck)
                        if resolved_pid:
                            self.root.after(0, lambda: self.update_game_name_from_id(resolved_pid))
                    threading.Thread(target=_resolve_and_update, daemon=True).start()
    
    def update_game_name_from_id(self, place_id):
        """Update game name label from a specific place ID (without reading from text box)"""
        if self._game_name_after_id is not None:
            try:
                self.root.after_cancel(self._game_name_after_id)
            except Exception:
                pass
            self._game_name_after_id = None

        def schedule_fetch():
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
            cookie_valid = self.cookie_status.get(username)
            
            if cookie_valid is False:
                display_text = f"⚠ {username}"
            else:
                display_text = f"{username}"
            
            if note:
                display_text += f" • {note}"
            index = self.account_list.size()
            self.account_list.insert(tk.END, display_text)
            
            if cookie_valid is False:
                self.account_list.itemconfig(index, fg="#FFB347")

        last_joined = self.settings.get("last_joined_user", "")
        if last_joined:
            accounts_keys = list(self.manager.accounts.keys())
            if last_joined in accounts_keys:
                idx = accounts_keys.index(last_joined)
                self.account_list.selection_clear(0, tk.END)
                self.account_list.selection_set(idx)
                self.account_list.see(idx)

    def on_account_list_hover(self, event):
        """Show tooltip when hovering over an expired account row"""
        index = self.account_list.nearest(event.y)
        
        if index < 0 or index >= self.account_list.size():
            self.hide_account_tooltip()
            return
        
        if index == self.account_tooltip_last_index:
            return
        
        self.hide_account_tooltip()
        self.account_tooltip_last_index = index
        
        display_text = self.account_list.get(index)
        if not display_text.startswith('\u26a0 '):
            return
        
        username = self.extract_username_from_display(display_text)
        
        def create_tooltip():
            if self.account_tooltip:
                return
            
            x_pos = event.x_root + 15
            y_pos = event.y_root + 15
            
            self.account_tooltip = tk.Toplevel(self.root)
            self.account_tooltip.wm_overrideredirect(True)
            self.account_tooltip.wm_geometry(f"+{x_pos}+{y_pos}")
            
            label = tk.Label(
                self.account_tooltip,
                text=f"Cookie expired for '{username}'.\nPlease remove this account and add it again.",
                bg=self.BG_DARK,
                fg=self.FG_TEXT,
                font=(self.FONT_FAMILY, 9),
                padx=8,
                pady=4,
                relief="solid",
                borderwidth=1
            )
            label.pack()
            
            if self.settings.get("enable_topmost", False):
                self.account_tooltip.attributes("-topmost", True)
        
        self.account_tooltip_timer = self.root.after(500, create_tooltip)
    
    def on_account_list_leave(self, event):
        """Hide tooltip when leaving the account list"""
        self.hide_account_tooltip()
    
    def hide_account_tooltip(self):
        """Hide the account list tooltip"""
        if self.account_tooltip_timer:
            self.root.after_cancel(self.account_tooltip_timer)
            self.account_tooltip_timer = None
        
        if self.account_tooltip:
            self.account_tooltip.destroy()
            self.account_tooltip = None
        
        self.account_tooltip_last_index = None
    
    def extract_username_from_display(self, display_text):
        """Extract username from display text (handles indicators like ⚠)"""
        username_part = display_text.split(' • ')[0]
        
        username_part = username_part.strip()
        if username_part.startswith('⚠ '):
            username_part = username_part[2:]
        
        return username_part.strip()
    
    def _send_webhook(self, url, content):
        def _post():
            try:
                requests.post(url, json={"content": content}, timeout=5)
            except Exception as e:
                print(f"[ERROR] Failed to send webhook: {e}")
        threading.Thread(target=_post, daemon=True).start()

    def _send_webhook_embed(self, url, title, description, color, ping_user_id=None):
        def _post():
            try:
                payload = {
                    "content": f"<@{ping_user_id}>" if ping_user_id else "",
                    "embeds": [{
                        "title": title,
                        "description": description,
                        "color": color,
                        "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                    }],
                    "attachments": []
                }
                requests.post(url, json=payload, timeout=5)
            except Exception as e:
                print(f"[ERROR] Failed to send webhook embed: {e}")
        threading.Thread(target=_post, daemon=True).start()

    def _send_webhook_screenshot(self, url, caption=""):
        def _post():
            tmp_path = None
            try:
                tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                tmp_path = tmp.name
                tmp.close()

                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
                    "$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                    "$b=New-Object System.Drawing.Bitmap($s.Width,$s.Height); "
                    "$g=[System.Drawing.Graphics]::FromImage($b); "
                    "$g.CopyFromScreen($s.Location,[System.Drawing.Point]::Empty,$s.Size); "
                    f"$b.Save('{tmp_path}',[System.Drawing.Imaging.ImageFormat]::Png); "
                    "$g.Dispose();$b.Dispose()"
                )
                subprocess.run(
                    ["powershell", "-NonInteractive", "-Command", ps],
                    capture_output=True, timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                with open(tmp_path, 'rb') as f:
                    requests.post(url, data={"content": caption},
                                  files={"file": ("screenshot.png", f, "image/png")}, timeout=10)
            except Exception as e:
                print(f"[ERROR] Webhook screenshot send failed: {e}")
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
        threading.Thread(target=_post, daemon=True).start()

    def _get_roblox_hwnds_from_pids(self, pids):
        hwnds = []
        def _cb(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                    if wpid in pids:
                        title = win32gui.GetWindowText(hwnd)
                        if title and "roblox" in title.lower():
                            hwnds.append(hwnd)
            except Exception:
                pass
            return True
        win32gui.EnumWindows(_cb, None)
        return hwnds

    def _tile_roblox_windows(self):
        pids = self._get_roblox_pids()
        if not pids:
            return
        hwnds = self._get_roblox_hwnds_from_pids(pids)
        n = len(hwnds)
        if n == 0:
            return
        try:
            screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            screen_h = ctypes.windll.user32.GetSystemMetrics(1)
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
            win_w = screen_w // cols
            win_h = screen_h // rows
            for i, hwnd in enumerate(hwnds):
                col = i % cols
                row = i // cols
                x = col * win_w
                y = row * win_h
                try:
                    win32gui.ShowWindow(hwnd, 9)
                    win32gui.MoveWindow(hwnd, x, y, win_w, win_h, True)
                except Exception as e:
                    print(f"[ERROR] Could not move window {hwnd}: {e}")
            print(f"[INFO] Tiled {n} Roblox window(s) in a {cols}×{rows} grid.")
        except Exception as e:
            print(f"[ERROR] Error tiling windows: {e}")

    def _tile_roblox_windows_after_launch(self):
        prev_count = len(self._get_roblox_pids())
        deadline = time.time() + 45
        while time.time() < deadline:
            time.sleep(3)
            curr_count = len(self._get_roblox_pids())
            if curr_count > prev_count:
                time.sleep(6)
                break
        self._tile_roblox_windows()

    def _save_cookie_status(self, username, is_valid):
        """Update cookie status in memory and persist to accounts file"""
        self.cookie_status[username] = is_valid
        if username in self.manager.accounts and isinstance(self.manager.accounts[username], dict):
            self.manager.accounts[username]['cookie_valid'] = is_valid

    def _watch_discord_logo(self):
        """Background thread: wait for discordlogo.png to appear, then apply it to the UI."""
        if self.discord_btn is not None:
            return
        path = self.discord_logo_path
        if not path:
            return
        for _ in range(60):
            if os.path.exists(path):
                self.root.after(0, self._apply_discord_logo_to_ui)
                return
            time.sleep(0.5)

    def _apply_discord_logo_to_ui(self):
        """Load (or reload) the discord logo and create/update the button."""
        path = self.discord_logo_path
        if not path or not os.path.exists(path):
            return
        try:
            img = tk.PhotoImage(file=path)
            w, h = img.width(), img.height()
            factor = max(1, max(w, h) // 20)
            if factor > 1:
                img = img.subsample(factor, factor)
            self.discord_logo_img = img
        except Exception:
            return
        if self.discord_btn is not None:
            self.discord_btn.config(image=img, bg=self.BG_DARK, activebackground=self.BG_DARK)
        else:
            self.discord_btn = tk.Button(
                self.quick_actions_row,
                image=img,
                bg=self.BG_DARK,
                activebackground=self.BG_DARK,
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=0,
                pady=0,
                highlightthickness=0,
                command=lambda: webbrowser.open("https://discord.gg/SZaZU8zwZA")
            )
            self.discord_btn.pack(side="right")

    def _silent_check_cookies(self):
        """Trigger a background silent cookie check. Safe to call from any thread."""
        if getattr(self, '_cookie_check_running', False):
            return
        threading.Thread(target=self._silent_check_cookies_worker, daemon=True).start()

    def _silent_check_cookies_worker(self):
        """Check all accounts not already known invalid."""
        if getattr(self, '_cookie_check_running', False):
            return
        self._cookie_check_running = True
        try:
            accounts = [u for u in self.manager.accounts
                        if self.cookie_status.get(u) is not False]
            if not accounts:
                return
            changed = False
            for username in accounts:
                try:
                    is_valid = self.manager.validate_account(username)
                    self._save_cookie_status(username, is_valid)
                    changed = True
                except Exception as e:
                    print(f"[ERROR] Cookie check failed for {username}: {e}")
            if changed:
                self.manager.save_accounts()
                self.root.after(0, self.refresh_accounts)
        finally:
            self._cookie_check_running = False
    
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
        username = self.extract_username_from_display(display_text)
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
            username = self.extract_username_from_display(display_text)
            usernames.append(username)
        return usernames

    def add_account(self):
        """
        Add a new account using browser automation
        """
        browser_path, browser_name = self.get_browser_path()
        
        if not browser_path:
            messagebox.showwarning(
                "Browser Required",
                "Add Account requires a browser.\n\n"
                "Please either:\n"
                "• Install Google Chrome, or\n"
                "• Download Chromium in Settings → Tools → Browser Engine"
            )
            return

        messagebox.showinfo("Add Account", f"Browser ({browser_name}) will open for account login.\nPlease log in and wait for the process to complete.")
        
        def add_account_thread():
            """
            Thread function to add account without blocking UI
            """
            try:
                success = self.manager.add_account(1, "https://www.roblox.com/login", "", browser_path)
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
        self.apply_window_icon(import_window)
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
        
        ttk.Label(main_frame, text="Cookie(s)", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
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
            cookie_input = cookie_text.get("1.0", "end-1c").strip()
            
            if not cookie_input:
                messagebox.showwarning("Missing Information", "Please enter the cookie(s).")
                return
            
            cookies = []
            if "_|WARNING:-" in cookie_input:
                parts = cookie_input.split("_|WARNING:-")
                for part in parts:
                    if part.strip():
                        cookies.append("_|WARNING:-" + part.strip())
            else:
                cookies = [cookie_input]
            
            imported_count = 0
            failed_count = 0
            imported_accounts = []
            
            for cookie in cookies:
                try:
                    success, username = self.manager.import_cookie_account(cookie)
                    if success:
                        imported_count += 1
                        imported_accounts.append(username)
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    print(f"[ERROR] Failed to import cookie: {e}")
            
            self.refresh_accounts()
            
            if imported_count > 0:
                if imported_count == 1:
                    messagebox.showinfo("Success", f"Account '{imported_accounts[0]}' imported successfully!")
                else:
                    messagebox.showinfo("Success", f"Successfully imported {imported_count} account(s)!\n\n{', '.join(imported_accounts)}")
                import_window.destroy()
            
            if failed_count > 0:
                if imported_count == 0:
                    messagebox.showerror("Error", f"Failed to import {failed_count} cookie(s). Please check the cookies.")
                else:
                    messagebox.showwarning("Partial Success", f"Imported {imported_count} account(s), but {failed_count} failed.")
        
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
        self.apply_window_icon(amount_window)
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
        self.apply_window_icon(website_window)
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
        self.apply_window_icon(js_window)
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
        browser_path, browser_name = self.get_browser_path()
        
        if not browser_path:
            messagebox.showwarning(
                "Browser Required",
                "Javascript Import requires a browser.\n\n"
                "Please either:\n"
                "• Install Google Chrome, or\n"
                "• Download Chromium in Settings → Tools → Browser Engine"
            )
            return

        def launch_thread():
            try:
                success = self.manager.add_account(amount, website, javascript, browser_path)
                
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
        self.apply_window_icon(note_window)
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

    def show_account_context_menu(self, event):
        """Show context menu on right-click"""
        index = self.account_list.nearest(event.y)
        if index < 0:
            return
        
        self.account_list.selection_clear(0, tk.END)
        self.account_list.selection_set(index)
        self.account_list.activate(index)
        
        display_text = self.account_list.get(index)
        username = self.extract_username_from_display(display_text)
        account = self.manager.accounts.get(username)
        
        if not account:
            return
        
        if not isinstance(account, dict):
            return
        
        user_id = account.get('user_id', 0)
        password = account.get('password', '')
        
        if hasattr(self, 'account_context_menu') and self.account_context_menu is not None:
            try:
                self.account_context_menu.destroy()
            except:
                pass
        
        self.account_context_menu = tk.Toplevel(self.root)
        self.account_context_menu.overrideredirect(True)
        self.account_context_menu.configure(bg=self.BG_MID, highlightthickness=1, highlightbackground="white")
        
        def copy_to_clipboard(text):
            self.root.clipboard_clear()
            self.root.clipboard_append(str(text))
            self.root.update()
            self.hide_account_context_menu()
        
        def hide_menu():
            self.hide_account_context_menu()
        
        username_btn = tk.Button(
            self.account_context_menu,
            text=f"Copy Username",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: copy_to_clipboard(username)
        )
        username_btn.pack(fill="x", padx=2, pady=1)
        
        if user_id:
            userid_btn = tk.Button(
                self.account_context_menu,
                text=f"Copy User ID",
                anchor="w",
                relief="flat",
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                activebackground=self.BG_LIGHT,
                activeforeground=self.FG_TEXT,
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=0,
                command=lambda: copy_to_clipboard(user_id)
            )
        else:
            userid_btn = tk.Button(
                self.account_context_menu,
                text=f"Copy User ID",
                anchor="w",
                relief="flat",
                bg=self.BG_MID,
                fg="#666666",
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=0,
                state="disabled"
            )
        userid_btn.pack(fill="x", padx=2, pady=1)
        
        if password:
            password_btn = tk.Button(
                self.account_context_menu,
                text=f"Copy Password",
                anchor="w",
                relief="flat",
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                activebackground=self.BG_LIGHT,
                activeforeground=self.FG_TEXT,
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=0,
                command=lambda: copy_to_clipboard(password)
            )
        else:
            password_btn = tk.Button(
                self.account_context_menu,
                text=f"Copy Password",
                anchor="w",
                relief="flat",
                bg=self.BG_MID,
                fg="#666666",
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=0,
                state="disabled"
            )
        password_btn.pack(fill="x", padx=2, pady=1)
        
        separator = tk.Frame(self.account_context_menu, height=1, bg="#666666")
        separator.pack(fill="x", padx=2, pady=2)
        
        def check_single_cookie():
            self.hide_account_context_menu()
            print(f"[INFO] Checking cookie for {username}...")
            
            def check_thread():
                try:
                    is_valid = self.manager.validate_account(username)
                    self._save_cookie_status(username, is_valid)
                    self.manager.save_accounts()
                    self.root.after(0, lambda: self.refresh_accounts())
                    
                    if is_valid:
                        self.root.after(0, lambda: messagebox.showinfo(
                            "Cookie Valid",
                            f"Cookie for '{username}' is valid!"
                        ))
                    else:
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Cookie Expired",
                            f"⚠ Cookie for '{username}' is expired or invalid!"
                        ))
                except Exception as e:
                    print(f"[ERROR] Failed to check cookie: {e}")
                    self._save_cookie_status(username, None)
                    self.manager.save_accounts()
                    self.root.after(0, lambda: messagebox.showerror(
                        "Check Failed",
                        f"Failed to check cookie for '{username}':\\n{str(e)}"
                    ))
            
            thread = threading.Thread(target=check_thread, daemon=True)
            thread.start()
        
        check_cookie_btn = tk.Button(
            self.account_context_menu,
            text="Check Cookie",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=check_single_cookie
        )
        check_cookie_btn.pack(fill="x", padx=2, pady=1)
        
        self.account_context_menu.geometry(f"+{event.x_root}+{event.y_root}")
        self.account_context_menu.update_idletasks()
        
        if self.settings.get("enable_topmost", False):
            self.account_context_menu.attributes("-topmost", True)
        
        self.account_context_menu.bind("<FocusOut>", lambda e: self.hide_account_context_menu())
        self.root.bind("<Button-1>", lambda e: self.hide_account_context_menu(), add="+")
    
    def hide_account_context_menu(self):
        """Hide the account context menu"""
        if hasattr(self, 'account_context_menu') and self.account_context_menu is not None:
            try:
                self.account_context_menu.destroy()
            except:
                pass
            self.account_context_menu = None


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
            failed_launch = False
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, "", "", launcher_pref):
                        success_count += 1
                    else:
                        failed_launch = True
                except Exception as e:
                    print(f"[ERROR] Failed to launch Roblox home for {uname}: {e}")
            if failed_launch:
                self._silent_check_cookies()
            
            if success_count > 1 and self.settings.get("auto_tile_windows", True):
                threading.Thread(target=self._tile_roblox_windows_after_launch, daemon=True).start()

            def on_done():
                if success_count > 0:
                    self.settings["last_joined_user"] = selected_usernames[-1]
                    self.save_settings()
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
        """Launch Roblox game with the selected account(s)"""
        
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]

        game_id_input = self.place_entry.get().strip()
        private_server_input = self.private_server_entry.get().strip()

        if game_id_input:
            if not game_id_input.isdigit():
                messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
                return
            game_id = game_id_input
        elif private_server_input:
            vip_pid = re.search(r'roblox\.com/games/(\d+)', private_server_input)
            game_id = vip_pid.group(1) if vip_pid else ""
        else:
            messagebox.showwarning("Missing Info", "Please enter a Place ID or paste a VIP server / share link in the Private Server field.")
            return

        private_server = private_server_input 

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
            failed_launch = False
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, pid, psid, launcher_pref):
                        success_count += 1
                    else:
                        failed_launch = True
                except Exception as e:
                    print(f"[ERROR] Failed to launch game for {uname}: {e}")
            if failed_launch:
                self._silent_check_cookies()

            if success_count > 1 and self.settings.get("auto_tile_windows", True):
                threading.Thread(target=self._tile_roblox_windows_after_launch, daemon=True).start()

            def on_done():
                if success_count > 0:
                    self.settings["last_joined_user"] = selected_usernames[-1]
                    self.save_settings()
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
        self.apply_window_icon(auto_rejoin_window)
        auto_rejoin_window.title("Auto-Rejoin")
        auto_rejoin_window.configure(bg=self.BG_DARK)
        auto_rejoin_window.resizable(False, False)
        
        self.root.update_idletasks()
        
        saved_pos = self.settings.get('auto_rejoin_window_position')
        if saved_pos and saved_pos.get('x') is not None and saved_pos.get('y') is not None:
            x = saved_pos['x']
            y = saved_pos['y']
        else:
            x = self.root.winfo_x() + 50
            y = self.root.winfo_y() + 50
        auto_rejoin_window.geometry(f"450x400+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            auto_rejoin_window.attributes("-topmost", True)
        
        auto_rejoin_window.transient(self.root)
        auto_rejoin_window.focus_force()
        
        main_frame = ttk.Frame(auto_rejoin_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        header_row = ttk.Frame(main_frame, style="Dark.TFrame")
        header_row.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header_row,
            text="Auto-Rejoin Accounts",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(side="left")

        def open_rejoin_webhook_settings():
            """Open the webhook settings window for auto-rejoin notifications."""
            wh_win = tk.Toplevel(auto_rejoin_window)
            self.apply_window_icon(wh_win)
            wh_win.title("Webhook Settings")
            wh_win.configure(bg=self.BG_DARK)
            wh_win.resizable(False, False)
            auto_rejoin_window.update_idletasks()
            wx = auto_rejoin_window.winfo_x() + 50
            wy = auto_rejoin_window.winfo_y() + 50
            wh_win.geometry(f"420x200+{wx}+{wy}")
            if self.settings.get("enable_topmost", False):
                wh_win.attributes("-topmost", True)
            wh_win.transient(auto_rejoin_window)
            wh_win.focus_force()

            cfg = self.settings.get('rejoin_webhook', {})

            frm = ttk.Frame(wh_win, style="Dark.TFrame")
            frm.pack(fill="both", expand=True, padx=20, pady=20)

            ttk.Label(frm, text="Webhook Settings", style="Dark.TLabel",
                      font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 10))

            ttk.Label(frm, text="Discord Webhook URL:", style="Dark.TLabel").pack(anchor="w")
            url_var = tk.StringVar(value=cfg.get('url', ''))
            url_entry = ttk.Entry(frm, textvariable=url_var, style="Dark.TEntry")
            url_entry.pack(fill="x", pady=(0, 10))

            ping_var = tk.BooleanVar(value=cfg.get('enable_ping', False))
            ping_row = ttk.Frame(frm, style="Dark.TFrame")
            ping_row.pack(fill="x", pady=(2, 0))
            ping_id_var = tk.StringVar(value=cfg.get('ping_user_id', ''))
            ping_id_entry = ttk.Entry(ping_row, textvariable=ping_id_var, width=20, style="Dark.TEntry")

            def _on_ping_toggle():
                ping_id_entry.config(state="normal" if ping_var.get() else "disabled")

            ttk.Checkbutton(
                ping_row,
                text="Ping user ID on alerts:",
                variable=ping_var,
                command=_on_ping_toggle,
                style="Dark.TCheckbutton"
            ).pack(side="left")
            ping_id_entry.pack(side="left", padx=(8, 0))
            ping_id_entry.config(state="normal" if ping_var.get() else "disabled")

            def save_webhook_settings():
                self.settings['rejoin_webhook'] = {
                    'url': url_var.get().strip(),
                    'enable_ping': ping_var.get(),
                    'ping_user_id': ping_id_var.get().strip()
                }
                self.save_settings()
                wh_win.destroy()

            def test_webhook():
                url = url_var.get().strip()
                if not url:
                    messagebox.showwarning("Missing URL", "Enter a webhook URL first.", parent=wh_win)
                    return
                _ping = ping_id_var.get().strip() if ping_var.get() and ping_id_var.get().strip() else None
                self._send_webhook_embed(
                    url,
                    "Webhook Test",
                    "Auto-Rejoin webhook is working correctly!",
                    5438822,
                    ping_user_id=_ping
                )

            btn_row = ttk.Frame(frm, style="Dark.TFrame")
            btn_row.pack(fill="x", pady=(16, 0))
            ttk.Button(btn_row, text="Test", style="Dark.TButton", command=test_webhook).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ttk.Button(btn_row, text="Save", style="Dark.TButton", command=save_webhook_settings).pack(side="left", fill="x", expand=True, padx=4)
            ttk.Button(btn_row, text="Cancel", style="Dark.TButton", command=wh_win.destroy).pack(side="left", fill="x", expand=True, padx=(4, 0))

        _discord_img_ref = getattr(self, 'discord_logo_img', None)
        if _discord_img_ref:
            wh_btn = tk.Button(
                header_row, image=_discord_img_ref,
                bg=self.BG_DARK, activebackground=self.BG_DARK,
                relief="flat", bd=0, cursor="hand2",
                padx=0, pady=0, highlightthickness=0,
                command=open_rejoin_webhook_settings
            )
            wh_btn.pack(side="right")
        else:
            ttk.Button(header_row, text="Webhook", style="Dark.TButton",
                       command=open_rejoin_webhook_settings).pack(side="right")
        
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
            self.apply_window_icon(add_window)
            add_window.title("Add Auto-Rejoin")
            add_window.configure(bg=self.BG_DARK)
            add_window.resizable(False, False)
            
            auto_rejoin_window.update_idletasks()
            x = auto_rejoin_window.winfo_x() + 50
            y = auto_rejoin_window.winfo_y() + 50
            add_window.geometry(f"400x470+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                add_window.attributes("-topmost", True)
            
            add_window.transient(auto_rejoin_window)
            add_window.focus_force()
            
            form_frame = ttk.Frame(add_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            checkbox_style = ttk.Style()
            checkbox_style.configure(
                "Dark.TCheckbutton",
                background=self.BG_DARK,
                foreground=self.FG_TEXT,
                font=("Segoe UI", 10)
            )
            
            ttk.Label(form_frame, text="Account(s) - Hold Ctrl to select multiple:", style="Dark.TLabel").pack(anchor="w")
            
            account_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            account_frame.pack(fill="both", expand=True, pady=(0, 10))
            
            account_listbox = tk.Listbox(
                account_frame,
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                selectbackground=self.FG_ACCENT,
                highlightthickness=0,
                border=1,
                font=("Segoe UI", 9),
                selectmode=tk.EXTENDED,
                height=6
            )
            account_listbox.pack(side="left", fill="both", expand=True)
            
            account_scrollbar = ttk.Scrollbar(account_frame, command=account_listbox.yview)
            account_scrollbar.pack(side="right", fill="y")
            account_listbox.config(yscrollcommand=account_scrollbar.set)
            
            for account in sorted(self.manager.accounts.keys()):
                account_listbox.insert(tk.END, account)
            
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
            
            check_presence_var = tk.BooleanVar(value=True)
            check_presence_check = ttk.Checkbutton(form_frame, text="Check if player is in target PlaceID", style="Dark.TCheckbutton", variable=check_presence_var)
            check_presence_check.pack(anchor="w", pady=(0, 10))
            
            def save_and_add():
                selected_indices = account_listbox.curselection()
                if not selected_indices:
                    messagebox.showwarning("Missing Info", "Please select at least one account.")
                    return
                
                selected_accounts = [account_listbox.get(i) for i in selected_indices]
                
                place_id = place_entry.get().strip()
                if not place_id:
                    messagebox.showwarning("Missing Info", "Please enter a Place ID.")
                    return
                if not place_id.isdigit():
                    messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
                    return
                
                job_id = job_entry.get().strip()
                
                config = {
                    'place_id': place_id,
                    'private_server': private_entry.get().strip(),
                    'job_id': job_id,
                    'check_interval': int(interval_spinbox.get()),
                    'max_retries': int(retry_spinbox.get()),
                    'check_presence': check_presence_var.get()
                }
                
                for account in selected_accounts:
                    self.auto_rejoin_configs[account] = config.copy()
                
                self.settings['auto_rejoin_configs'] = self.auto_rejoin_configs
                self.save_settings()
                
                add_window.destroy()
                refresh_rejoin_list()
                
                if len(selected_accounts) == 1:
                    messagebox.showinfo("Success", f"Added auto-rejoin for {selected_accounts[0]}!")
                else:
                    messagebox.showinfo("Success", f"Added auto-rejoin for {len(selected_accounts)} accounts:\n{', '.join(selected_accounts)}")
                
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
            self.apply_window_icon(edit_window)
            edit_window.title("Edit Auto-Rejoin")
            edit_window.configure(bg=self.BG_DARK)
            edit_window.resizable(False, False)
            
            auto_rejoin_window.update_idletasks()
            x = auto_rejoin_window.winfo_x() + 50
            y = auto_rejoin_window.winfo_y() + 50
            edit_window.geometry(f"400x400+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                edit_window.attributes("-topmost", True)
            
            edit_window.transient(auto_rejoin_window)
            edit_window.focus_force()
            
            form_frame = ttk.Frame(edit_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            checkbox_style = ttk.Style()
            checkbox_style.configure(
                "Dark.TCheckbutton",
                background=self.BG_DARK,
                foreground=self.FG_TEXT,
                font=("Segoe UI", 10)
            )
            
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
            
            check_presence_var = tk.BooleanVar(value=config.get('check_presence', True))
            check_presence_check = ttk.Checkbutton(form_frame, text="Check if player is in target PlaceID", style="Dark.TCheckbutton", variable=check_presence_var)
            check_presence_check.pack(anchor="w", pady=(0, 10))
            
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
                    'max_retries': int(retry_spinbox.get()),
                    'check_presence': check_presence_var.get()
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
            
            self._match_pids_to_accounts([account])

            wh_cfg = self.settings.get('rejoin_webhook', {})
            wh_url = wh_cfg.get('url', '').strip()
            if wh_url:
                _ping = wh_cfg.get('ping_user_id', '') if wh_cfg.get('enable_ping') else None
                self._send_webhook_embed(
                    wh_url,
                    "Auto Rejoin Started",
                    f"Monitoring 1 account:\n- **{account}** on place `{self.auto_rejoin_configs[account].get('place_id', '?')}`",
                    5438822,
                    ping_user_id=_ping or None
                )

            self.start_auto_rejoin_for_account(account)

            auto_rejoin_window.after(500, refresh_rejoin_list)
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
            accounts = list(self.auto_rejoin_configs.keys())

            self._match_pids_to_accounts(accounts)

            wh_cfg = self.settings.get('rejoin_webhook', {})
            wh_url = wh_cfg.get('url', '').strip()
            if wh_url and accounts:
                lines = "\n".join(
                    f"- **{acc}** on place `{self.auto_rejoin_configs[acc].get('place_id', '?')}`"
                    for acc in accounts
                )
                _ping = wh_cfg.get('ping_user_id', '') if wh_cfg.get('enable_ping') else None
                self._send_webhook_embed(
                    wh_url,
                    "Auto Rejoin Started",
                    f"Monitoring {len(accounts)} account(s):\n{lines}",
                    5438822,
                    ping_user_id=_ping or None
                )

            for account in accounts:
                self.start_auto_rejoin_for_account(account)

            auto_rejoin_window.after(500, refresh_rejoin_list)
            messagebox.showinfo("Started", f"Auto-rejoin started for all {len(accounts)} account(s)!")
        
        def stop_all():
            """Stop auto-rejoin for all accounts"""
            for account in list(self.auto_rejoin_threads.keys()):
                self.stop_auto_rejoin_for_account(account)
            refresh_rejoin_list()
            messagebox.showinfo("Stopped", "Auto-rejoin stopped for all accounts!")
        
        def on_auto_rejoin_close():
            """Save window position before closing"""
            self.settings['auto_rejoin_window_position'] = {
                'x': auto_rejoin_window.winfo_x(),
                'y': auto_rejoin_window.winfo_y()
            }
            self.save_settings()
            auto_rejoin_window.destroy()
        
        auto_rejoin_window.protocol("WM_DELETE_WINDOW", on_auto_rejoin_close)
        
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
        self.apply_window_icon(join_window)
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
                        print(f"[ERROR] Failed to launch game for {uname}: {e}")
                
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
        self.apply_window_icon(job_id_window)
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
                        print(f"[ERROR] Failed to launch game for {uname}: {e}")
                
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

    def join_small_server(self):
        """Join the smallest available server for a given place ID"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]
        
        place_id = self.place_entry.get().strip()
        if not place_id:
            messagebox.showwarning("Missing Information", "Please enter a Place ID first.")
            return
        
        try:
            int(place_id)
        except ValueError:
            messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
            return
        
        def worker(selected_usernames, pid):
            print(f"[INFO] Searching for smallest server in place {pid}...")
            game_id = RobloxAPI.get_smallest_server(pid)
            
            if not game_id:
                self.root.after(0, lambda: messagebox.showerror(
                    "Error",
                    f"Could not find any available servers for place {pid}.\n\nPlease try again later or check the Place ID."
                ))
                return
            
            print(f"[SUCCESS] Found smallest server: {game_id}")
            
            launcher_pref = self.settings.get("roblox_launcher", "default")
            success_count = 0
            
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, pid, "", launcher_pref, game_id):
                        success_count += 1
                except Exception as e:
                    print(f"[ERROR] Failed to launch game for {uname}: {e}")
            
            def on_done():
                if success_count > 0:
                    game_name = RobloxAPI.get_game_name(pid)
                    if game_name:
                        self.add_game_to_list(pid, game_name, "")
                    else:
                        self.add_game_to_list(pid, f"Place {pid}", "")
                    
                    if len(selected_usernames) == 1:
                        messagebox.showinfo(
                            "Success",
                            f"Joining smallest server! Check your desktop."
                        )
                    else:
                        messagebox.showinfo(
                            "Success",
                            f"Joining smallest server with {success_count} account(s)! Check your desktop."
                        )
                else:
                    messagebox.showerror("Error", "Failed to launch Roblox.")
            
            self.root.after(0, on_done)
        
        threading.Thread(target=worker, args=(usernames, place_id), daemon=True).start()

    def _close_roblox_handles(self, handle_path):
        """Close ROBLOX_singletonEvent handles for all running Roblox processes using handle64.exe"""
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

    def _handle64_monitor_thread(self):
        target = "robloxplayerbeta.exe"
        known = set()
        
        while self.handle64_monitoring and self.handle64_path:
            try:
                current = set()
                for p in psutil.process_iter(["pid", "name"]):
                    if p.info["name"] and p.info["name"].lower() == target:
                        pid = p.info["pid"]
                        if self._is_valid_roblox_game_client(pid, target):
                            current.add(pid)
                
                new = current - known
                if new:
                    threading.Thread(target=self._handle64_close_handles, args=(list(new),), daemon=True).start()
                    known |= new
                    for pid in new:
                        print(f"[INFO] Roblox process created PID:{pid}")
                
                known -= (known - current)
                
                time.sleep(0.4)
                    
            except Exception as e:
                print(f"[WARNING] Handle64 monitor error: {str(e)}")
                time.sleep(1.0)

    def _handle64_close_handles(self, new_pids):
        """Closes ROBLOX_singletonEvent handles for the given PIDs using handle64.exe"""
        HANDLE = self.handle64_path
        
        for pid in new_pids:
            handle_value = None
            handle_found = False
            try:
                for attempt in range(5):
                    cmd = f'"{HANDLE}" -accepteula -p {pid} -a'
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        stdin=subprocess.DEVNULL, text=True, shell=True)
                    lines = proc.stdout.splitlines()
                    for line in lines:
                        if "ROBLOX_singletonEvent" in line:
                            m = re.search(r"([0-9A-F]+):.*ROBLOX_singletonEvent", line, re.IGNORECASE)
                            if m:
                                handle_value = m.group(1)
                                break
                            else:
                                possible = re.findall(r"\b[0-9A-F]{4,}\b", line)
                                if possible:
                                    handle_value = possible[0]
                                    break
                    if handle_value:
                        handle_found = True
                        break
                    time.sleep(1)
                if not handle_value:
                    print(f"[FAILED] Handle not closed for PID:{pid}")
                if handle_found:
                    subprocess.run(f'"{HANDLE}" -accepteula -p {pid} -c {handle_value} -y',
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, shell=True)
                    print(f"[SUCCESS] Closed handle event for PID:{pid}")
            except Exception:
                print(f"[FAILED] Handle not closed for PID:{pid}")

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
                print(f"[INFO] Found handle64.exe at: {handle_path}")
                return handle_path
            
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            handle_path = os.path.join(base_dir, 'handle64.exe')
            if os.path.exists(handle_path):
                print(f"[INFO] Found handle64.exe at: {handle_path}")
                return handle_path
            
            handle_path = os.path.join(base_dir, 'handle', 'handle64.exe')
            if os.path.exists(handle_path):
                print(f"[INFO] Found handle64.exe at: {handle_path}")
                return handle_path
            
            print(f"[WARNING] handle64.exe not found in: {self.data_folder}, {base_dir}, or {os.path.join(base_dir, 'handle')}")
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
                try:
                    is_admin = ctypes.windll.shell32.IsUserAnAdmin()
                except:
                    is_admin = False
                
                if not is_admin:
                    print("[WARNING] Not running as admin! Prompting user.")
                    want_admin = messagebox.askyesno(
                        "Admin Required",
                        "handle64 mode requires administrator privileges.\n\n"
                        "The app is NOT running as admin.\n\n"
                        "Do you want to relaunch as administrator?\n\n"
                        "Click Yes to restart as admin, or No to fall back to the Default method."
                    )
                    if want_admin:
                        print("[INFO] Relaunching as administrator...")
                        try:
                            params = " ".join(f'"{a}"' for a in sys.argv[1:])
                            ctypes.windll.shell32.ShellExecuteW(
                                None, "runas", sys.executable, params, None, 1
                            )
                        except Exception as e:
                            print(f"[ERROR] Failed to relaunch as admin: {e}")
                            messagebox.showerror("Error", f"Failed to relaunch as administrator:\n{e}")
                        self.root.after(500, self.root.destroy)
                        return False
                    else:
                        print("[INFO] User declined admin, switching to Default method.")
                        self.settings["multi_roblox_method"] = "default"
                        self.save_settings()
                        use_handle64 = False
                
                if use_handle64:
                    handle64_path = self._find_handle64_exe()
                    if handle64_path:
                        print("[INFO] handle64.exe found. Using advanced multi-roblox mode.")
                        self.handle64_path = handle64_path
                        
                        self.handle64_monitoring = True
                        self.handle64_monitor_thread = threading.Thread(
                            target=self._handle64_monitor_thread,
                            daemon=True
                        )
                        self.handle64_monitor_thread.start()
                        print("[INFO] Handle64 monitor started.")
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
            
            mutex = None
            if not use_handle64:
                mutex = win32event.CreateMutex(None, True, "ROBLOX_singletonEvent")
                print("[INFO] Multi Roblox activated (mutex mode).")
                
                if win32api.GetLastError() == 183:
                    print("[INFO] Mutex already exists. Took ownership.")
            else:
                print("[INFO] Multi Roblox activated (handle64 mode).")
            
            cookies_path = os.path.join(
                os.getenv('LOCALAPPDATA'),
                r'Roblox\LocalStorage\RobloxCookies.dat'
            )
            
            cookie_file = None
            if os.path.exists(cookies_path):
                try:
                    cookie_file = open(cookies_path, 'r+b')
                    msvcrt.locking(cookie_file.fileno(), msvcrt.LK_NBLCK, os.path.getsize(cookies_path))
                    print("[SUCCESS] Error 773 fix applied.")
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
            if self.handle64_monitoring:
                self.handle64_monitoring = False
                if self.handle64_monitor_thread:
                    self.handle64_monitor_thread.join(timeout=2.0)
                self.handle64_monitor_thread = None
                self.handle64_path = None
                print("[INFO] Handle64 monitor stopped.")
            
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
                                print("[SUCCESS] Cookie file unlocked.")
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
                        print("[SUCCESS] Multi Roblox mutex released and closed.")
                    except Exception as mutex_error:
                        print(f"[ERROR] Failed to release mutex: {mutex_error}")
                
                self.multi_roblox_handle = None
        except Exception as e:
            print(f"[ERROR] Error disabling Multi Roblox: {e}")
    
    def initialize_multi_roblox(self):
        """Initialize Multi Roblox on startup if enabled in settings"""
        success = self.enable_multi_roblox()
        if not success:
            self.settings["enable_multi_roblox"] = False
            self.save_settings()

    def open_multi_roblox_method_settings(self):
        """Open Multi Roblox method selection window"""
        method_window = tk.Toplevel(self.root)
        self.apply_window_icon(method_window)
        method_window.title("Multi Roblox Method Settings")
        method_window.geometry("400x330")
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
        handle_radio.bind("<Enter>", lambda e: show_tooltip(e, "Uses handle64.exe to close handles.\nAllows multi-roblox with running instances.\nRequires administrator permission!"))
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
            
            was_active = self.multi_roblox_handle is not None
            
            if was_active:
                old_method = self.settings.get("multi_roblox_method", "default")
                if old_method != selected:
                    print(f"[INFO] Switching multi-roblox from {old_method} to {selected}")
                    self.disable_multi_roblox()
            
            self.settings["multi_roblox_method"] = selected
            try:
                with open(self.settings_file, 'w') as f:
                    json.dump(self.settings, f, indent=2)
            except Exception as e:
                print(f"[ERROR] Failed to save settings: {e}")
            
            if was_active:
                success = self.enable_multi_roblox()
                if not success:
                    messagebox.showerror("Error", "Failed to restart Multi Roblox with new method.")
                    method_window.destroy()
                    return
            
            actual_method = self.settings.get("multi_roblox_method", "default")
            messagebox.showinfo("Success", f"Multi Roblox method set to: {actual_method.title()}")
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


    def _run_encryption_switch(self):
        """Run the encryption method switch process"""
        
        current_accounts = self.manager.accounts.copy()
        
        self.manager.encryption_config.reset_encryption()
        self.manager.encryptor = None
        self.manager.accounts = current_accounts
        self.manager.save_accounts()
        
        self.root.destroy()
        
        setup_ui = EncryptionSetupUI()
        result = setup_ui.setup_encryption_ui()
        
        if setup_ui.should_exit:
            sys.exit(0)
        
        
        try:
            new_method = setup_ui.encryption_config.get_encryption_method()
            
            if new_method == 'password':
                if result is None:
                    raise ValueError("Password setup failed - no password returned")
                new_manager = RobloxAccountManager(password=result)
            else:
                new_manager = RobloxAccountManager()
            
            new_manager.save_accounts()
            
            messagebox.showinfo("Success", "Encryption method switched successfully!\nYour accounts have been re-encrypted.")
            
            new_root = tk.Tk()
            app = AccountManagerUI(new_root, new_manager)
            new_root.mainloop()
            
        except Exception as e:
            print(f"[ERROR] Failed to switch encryption: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to switch encryption: {e}")
            sys.exit(1)

    def open_settings(self):
        """Open the Settings window"""
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus()
            return
        
        settings_window = tk.Toplevel(self.root)
        self.apply_window_icon(settings_window)
        self.settings_window = settings_window
        settings_window.title("Settings")
        settings_window.configure(bg=self.BG_DARK)
        settings_window.resizable(False, False)
        
        settings_window.transient(self.root)
        
        def on_close():
            self.settings_window = None
            settings_window.destroy()
        
        def on_settings_close():
            """Save window position before closing"""
            self.settings['settings_window_position'] = {
                'x': settings_window.winfo_x(),
                'y': settings_window.winfo_y()
            }
            self.save_settings()
            self.settings_window = None
            settings_window.destroy()
        
        settings_window.protocol("WM_DELETE_WINDOW", on_settings_close)
        
        if self.settings.get("enable_topmost", False):
            settings_window.attributes("-topmost", True)
        
        self.root.update_idletasks()
        
        settings_width = 300
        settings_height = 385
        
        saved_pos = self.settings.get('settings_window_position')
        if saved_pos and saved_pos.get('x') is not None and saved_pos.get('y') is not None:
            x = saved_pos['x']
            y = saved_pos['y']
        else:
            main_x = self.root.winfo_x()
            main_y = self.root.winfo_y()
            main_width = self.root.winfo_width()
            main_height = self.root.winfo_height()
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
        
        tool_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(tool_tab, text="Tool")
        
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
        
        def is_start_menu_shortcut_present():
            """Check if Start Menu shortcut exists"""
            start_menu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
            shortcut_path = os.path.join(start_menu, "Roblox Account Manager.lnk")
            return os.path.exists(shortcut_path)
        
        def toggle_start_menu_shortcut():
            """Create or remove Start Menu shortcut"""
            start_menu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
            shortcut_path = os.path.join(start_menu, "Roblox Account Manager.lnk")
            
            if start_menu_var.get():
                try:
                    import subprocess
                    exe_path = os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else sys.argv[0])
                    if not getattr(sys, 'frozen', False):
                        exe_path = os.path.abspath(sys.argv[0])
                    
                    ps_script = f'''
                    $WshShell = New-Object -comObject WScript.Shell
                    $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
                    $Shortcut.TargetPath = "{exe_path}"
                    $Shortcut.WorkingDirectory = "{os.path.dirname(exe_path)}"
                    $Shortcut.Description = "Roblox Account Manager"
                    $Shortcut.Save()
                    '''
                    subprocess.run(["powershell", "-Command", ps_script], 
                                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    print("[INFO] Start Menu shortcut created")
                except Exception as e:
                    print(f"[ERROR] Failed to create Start Menu shortcut: {e}")
                    start_menu_var.set(False)
            else:
                try:
                    if os.path.exists(shortcut_path):
                        os.remove(shortcut_path)
                        print("[INFO] Start Menu shortcut removed")
                except Exception as e:
                    print(f"[ERROR] Failed to remove Start Menu shortcut: {e}")
        
        start_menu_var = tk.BooleanVar(value=is_start_menu_shortcut_present())
        start_menu_check = ttk.Checkbutton(
            main_frame,
            text="Add to Start Menu",
            variable=start_menu_var,
            style="Dark.TCheckbutton",
            command=toggle_start_menu_shortcut
        )
        start_menu_check.pack(anchor="w", pady=2)
        
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
        
        def get_launcher_display_name(launcher):
            launcher_names = {
                "default": "Default",
                "bloxstrap": "Bloxstrap",
                "fishstrap": "Fishstrap",
                "froststrap": "Froststrap",
                "client": "Roblox Client"
            }
            return launcher_names.get(launcher, "Default")
        
        def open_launcher_selection():
            launcher_window = tk.Toplevel(settings_window)
            launcher_window.title("Roblox Launcher")
            launcher_window.geometry("350x300")
            launcher_window.configure(bg=self.BG_DARK)
            launcher_window.resizable(False, False)
            launcher_window.transient(settings_window)
            launcher_window.grab_set()
            self.apply_window_icon(launcher_window)
            
            if self.settings.get("enable_topmost", False):
                launcher_window.attributes("-topmost", True)
            
            launcher_window.update_idletasks()
            x = settings_window.winfo_x() + (settings_window.winfo_width() // 2) - (launcher_window.winfo_width() // 2)
            y = settings_window.winfo_y() + (settings_window.winfo_height() // 2) - (launcher_window.winfo_height() // 2)
            launcher_window.geometry(f"+{x}+{y}")
            
            container = ttk.Frame(launcher_window, style="Dark.TFrame")
            container.pack(fill="both", expand=True, padx=20, pady=20)
            
            header_frame = ttk.Frame(container, style="Dark.TFrame")
            header_frame.pack(fill="x", pady=(0, 15))
            
            ttk.Label(
                header_frame,
                text="Select a Launcher",
                style="Dark.TLabel",
                font=(self.FONT_FAMILY, 11, "bold")
            ).pack(anchor="w")
            
            ttk.Label(
                header_frame,
                text="Choose how to launch Roblox games",
                style="Dark.TLabel",
                font=(self.FONT_FAMILY, 8)
            ).pack(anchor="w", pady=(2, 0))
            
            separator = ttk.Frame(container, style="Dark.TFrame", height=1)
            separator.pack(fill="x", pady=(0, 15))
            separator.configure(relief="solid", borderwidth=1)
            
            current_launcher = self.settings.get("roblox_launcher", "default")
            launcher_var = tk.StringVar(value=current_launcher)
            
            radio_style = ttk.Style()
            radio_style.configure(
                "Dark.TRadiobutton",
                background=self.BG_DARK,
                foreground=self.FG_TEXT,
                font=(self.FONT_FAMILY, 9)
            )
            radio_style.map(
                "Dark.TRadiobutton",
                background=[('active', self.BG_DARK)],
                foreground=[('active', self.FG_TEXT)]
            )
            
            launchers_frame = ttk.Frame(container, style="Dark.TFrame")
            launchers_frame.pack(fill="both", expand=True)
            
            launchers = [
                ("Default", "default"),
                ("Bloxstrap", "bloxstrap"),
                ("Fishstrap", "fishstrap"),
                ("Froststrap", "froststrap"),
                ("Roblox Client", "client")
            ]
            
            for name, value in launchers:
                rb = ttk.Radiobutton(
                    launchers_frame,
                    text=name,
                    variable=launcher_var,
                    value=value,
                    style="Dark.TRadiobutton"
                )
                rb.pack(anchor="w", pady=3)
            
            def save_and_close():
                selected = launcher_var.get()
                self.settings["roblox_launcher"] = selected
                self.save_settings()
                launcher_window.destroy()
            
            ttk.Button(
                container,
                text="Close",
                style="Dark.TButton",
                command=save_and_close
            ).pack(fill="x", pady=(15, 0))
        
        launcher_btn = ttk.Button(
            roblox_frame,
            text="Roblox Launcher",
            style="Dark.TButton",
            command=open_launcher_selection
        )
        launcher_btn.pack(fill="x", pady=(0, 5))
        
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
        force_close_btn.pack(fill="x", pady=(0, 5))
        
        rename_var = tk.BooleanVar(value=self.settings.get("rename_roblox_windows", False))
        
        def on_rename_toggle():
            enabled = rename_var.get()
            self.settings["rename_roblox_windows"] = enabled
            self.save_settings()
            
            if enabled:
                self.start_rename_monitoring()
            else:
                self.stop_rename_monitoring()
        
        ttk.Checkbutton(
            roblox_frame,
            text="Rename Roblox Windows",
            variable=rename_var,
            style="Dark.TCheckbutton",
            command=on_rename_toggle
        ).pack(anchor="w", pady=(0, 10))
        
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
            text="Action Key:",
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        ).pack(side="left")
        
        current_key = self.settings.get("anti_afk_key", "w")
        
        key_button = ttk.Button(
            action_frame,
            text=current_key.upper(),
            style="Dark.TButton",
            width=14
        )
        key_button.pack(side="right")
        
        def start_key_recording():
            key_button.config(text="Press...")
            key_button.focus_set()
            
            def finish_recording(recorded_key):
                key_button.config(text=recorded_key.upper())
                self.settings["anti_afk_key"] = recorded_key
                self.save_settings()
                
                key_button.unbind("<KeyPress>")
                key_button.unbind("<Button-1>")
                key_button.unbind("<Button-2>")
                key_button.unbind("<Button-3>")
                key_button.unbind("<Button-4>")
                key_button.unbind("<Button-5>")
                key_button.unbind("<MouseWheel>")
            
            def on_key_press(event):
                key = event.keysym.lower()
                
                key_mapping = {
                    "return": "enter",
                    "control_l": "ctrl",
                    "control_r": "ctrl",
                    "shift_l": "shift",
                    "shift_r": "shift",
                    "alt_l": "alt",
                    "alt_r": "alt"
                }
                
                key = key_mapping.get(key, key)
                finish_recording(key)
                return "break"
            
            def on_mouse_button(event):
                mouse_mapping = {
                    1: "lmb",
                    2: "mmb",
                    3: "rmb",
                    4: "xbutton1",
                    5: "xbutton2"
                }
                button = mouse_mapping.get(event.num, f"mouse{event.num}")
                finish_recording(button)
                return "break"
            
            def on_scroll(event):
                if event.delta > 0:
                    finish_recording("scroll_up")
                else:
                    finish_recording("scroll_down")
                return "break"
            
            key_button.bind("<KeyPress>", on_key_press)
            key_button.bind("<Button-1>", on_mouse_button)
            key_button.bind("<Button-2>", on_mouse_button)
            key_button.bind("<Button-3>", on_mouse_button)
            key_button.bind("<Button-4>", on_mouse_button)
            key_button.bind("<Button-5>", on_mouse_button)
            key_button.bind("<MouseWheel>", on_scroll)
        
        key_button.config(command=start_key_recording)
        
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
            to=19,
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
        
        amount_frame = ttk.Frame(settings_frame, style="Dark.TFrame")
        amount_frame.pack(fill="x", pady=2)
        
        ttk.Label(
            amount_frame,
            text="Key Press Amount:",
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        ).pack(side="left")
        
        amount_var = tk.IntVar(value=self.settings.get("anti_afk_key_amount", 1))
        
        def on_amount_change():
            try:
                new_value = amount_var.get()
                self.settings["anti_afk_key_amount"] = new_value
                self.save_settings()
            except:
                pass
        
        amount_spinner = tk.Spinbox(
            amount_frame,
            from_=1,
            to=10,
            textvariable=amount_var,
            width=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_LIGHT,
            font=(self.FONT_FAMILY, 9),
            command=on_amount_change,
            readonlybackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            selectforeground=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=0
        )
        amount_spinner.pack(side="right")
        
        amount_spinner.bind("<KeyRelease>", lambda e: on_amount_change())
        amount_spinner.bind("<FocusOut>", lambda e: on_amount_change())
        
        if self.settings.get("anti_afk_enabled", False):
            self.root.after(1000, self.start_anti_afk)
        
        if self.settings.get("rename_roblox_windows", False):
            self.root.after(1000, self.start_rename_monitoring)
        
        if self.settings.get("active_instances_monitoring", False):
            self.root.after(1500, self.start_instances_monitoring)
        
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
            if hasattr(self, 'discord_btn') and self.discord_btn:
                self.discord_btn.config(bg=self.BG_DARK, activebackground=self.BG_DARK)
            if hasattr(self, 'discord_btn') and self.discord_btn:
                self.discord_btn.config(bg=self.BG_DARK, activebackground=self.BG_DARK)
            
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
        
        ttk.Button(
            about_frame,
            text="Discord Server",
            style="Dark.TButton",
            command=lambda: webbrowser.open("https://discord.gg/SZaZU8zwZA")
        ).pack(fill="x", pady=(0, 10))
        
        def open_github():
            webbrowser.open("https://github.com/evanovar/RobloxAccountManager")

        
        ttk.Button(
            about_frame,
            text="Open GitHub Repository",
            style="Dark.TButton",
            command=open_github
        ).pack(fill="x", pady=(0, 10))
        
        tool_frame = ttk.Frame(tool_tab, style="Dark.TFrame")
        tool_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        ttk.Label(
            tool_frame,
            text="Tools",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 15))
        
        def wipe_data():
            """Wipe data"""
            if not messagebox.askyesno("Confirm Wipe Data", "Are you sure you want to wipe ALL data?\n\nThis action cannot be undone!"):
                return
            
            encryption_method = self.manager.get_encryption_method()
            
            if encryption_method == "password":
                password_window = tk.Toplevel(settings_window)
                self.apply_window_icon(password_window)
                password_window.title("Enter Password")
                password_window.geometry("350x150")
                password_window.configure(bg=self.BG_DARK)
                password_window.resizable(False, False)
                password_window.transient(settings_window)
                password_window.grab_set()
                
                settings_window.update_idletasks()
                x = settings_window.winfo_x() + (settings_window.winfo_width() - 350) // 2
                y = settings_window.winfo_y() + (settings_window.winfo_height() - 150) // 2
                password_window.geometry(f"350x150+{x}+{y}")
                
                main_frame = ttk.Frame(password_window, style="Dark.TFrame")
                main_frame.pack(fill="both", expand=True, padx=20, pady=20)
                
                ttk.Label(main_frame, text="Enter your password:", style="Dark.TLabel").pack(anchor="w", pady=(0, 10))
                
                password_entry = ttk.Entry(main_frame, style="Dark.TEntry", show="*")
                password_entry.pack(fill="x", pady=(0, 15))
                password_entry.focus_set()
                
                def verify_and_wipe():
                    password = password_entry.get()
                    if not password:
                        messagebox.showwarning("Missing Password", "Please enter your password.")
                        return
                    
                    if self.manager.verify_password(password):
                        password_window.destroy()
                        if messagebox.askyesno("Final Confirmation", "This will permanently delete ALL data. Continue?"):
                            settings_window.destroy()
                            self.manager.wipe_all_data()
                            messagebox.showinfo("Success", "All data has been wiped!")
                            settings_window.quit()
                    else:
                        messagebox.showerror("Invalid Password", "Password is incorrect.")
                
                btn_frame = ttk.Frame(main_frame, style="Dark.TFrame")
                btn_frame.pack(fill="x")
                
                ttk.Button(btn_frame, text="Verify", style="Dark.TButton", command=verify_and_wipe).pack(side="left", fill="x", expand=True, padx=(0, 5))
                ttk.Button(btn_frame, text="Cancel", style="Dark.TButton", command=password_window.destroy).pack(side="left", fill="x", expand=True, padx=(5, 0))
            else:
                if messagebox.askyesno("Final Confirmation", "This will permanently delete ALL data. Continue?"):
                    settings_window.destroy()
                    self.manager.wipe_all_data()
                    messagebox.showinfo("Success", "All data has been wiped!")
                    settings_window.quit()
        
        
        def switch_encryption_method():
            """Switch encryption method"""
            current_method = self.manager.get_encryption_method()
            
            if current_method == "password":
                password_window = tk.Toplevel(settings_window)
                self.apply_window_icon(password_window)
                password_window.title("Verify Password")
                password_window.geometry("350x150")
                password_window.configure(bg=self.BG_DARK)
                password_window.resizable(False, False)
                password_window.transient(settings_window)
                password_window.grab_set()
                
                settings_window.update_idletasks()
                x = settings_window.winfo_x() + (settings_window.winfo_width() - 350) // 2
                y = settings_window.winfo_y() + (settings_window.winfo_height() - 150) // 2
                password_window.geometry(f"350x150+{x}+{y}")
                
                pwd_frame = ttk.Frame(password_window, style="Dark.TFrame")
                pwd_frame.pack(fill="both", expand=True, padx=20, pady=20)
                
                ttk.Label(pwd_frame, text="Enter your password to continue:", style="Dark.TLabel").pack(anchor="w", pady=(0, 10))
                
                password_entry = ttk.Entry(pwd_frame, style="Dark.TEntry", show="*")
                password_entry.pack(fill="x", pady=(0, 15))
                password_entry.focus_set()
                
                def verify_and_proceed():
                    password = password_entry.get()
                    if not password:
                        messagebox.showwarning("Missing Password", "Please enter your password.")
                        return
                    
                    if self.manager.verify_password(password):
                        password_window.destroy()
                        settings_window.destroy()
                        self._run_encryption_switch()
                    else:
                        messagebox.showerror("Invalid Password", "Password is incorrect.")
                
                pwd_btn_frame = ttk.Frame(pwd_frame, style="Dark.TFrame")
                pwd_btn_frame.pack(fill="x")
                
                ttk.Button(pwd_btn_frame, text="Verify", style="Dark.TButton", command=verify_and_proceed).pack(side="left", fill="x", expand=True, padx=(0, 5))
                ttk.Button(pwd_btn_frame, text="Cancel", style="Dark.TButton", command=password_window.destroy).pack(side="left", fill="x", expand=True, padx=(5, 0))
            else:
                settings_window.destroy()
                self._run_encryption_switch()
        
        ttk.Button(
            tool_frame,
            text="Switch Encryption Method",
            style="Dark.TButton",
            command=switch_encryption_method
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Browser Engine",
            style="Dark.TButton",
            command=self.open_browser_engine_window
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Roblox Settings",
            style="Dark.TButton",
            command=self.open_roblox_settings_window
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Active Instances",
            style="Dark.TButton",
            command=self.open_active_instances_window
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Roblox Version",
            style="Dark.TButton",
            command=self.open_roblox_version_window
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Wipe Data",
            style="Dark.TButton",
            command=wipe_data
        ).pack(side="bottom", fill="x", pady=(10, 0))
    
    def start_instances_monitoring(self):
        """Start background monitoring of active Roblox instances"""
        if self.instances_monitor_thread and self.instances_monitor_thread.is_alive():
            return
        
        self.instances_monitor_stop.clear()
        self.instances_monitor_thread = threading.Thread(target=self._instances_monitor_worker, daemon=True)
        self.instances_monitor_thread.start()
        print("[INFO] Active Instances background monitoring started")
    
    def stop_instances_monitoring(self):
        """Stop background monitoring of active Roblox instances"""
        if self.instances_monitor_thread:
            self.instances_monitor_stop.set()
            self.instances_monitor_thread = None
            self.instances_data.clear()
            self.instances_pids.clear()
            print("[INFO] Active Instances background monitoring stopped")
    
    def _instances_monitor_worker(self):
        """Background thread that continuously monitors Roblox instances"""
        import psutil
        import time
        
        while not self.instances_monitor_stop.is_set():
            try:
                new_pids = set()
                processes = []
                
                for proc in psutil.process_iter(['pid', 'name', 'create_time', 'memory_info']):
                    try:
                        if proc.info['name'].lower() == 'robloxplayerbeta.exe':
                            pid = proc.info['pid']
                            if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                                new_pids.add(pid)
                                processes.append(proc)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                current_time = time.time()
                failed_pids_to_retry = []
                for pid, (fail_time, create_time, memory_mb) in list(self.instances_failed_pids.items()):
                    if current_time - fail_time >= 5:
                        if pid in new_pids:
                            failed_pids_to_retry.append((pid, create_time, memory_mb))
                        else:
                            del self.instances_failed_pids[pid]
                
                if new_pids != self.instances_pids:
                    print(f"[INFO] Active Instances: PID change detected. Old: {self.instances_pids}, New: {new_pids}")
                    self.instances_pids = new_pids.copy()
                    
                    new_data = []
                    used_logs = set()
                    
                    for proc in processes:
                        pid = proc.info['pid']
                        
                        try:
                            memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                            create_time = proc.info['create_time']
                        except:
                            memory_mb = 0
                            create_time = 0
                        
                        user_id, _ = self._get_user_id_from_pid(pid, used_logs)
                        username = None
                        avatar_url = None
                        
                        if user_id:
                            if user_id in self.instances_cache["user_id_to_username"]:
                                username = self.instances_cache["user_id_to_username"][user_id]
                            else:
                                for account in self.manager.accounts:
                                    stored_uid = self.manager.accounts[account].get("user_id")
                                    if stored_uid == user_id or stored_uid == str(user_id):
                                        username = account
                                        self.instances_cache["user_id_to_username"][user_id] = username
                                        break
                                
                                if not username:
                                    username = RobloxAPI.get_username_from_user_id(user_id)
                                    if username:
                                        self.instances_cache["user_id_to_username"][user_id] = username
                                        for account in self.manager.accounts:
                                            if account == username:
                                                self.manager.accounts[account]["user_id"] = str(user_id)
                                                self.manager.save_accounts()
                                                break
                            
                            if user_id in self.instances_cache["user_id_to_avatar"]:
                                avatar_url = self.instances_cache["user_id_to_avatar"][user_id]
                            else:
                                avatar_url = RobloxAPI.get_user_avatar_url(user_id, "150x150")
                                if avatar_url:
                                    self.instances_cache["user_id_to_avatar"][user_id] = avatar_url
                        
                        new_data.append({
                            "pid": pid, "user_id": user_id, "username": username,
                            "avatar_url": avatar_url, "create_time": create_time, "memory_mb": memory_mb
                        })
                        
                        if not user_id:
                            self.instances_failed_pids[pid] = (current_time, create_time, memory_mb)
                        elif pid in self.instances_failed_pids:
                            del self.instances_failed_pids[pid]
                    
                    self.instances_data = new_data
                elif failed_pids_to_retry:
                    print(f"[INFO] Active Instances: Retrying {len(failed_pids_to_retry)} failed PID(s)")
                    used_logs = set()
                    for pid, create_time, memory_mb in failed_pids_to_retry:
                        user_id, _ = self._get_user_id_from_pid(pid, used_logs)
                        
                        if user_id:
                            print(f"[INFO] Active Instances: Successfully got user ID for PID {pid} on retry")
                            username = None
                            avatar_url = None
                            
                            if user_id in self.instances_cache["user_id_to_username"]:
                                username = self.instances_cache["user_id_to_username"][user_id]
                            else:
                                for account in self.manager.accounts:
                                    stored_uid = self.manager.accounts[account].get("user_id")
                                    if stored_uid == user_id or stored_uid == str(user_id):
                                        username = account
                                        self.instances_cache["user_id_to_username"][user_id] = username
                                        break
                                
                                if not username:
                                    username = RobloxAPI.get_username_from_user_id(user_id)
                                    if username:
                                        self.instances_cache["user_id_to_username"][user_id] = username
                                        for account in self.manager.accounts:
                                            if account == username:
                                                self.manager.accounts[account]["user_id"] = str(user_id)
                                                self.manager.save_accounts()
                                                break
                            
                            if user_id in self.instances_cache["user_id_to_avatar"]:
                                avatar_url = self.instances_cache["user_id_to_avatar"][user_id]
                            else:
                                avatar_url = RobloxAPI.get_user_avatar_url(user_id, "150x150")
                                if avatar_url:
                                    self.instances_cache["user_id_to_avatar"][user_id] = avatar_url
                            
                            for entry in self.instances_data:
                                if entry["pid"] == pid:
                                    entry["user_id"] = user_id
                                    entry["username"] = username
                                    entry["avatar_url"] = avatar_url
                                    break
                            
                            del self.instances_failed_pids[pid]
                            self.instances_data_updated = True
                        else:
                            self.instances_failed_pids[pid] = (current_time, create_time, memory_mb)
                else:
                    for entry in self.instances_data:
                        try:
                            proc = psutil.Process(entry["pid"])
                            entry["memory_mb"] = proc.memory_info().rss / 1024 / 1024
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                
            except Exception as e:
                print(f"[ERROR] Active Instances monitor error: {e}")
            
            self.instances_monitor_stop.wait(2)
    
    def open_active_instances_window(self):
        """Open window showing all active Roblox instances with pre-cached data"""
        instances_window = tk.Toplevel(self.root)
        self.apply_window_icon(instances_window)
        instances_window.title("Active Roblox Instances")
        instances_window.geometry("400x400")
        instances_window.configure(bg=self.BG_DARK)
        instances_window.resizable(False, False)
        
        if self.settings.get("enable_topmost", False):
            instances_window.attributes("-topmost", True)
        
        instances_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (instances_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (instances_window.winfo_height() // 2)
        instances_window.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(instances_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        header_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        header_frame.pack(fill="x", pady=(0, 10))
        
        title_label = ttk.Label(
            header_frame,
            text="Active Roblox Instances",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 12, "bold")
        )
        title_label.pack(side="left")
        
        monitoring_enabled = tk.BooleanVar(value=self.settings.get("active_instances_monitoring", False))
        
        monitor_checkbox = ttk.Checkbutton(
            header_frame,
            text="Enable Active Instances",
            variable=monitoring_enabled,
            style="Dark.TCheckbutton"
        )
        monitor_checkbox.pack(side="right")
        
        canvas_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        canvas_frame.pack(fill="both", expand=True)
        
        canvas = tk.Canvas(canvas_frame, bg=self.BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="Dark.TFrame")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        status_label = ttk.Label(
            main_frame,
            text="Loading instances...",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        )
        status_label.pack(pady=(10, 0))
        
        window_active = [True]
        refresh_timer = [None]
        last_rendered_pids = [set()]
        instance_widgets = {}
        
        def on_window_close():
            window_active[0] = False
            if refresh_timer[0]:
                instances_window.after_cancel(refresh_timer[0])
            instances_window.destroy()
        
        instances_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        def render_instances():
            """Render the pre-cached instance data to the UI"""
            from PIL import Image, ImageTk
            from io import BytesIO
            
            if not window_active[0]:
                return
            
            if not monitoring_enabled.get():
                return
            
            data = list(self.instances_data)
            current_pids_set = {d["pid"] for d in data}
            
            data_was_updated = self.instances_data_updated
            if data_was_updated:
                self.instances_data_updated = False
            
            if current_pids_set != last_rendered_pids[0] or data_was_updated:
                reason = "PIDs changed" if current_pids_set != last_rendered_pids[0] else "data updated"
                print(f"[INFO] Active Instances window: {reason}, rebuilding UI")
                last_rendered_pids[0] = current_pids_set
                instance_widgets.clear()
                
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                
                if not data:
                    status_label.config(text="No active Roblox instances found")
                    ttk.Label(
                        scrollable_frame,
                        text="No active Roblox instances",
                        style="Dark.TLabel",
                        font=(self.FONT_FAMILY, 10)
                    ).pack(pady=20)
                else:
                    status_label.config(text=f"Found {len(data)} instance(s) - Last updated: {datetime.now().strftime('%H:%M:%S')}")
                    
                    for entry in data:
                        pid = entry["pid"]
                        user_id = entry["user_id"]
                        username = entry["username"]
                        avatar_url = entry["avatar_url"]
                        create_time = entry["create_time"]
                        memory_mb = entry["memory_mb"]
                        
                        instance_frame = tk.Frame(
                            scrollable_frame, bg=self.BG_MID, relief="solid", borderwidth=1
                        )
                        instance_frame.pack(fill="x", pady=5, padx=5)
                        
                        inner_frame = tk.Frame(instance_frame, bg=self.BG_MID)
                        inner_frame.pack(fill="x", padx=10, pady=10)
                        
                        try:
                            ct = datetime.fromtimestamp(create_time)
                            uptime = datetime.now() - ct
                            uptime_str = f"{int(uptime.total_seconds() // 3600)}h {int((uptime.total_seconds() % 3600) // 60)}m"
                        except:
                            uptime_str = "Unknown"
                        
                        if username:
                            avatar_label = tk.Label(inner_frame, bg=self.BG_MID)
                            avatar_label.pack(side="left", padx=(0, 15))
                            
                            if user_id and user_id in self.instances_cache["user_id_to_photo"]:
                                photo = self.instances_cache["user_id_to_photo"][user_id]
                                avatar_label.config(image=photo)
                                avatar_label.image = photo
                            else:
                                avatar_label.config(text="...", font=(self.FONT_FAMILY, 24), fg=self.FG_TEXT)
                                
                                def download_avatar(uid, url, label, win):
                                    try:
                                        if url:
                                            response = requests.get(url, timeout=5)
                                            if response.status_code == 200:
                                                img_data = BytesIO(response.content)
                                                img = Image.open(img_data)
                                                img = img.resize((70, 70), Image.Resampling.LANCZOS)
                                                photo = ImageTk.PhotoImage(img)
                                                self.instances_cache["user_id_to_photo"][uid] = photo
                                                def update_label():
                                                    try:
                                                        if window_active[0] and label.winfo_exists():
                                                            label.config(image=photo)
                                                            label.image = photo
                                                    except:
                                                        pass
                                                win.after(0, update_label)
                                                return
                                        def update_fallback():
                                            try:
                                                if window_active[0] and label.winfo_exists():
                                                    label.config(text="[?]", font=(self.FONT_FAMILY, 24), fg=self.FG_TEXT)
                                            except:
                                                pass
                                        win.after(0, update_fallback)
                                    except Exception as e:
                                        print(f"[ERROR] Failed to load avatar for user {uid}: {e}")
                                        def update_error():
                                            try:
                                                if window_active[0] and label.winfo_exists():
                                                    label.config(text="[?]", font=(self.FONT_FAMILY, 24), fg=self.FG_TEXT)
                                            except:
                                                pass
                                        win.after(0, update_error)
                                
                                if user_id and avatar_url:
                                    threading.Thread(target=download_avatar, args=(user_id, avatar_url, avatar_label, instances_window), daemon=True).start()
                                else:
                                    avatar_label.config(text="[?]", font=(self.FONT_FAMILY, 24), fg=self.FG_TEXT)
                            
                            info_frame = tk.Frame(inner_frame, bg=self.BG_MID)
                            info_frame.pack(side="left", fill="both", expand=True)
                            
                            tk.Label(info_frame, text=username, bg=self.BG_MID, fg=self.FG_TEXT,
                                     font=(self.FONT_FAMILY, 12, "bold"), anchor="w").pack(anchor="w")
                            
                            details1_frame = tk.Frame(info_frame, bg=self.BG_MID)
                            details1_frame.pack(anchor="w", pady=(2, 0))
                            tk.Label(details1_frame, text=f"PID: {pid}", bg=self.BG_MID, fg=self.FG_TEXT,
                                     font=(self.FONT_FAMILY, 9), anchor="w").pack(side="left", padx=(0, 15))
                            tk.Label(details1_frame, text=f"User ID: {user_id}", bg=self.BG_MID, fg=self.FG_TEXT,
                                     font=(self.FONT_FAMILY, 9), anchor="w").pack(side="left")
                            
                            details2_frame = tk.Frame(info_frame, bg=self.BG_MID)
                            details2_frame.pack(anchor="w", pady=(2, 0))
                            uptime_label = tk.Label(details2_frame, text=f"Uptime: {uptime_str}", bg=self.BG_MID, fg="#90EE90",
                                     font=(self.FONT_FAMILY, 9), anchor="w")
                            uptime_label.pack(side="left", padx=(0, 15))
                            memory_label = tk.Label(details2_frame, text=f"Memory: {memory_mb:.0f} MB", bg=self.BG_MID, fg="#87CEEB",
                                     font=(self.FONT_FAMILY, 9), anchor="w")
                            memory_label.pack(side="left")
                            
                            instance_widgets[pid] = {'uptime_label': uptime_label, 'memory_label': memory_label, 'create_time': create_time}
                        elif user_id:
                            tk.Label(inner_frame, text=f"PID: {pid} - Failed to get username (Uptime: {uptime_str})",
                                     bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 10)).pack()
                        else:
                            tk.Label(inner_frame, text=f"PID: {pid} - Failed to get user ID (Uptime: {uptime_str}, Memory: {memory_mb:.0f} MB)",
                                     bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 10)).pack()
            else:
                if data:
                    status_label.config(text=f"Found {len(data)} instance(s) - Last updated: {datetime.now().strftime('%H:%M:%S')}")
                    
                    for entry in data:
                        pid = entry["pid"]
                        if pid in instance_widgets:
                            widgets = instance_widgets[pid]
                            
                            try:
                                create_time = widgets['create_time']
                                ct = datetime.fromtimestamp(create_time)
                                uptime = datetime.now() - ct
                                uptime_str = f"{int(uptime.total_seconds() // 3600)}h {int((uptime.total_seconds() % 3600) // 60)}m"
                                if widgets['uptime_label'].winfo_exists():
                                    widgets['uptime_label'].config(text=f"Uptime: {uptime_str}")
                            except:
                                pass
                            
                            try:
                                memory_mb = entry.get("memory_mb", 0)
                                if widgets['memory_label'].winfo_exists():
                                    widgets['memory_label'].config(text=f"Memory: {memory_mb:.0f} MB")
                            except:
                                pass
            
            if window_active[0] and monitoring_enabled.get():
                refresh_timer[0] = instances_window.after(2000, render_instances)
        
        def toggle_monitoring():
            enabled = monitoring_enabled.get()
            self.settings["active_instances_monitoring"] = enabled
            self.save_settings()
            print(f"[INFO] Active Instances {'enabled' if enabled else 'disabled'}")
            if enabled:
                last_rendered_pids[0] = set()
                instance_widgets.clear()
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                
                self.start_instances_monitoring()
                refresh_btn.config(state="normal")
                status_label.config(text="Starting monitoring...")
                render_instances()
            else:
                self.stop_instances_monitoring()
                refresh_btn.config(state="disabled")
                if refresh_timer[0]:
                    instances_window.after_cancel(refresh_timer[0])
                    refresh_timer[0] = None
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                status_label.config(text="Active Instances disabled")
                ttk.Label(
                    scrollable_frame,
                    text="Enable the checkbox to start monitoring",
                    style="Dark.TLabel",
                    font=(self.FONT_FAMILY, 10)
                ).pack(pady=20)
        
        monitor_checkbox.config(command=toggle_monitoring)
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(10, 0))
        
        refresh_btn = ttk.Button(
            button_frame,
            text="Refresh Now",
            style="Dark.TButton",
            command=render_instances,
            state="normal" if monitoring_enabled.get() else "disabled"
        )
        refresh_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Close",
            style="Dark.TButton",
            command=on_window_close
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        if monitoring_enabled.get():
            render_instances()
        else:
            status_label.config(text="Active Instances disabled")
            ttk.Label(
                scrollable_frame,
                text="Enable the checkbox to start monitoring",
                style="Dark.TLabel",
                font=(self.FONT_FAMILY, 10)
            ).pack(pady=20)
    
    def open_browser_engine_window(self):
        """Open Browser Engine selection window"""
        browser_window = tk.Toplevel(self.root)
        self.apply_window_icon(browser_window)
        browser_window.title("Browser Engine Settings")
        browser_window.geometry("420x330")
        browser_window.configure(bg=self.BG_DARK)
        browser_window.resizable(False, False)
        browser_window.transient(self.root)
        
        if self.settings.get("enable_topmost", False):
            browser_window.attributes("-topmost", True)
        
        browser_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (browser_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (browser_window.winfo_height() // 2)
        browser_window.geometry(f"+{x}+{y}")
        
        current_browser = self.settings.get("browser_type", "chrome")
        browser_var = tk.StringVar(value=current_browser)
        chrome_installed = self.is_chrome_installed()
        chromium_path = os.path.join(self.data_folder, "Chromium", "chrome-win64", "chrome.exe")
        chromium_installed = os.path.exists(chromium_path)
        
        container = ttk.Frame(browser_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        header_frame = ttk.Frame(container, style="Dark.TFrame")
        header_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            header_frame,
            text="Select Browser Engine",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text="Choose which browser to use for Add Account",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(2, 0))
        
        separator = ttk.Frame(container, style="Dark.TFrame", height=1)
        separator.pack(fill="x", pady=(0, 15))
        separator.configure(relief="solid", borderwidth=1)
        
        options_frame = ttk.Frame(container, style="Dark.TFrame")
        options_frame.pack(fill="both", expand=True)
        
        radio_style = ttk.Style()
        radio_style.configure(
            "Browser.TRadiobutton",
            background=self.BG_DARK,
            foreground=self.FG_TEXT,
            font=(self.FONT_FAMILY, 10)
        )
        radio_style.map(
            "Browser.TRadiobutton",
            background=[("active", self.BG_DARK)],
            foreground=[("active", self.FG_TEXT)]
        )
        
        chrome_frame = ttk.Frame(options_frame, style="Dark.TFrame")
        chrome_frame.pack(fill="x", pady=(0, 8))
        
        chrome_radio = ttk.Radiobutton(
            chrome_frame,
            text="Google Chrome",
            variable=browser_var,
            value="chrome",
            style="Browser.TRadiobutton"
        )
        chrome_radio.pack(side="left")
        
        chrome_status = "✓ Installed" if chrome_installed else "Not Installed"
        chrome_color = "#00FF00" if chrome_installed else "#FF6666"
        tk.Label(
            chrome_frame,
            text=f"  [{chrome_status}]",
            bg=self.BG_DARK,
            fg=chrome_color,
            font=(self.FONT_FAMILY, 9)
        ).pack(side="left")
        
        chromium_frame = ttk.Frame(options_frame, style="Dark.TFrame")
        chromium_frame.pack(fill="x", pady=(0, 15))
        
        chromium_radio = ttk.Radiobutton(
            chromium_frame,
            text="Chromium",
            variable=browser_var,
            value="chromium",
            style="Browser.TRadiobutton"
        )
        chromium_radio.pack(side="left")
        
        chromium_status_text = "✓ Installed" if chromium_installed else "Not Installed"
        chromium_color = "#00FF00" if chromium_installed else "#FF6666"
        chromium_status_label = tk.Label(
            chromium_frame,
            text=f"  [{chromium_status_text}]",
            bg=self.BG_DARK,
            fg=chromium_color,
            font=(self.FONT_FAMILY, 9)
        )
        chromium_status_label.pack(side="left")
        
        progress_outer = tk.Frame(options_frame, bg=self.BG_LIGHT, relief="solid", borderwidth=1)
        
        progress_inner = tk.Frame(progress_outer, bg=self.BG_MID, height=22)
        progress_inner.pack(fill="x", padx=1, pady=1)
        progress_inner.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_inner, bg=self.BG_LIGHT, width=0)
        progress_fill.place(x=0, y=0, relheight=1)
        
        progress_label = tk.Label(
            progress_inner,
            text="0%",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        progress_label.place(relx=0.5, rely=0.5, anchor="center")
        
        status_label = ttk.Label(
            options_frame,
            text="",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        )
        
        def update_progress(percent):
            """Update the custom progress bar"""
            progress_inner.update_idletasks()
            total_width = progress_inner.winfo_width()
            fill_width = int((percent / 100) * total_width)
            progress_fill.place(x=0, y=0, relheight=1, width=fill_width)
            
            label_x = total_width // 2
            if fill_width >= label_x:
                progress_label.config(bg=self.BG_LIGHT, fg=self.BG_DARK)
            else:
                progress_label.config(bg=self.BG_MID, fg=self.FG_TEXT)
            
            progress_label.config(text=f"{int(percent)}%")
            browser_window.update()
        
        download_btn = None
        
        def download_chromium():
            """Download portable Chromium"""
            nonlocal chromium_installed
            
            download_btn.config(state="disabled", text="Downloading...")
            progress_outer.pack(fill="x", pady=(0, 10))
            status_label.pack(anchor="w", pady=(0, 10))
            status_label.config(text="Downloading Chromium...")
            browser_window.update()
            
            def do_download():
                try:
                    chromium_dir = os.path.join(self.data_folder, "Chromium")
                    os.makedirs(chromium_dir, exist_ok=True)
                    
                    browser_window.after(0, lambda: status_label.config(text="Fetching latest version..."))
                    last_change_url = "https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/LAST_CHANGE"
                    last_change_response = requests.get(last_change_url, timeout=30)
                    if last_change_response.status_code != 200:
                        raise Exception("Failed to fetch latest Chromium version")
                    build_number = last_change_response.text.strip()
                    
                    download_url = f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{build_number}/chrome-win.zip"
                    browser_window.after(0, lambda: status_label.config(text=f"Downloading build {build_number}..."))
                    zip_path = os.path.join(chromium_dir, "chromium.zip")
                    
                    response = requests.get(download_url, stream=True, timeout=60)
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    last_progress = 0
                    
                    with open(zip_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    progress = int((downloaded / total_size) * 100)
                                    if progress >= last_progress + 1:
                                        last_progress = progress
                                        browser_window.after(10, lambda p=progress: update_progress(p))
                    
                    browser_window.after(0, lambda: update_progress(100))
                    browser_window.after(0, lambda: status_label.config(text="Extracting Chromium..."))
                    browser_window.after(50, lambda: update_progress(0))
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        file_list = zip_ref.namelist()
                        total_files = len(file_list)
                        for i, file in enumerate(file_list):
                            zip_ref.extract(file, chromium_dir)
                            if i % 50 == 0:
                                progress = int((i / total_files) * 100)
                                browser_window.after(0, lambda p=progress: update_progress(p))
                    
                    browser_window.after(0, lambda: update_progress(100))
                    
                    extracted_folder = os.path.join(chromium_dir, "chrome-win")
                    target_folder = os.path.join(chromium_dir, "chrome-win64")
                    if os.path.exists(extracted_folder) and not os.path.exists(target_folder):
                        os.rename(extracted_folder, target_folder)
                    
                    os.remove(zip_path)
                    
                    browser_window.after(0, lambda: status_label.config(text="Downloading ChromeDriver..."))
                    browser_window.after(50, lambda: update_progress(0))
                    
                    chromedriver_url = f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{build_number}/chromedriver_win32.zip"
                    chromedriver_zip_path = os.path.join(chromium_dir, "chromedriver.zip")
                    
                    chromedriver_response = requests.get(chromedriver_url, stream=True, timeout=60)
                    cd_total_size = int(chromedriver_response.headers.get('content-length', 0))
                    cd_downloaded = 0
                    cd_last_progress = 0
                    
                    with open(chromedriver_zip_path, 'wb') as f:
                        for chunk in chromedriver_response.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                cd_downloaded += len(chunk)
                                if cd_total_size > 0:
                                    progress = int((cd_downloaded / cd_total_size) * 100)
                                    if progress >= cd_last_progress + 1:
                                        cd_last_progress = progress
                                        browser_window.after(10, lambda p=progress: update_progress(p))
                    
                    browser_window.after(0, lambda: update_progress(100))
                    browser_window.after(0, lambda: status_label.config(text="Extracting ChromeDriver..."))
                    browser_window.after(50, lambda: update_progress(0))
                    
                    with zipfile.ZipFile(chromedriver_zip_path, 'r') as zip_ref:
                        zip_ref.extractall(chromium_dir)
                    
                    browser_window.after(0, lambda: update_progress(100))
                    
                    chromedriver_extracted = os.path.join(chromium_dir, "chromedriver-win32", "chromedriver.exe")
                    chromedriver_target = os.path.join(target_folder, "chromedriver.exe")
                    if os.path.exists(chromedriver_extracted):
                        shutil.copy2(chromedriver_extracted, chromedriver_target)
                        shutil.rmtree(os.path.join(chromium_dir, "chromedriver-win32"))
                    
                    os.remove(chromedriver_zip_path)
                    
                    def update_ui():
                        nonlocal chromium_installed
                        chromium_installed = os.path.exists(os.path.join(chromium_dir, "chrome-win64", "chrome.exe"))
                        if chromium_installed:
                            chromium_status_label.config(text="  [✓ Installed]", fg="#00FF00")
                            download_btn.config(state="disabled", text="✓ Downloaded")
                            status_label.config(text="Chromium downloaded successfully!")
                        else:
                            download_btn.config(state="normal", text="Download Chromium")
                            status_label.config(text="Failed to extract Chromium.")
                        progress_outer.pack_forget()
                    
                    browser_window.after(0, update_ui)
                    
                except Exception as download_error:
                    error_msg = str(download_error)
                    def show_error():
                        download_btn.config(state="normal", text="Download Chromium")
                        progress_outer.pack_forget()
                        status_label.config(text=f"Download failed: {error_msg[:50]}...")
                    browser_window.after(0, show_error)
            
            thread = threading.Thread(target=do_download, daemon=True)
            thread.start()
        
        if not chromium_installed:
            download_btn = ttk.Button(
                options_frame,
                text="Download Chromium",
                style="Dark.TButton",
                command=download_chromium
            )
            download_btn.pack(fill="x", pady=(0, 10))
        else:
            download_btn = ttk.Button(
                options_frame,
                text="✓ Downloaded",
                style="Dark.TButton",
                state="disabled"
            )
            download_btn.pack(fill="x", pady=(0, 10))
        
        def on_browser_change(*args):
            nonlocal chromium_installed
            selected = browser_var.get()
            if selected == "chromium" and not chromium_installed:
                messagebox.showwarning(
                    "Chromium Not Installed",
                    "Please download Chromium first."
                )
                browser_var.set("chrome")
                return
            if selected == "chrome" and not chrome_installed:
                messagebox.showwarning(
                    "Chrome Not Installed",
                    "Google Chrome is not installed.\nPlease install Chrome or use Chromium."
                )
                if chromium_installed:
                    browser_var.set("chromium")
                return
            self.settings["browser_type"] = selected
            self.save_settings()
        
        browser_var.trace_add("write", on_browser_change)
        
        ttk.Button(
            container,
            text="Close",
            style="Dark.TButton",
            command=browser_window.destroy
        ).pack(fill="x", pady=(10, 0))
    
    def open_roblox_version_window(self):
        """Open Roblox Version downloader window"""
        version_window = tk.Toplevel(self.root)
        self.apply_window_icon(version_window)
        version_window.title("Roblox Version Downloader")
        version_window.geometry("500x550")
        version_window.configure(bg=self.BG_DARK)
        version_window.resizable(False, False)
        version_window.transient(self.root)
        
        if self.settings.get("enable_topmost", False):
            version_window.attributes("-topmost", True)
        
        version_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (version_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (version_window.winfo_height() // 2)
        version_window.geometry(f"+{x}+{y}")
        
        container = ttk.Frame(version_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        header_frame = ttk.Frame(container, style="Dark.TFrame")
        header_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            header_frame,
            text="Roblox Version Downloader",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text="Download and install specific Roblox versions",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(2, 0))
        
        separator = ttk.Frame(container, style="Dark.TFrame", height=1)
        separator.pack(fill="x", pady=(0, 15))
        separator.configure(relief="solid", borderwidth=1)
        
        input_frame = ttk.Frame(container, style="Dark.TFrame")
        input_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            input_frame,
            text="Version Hash:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        version_entry_frame = ttk.Frame(input_frame, style="Dark.TFrame")
        version_entry_frame.pack(fill="x", pady=(0, 10))
        
        version_var = tk.StringVar()
        version_entry = ttk.Entry(version_entry_frame, textvariable=version_var, style="Dark.TEntry")
        version_entry.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=4)
        
        ttk.Label(
            input_frame,
            text="Install Path:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        path_frame = ttk.Frame(input_frame, style="Dark.TFrame")
        path_frame.pack(fill="x", pady=(0, 10))
        
        default_path = os.path.join(os.getenv("LOCALAPPDATA"), "Roblox", "Versions")
        path_var = tk.StringVar(value=default_path)
        path_entry = ttk.Entry(path_frame, textvariable=path_var, style="Dark.TEntry")
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=4)
        
        def browse_path():
            """Browse for install directory"""
            from tkinter import filedialog
            versions_path = os.path.join(os.getenv("LOCALAPPDATA"), "Roblox", "Versions")
            directory = filedialog.askdirectory(title="Select Install Directory", initialdir=versions_path if os.path.exists(versions_path) else None)
            if directory:
                path_var.set(directory)
        
        ttk.Button(
            path_frame,
            text="Browse",
            style="Dark.TButton",
            command=browse_path
        ).pack(side="left")
        
        progress_outer = tk.Frame(container, bg=self.BG_LIGHT, relief="solid", borderwidth=1)
        
        progress_inner = tk.Frame(progress_outer, bg=self.BG_MID, height=22)
        progress_inner.pack(fill="x", padx=1, pady=1)
        progress_inner.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_inner, bg=self.BG_LIGHT, width=0)
        progress_fill.place(x=0, y=0, relheight=1)
        
        progress_label = tk.Label(
            progress_inner,
            text="0%",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        progress_label.place(relx=0.5, rely=0.5, anchor="center")
        
        log_frame = ttk.Frame(container, style="Dark.TFrame")
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        ttk.Label(
            log_frame,
            text="Download Log:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        log_text = tk.Text(
            log_frame,
            height=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9),
            relief="solid",
            borderwidth=1,
            wrap="word",
            state="disabled"
        )
        log_text.pack(fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(log_text, command=log_text.yview, style="Dark.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        log_text.config(yscrollcommand=scrollbar.set)
        
        def update_progress(percent):
            """Update the custom progress bar"""
            try:
                progress_inner.update_idletasks()
                total_width = progress_inner.winfo_width()
                fill_width = int((percent / 100) * total_width)
                progress_fill.place(x=0, y=0, relheight=1, width=fill_width)
                
                label_x = total_width // 2
                if fill_width >= label_x:
                    progress_label.config(bg=self.BG_LIGHT, fg=self.BG_DARK)
                else:
                    progress_label.config(bg=self.BG_MID, fg=self.FG_TEXT)
                
                progress_label.config(text=f"{int(percent)}%")
                version_window.update()
            except:
                pass
        
        def log_message(msg):
            """Log message to text widget"""
            try:
                log_text.config(state="normal")
                log_text.insert(tk.END, msg + "\n")
                log_text.see(tk.END)
                log_text.config(state="disabled")
            except:
                pass
        
        def get_current_version():
            """Fetch current LIVE version"""
            fetch_btn.config(state="disabled", text="Fetching...")
            version_window.update()
            
            def do_fetch():
                try:
                    version = self.manager.get_roblox_version("LIVE")
                    if version:
                        def update_ui():
                            version_var.set(version)
                            log_message(f"✓ Fetched current version: {version}")
                            fetch_btn.config(state="normal", text="Get Latest")
                        version_window.after(0, update_ui)
                    else:
                        def show_error():
                            log_message("✗ Failed to fetch current version")
                            fetch_btn.config(state="normal", text="Get Latest")
                        version_window.after(0, show_error)
                except Exception as e:
                    def show_error():
                        log_message(f"✗ Error: {str(e)[:50]}")
                        fetch_btn.config(state="normal", text="Get Latest")
                    version_window.after(0, show_error)
            
            thread = threading.Thread(target=do_fetch, daemon=True)
            thread.start()
        
        fetch_btn = ttk.Button(
            version_entry_frame,
            text="Get Latest",
            style="Dark.TButton",
            command=get_current_version
        )
        fetch_btn.pack(side="left")
        
        download_btn = None
        
        def download_version():
            """Download and install Roblox version"""
            version = version_var.get().strip()
            if not version:
                messagebox.showwarning("Missing Version", "Please enter a version hash or click 'Get Latest'")
                return
            
            base_path = path_var.get().strip()
            if not base_path:
                messagebox.showwarning("Missing Path", "Please select an install directory")
                return
            
            if not version.startswith("version-"):
                version_hash = f"version-{version}"
            else:
                version_hash = version
            
            install_path = os.path.join(base_path, version_hash)
            
            download_btn.config(state="disabled", text="Downloading...")
            fetch_btn.config(state="disabled")
            log_text.config(state="normal")
            log_text.delete("1.0", tk.END)
            log_text.config(state="disabled")
            progress_outer.pack(fill="x", pady=(10, 0))
            progress_outer.pack_configure(before=log_frame)
            update_progress(0)
            version_window.update()
            
            def do_download():
                try:
                    package_count = [0]
                    total_packages = [1]
                    last_logged_percent = [-1]
                    
                    def progress_callback(msg):
                        if msg.startswith("DOWNLOAD_PROGRESS:"):
                            try:
                                parts = msg.split(":")
                                package_name = parts[1]
                                percent = float(parts[2])
                                size_mb = float(parts[3])
                                total_mb = float(parts[4])
                                display_msg = f"Downloading {package_name}: {percent:.0f}% ({size_mb:.1f} MB / {total_mb:.1f} MB)"
                                
                                if int(percent) % 10 == 0 and int(percent) != last_logged_percent[0]:
                                    last_logged_percent[0] = int(percent)
                                    version_window.after(0, lambda m=display_msg: log_message(m))
                                
                                version_window.after(0, lambda p=percent: update_progress(p))
                            except:
                                pass
                        elif msg.startswith("EXTRACT_START:"):
                            try:
                                package_name = msg.split(":")[1]
                                display_msg = f"Extracting {package_name}..."
                                version_window.after(0, lambda m=display_msg: log_message(m))
                                version_window.after(0, lambda: update_progress(0))
                                last_logged_percent[0] = -1
                            except:
                                pass
                        elif msg.startswith("EXTRACT_PROGRESS:"):
                            try:
                                parts = msg.split(":")
                                package_name = parts[1]
                                percent = float(parts[2])
                                
                                if int(percent) % 25 == 0 and int(percent) != last_logged_percent[0]:
                                    last_logged_percent[0] = int(percent)
                                    display_msg = f"Extracting {package_name}: {percent:.0f}%"
                                    version_window.after(0, lambda m=display_msg: log_message(m))
                                
                                version_window.after(0, lambda p=percent: update_progress(p))
                            except:
                                pass
                        elif msg.startswith("EXTRACT_COMPLETE:"):
                            try:
                                package_name = msg.split(":")[1]
                                display_msg = f"✓ Completed {package_name}"
                                version_window.after(0, lambda m=display_msg: log_message(m))
                                version_window.after(0, lambda: update_progress(100))
                                last_logged_percent[0] = -1
                            except:
                                pass
                        else:
                            version_window.after(0, lambda m=msg: log_message(m))
                    
                    success, result = self.manager.download_roblox_version(
                        version,
                        install_path,
                        "LIVE",
                        progress_callback
                    )
                    
                    def update_ui():
                        if success:
                            log_message(f"✓ Installation complete!")
                            download_btn.config(state="normal", text="Download")
                        else:
                            log_message(f"✗ {result}")
                            download_btn.config(state="normal", text="Download")
                            messagebox.showerror("Download Failed", result)
                        
                        fetch_btn.config(state="normal")
                        progress_outer.pack_forget()
                    
                    version_window.after(0, update_ui)
                    
                except Exception as e:
                    def show_error():
                        error_msg = str(e)
                        log_message(f"✗ Error: {error_msg}")
                        download_btn.config(state="normal", text="Download")
                        fetch_btn.config(state="normal")
                        progress_outer.pack_forget()
                        messagebox.showerror("Error", f"Download failed:\n{error_msg}")
                    version_window.after(0, show_error)
            
            thread = threading.Thread(target=do_download, daemon=True)
            thread.start()
        
        button_frame = ttk.Frame(container, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(15, 0))
        
        download_btn = ttk.Button(
            button_frame,
            text="Download",
            style="Dark.TButton",
            command=download_version
        )
        download_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Close",
            style="Dark.TButton",
            command=version_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
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
                self._apply_console_tags()
                self.console_text_widget.see(tk.END)
                self.console_text_widget.config(state="disabled")
            except:
                pass
    
    def _apply_console_tags(self):
        """Apply color tags to console keywords"""
        if not self.console_text_widget:
            return
        
        keywords = {
            "[SUCCESS]": "success",
            "[ERROR]": "error",
            "[INFO]": "info",
            "[WARNING]": "warning"
        }
        
        for keyword, tag in keywords.items():
            search_start = "1.0"
            while True:
                pos = self.console_text_widget.search(keyword, search_start, tk.END, nocase=False)
                if not pos:
                    break
                end_pos = f"{pos}+{len(keyword)}c"
                self.console_text_widget.tag_add(tag, pos, end_pos)
                search_start = end_pos
    
    def open_console_window(self):
        """Open the Console Output window"""
        if self.console_window and tk.Toplevel.winfo_exists(self.console_window):
            self.console_window.focus()
            return
        
        self.console_window = tk.Toplevel(self.root)
        self.apply_window_icon(self.console_window)
        self.console_window.title("Console Output")
        self.console_window.configure(bg=self.BG_DARK)
        self.console_window.minsize(500, 450)
        
        if self.settings.get("enable_topmost", False):
            self.console_window.attributes("-topmost", True)
        
        self.root.update_idletasks()
        
        saved_console = self.settings.get('console_window_geometry')
        if saved_console and saved_console.get('x') is not None and saved_console.get('y') is not None:
            width = saved_console.get('width', 700)
            height = saved_console.get('height', 500)
            x = saved_console['x']
            y = saved_console['y']
            self.console_window.geometry(f"{width}x{height}+{x}+{y}")
        else:
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
        
        self.console_text_widget.tag_configure("success", foreground="#00FF00")
        self.console_text_widget.tag_configure("error", foreground="#FF0000")
        self.console_text_widget.tag_configure("info", foreground="#0078D7")
        self.console_text_widget.tag_configure("warning", foreground="#FFD700")
        
        scrollbar = ttk.Scrollbar(text_frame, command=self.console_text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.console_text_widget.config(yscrollcommand=scrollbar.set)
        
        self.console_text_widget.config(state="normal")
        for message in self.console_output:
            self.console_text_widget.insert(tk.END, message)
        
        self._apply_console_tags()
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
        
        def on_console_close():
            """Save window geometry (position and size) before closing"""
            self.settings['console_window_geometry'] = {
                'x': self.console_window.winfo_x(),
                'y': self.console_window.winfo_y(),
                'width': self.console_window.winfo_width(),
                'height': self.console_window.winfo_height()
            }
            self.save_settings()
            self.console_text_widget = None
            self.console_window.destroy()
            self.console_window = None
        
        self.console_window.protocol("WM_DELETE_WINDOW", on_console_close)
    
    def open_favorites_window(self):
        """Open the favorites management window"""
        favorites_window = tk.Toplevel(self.root)
        self.apply_window_icon(favorites_window)
        favorites_window.title("Favorite Games")
        favorites_window.configure(bg=self.BG_DARK)
        favorites_window.resizable(False, False)
        
        self.root.update_idletasks()
        
        saved_pos = self.settings.get('favorites_window_position')
        if saved_pos and saved_pos.get('x') is not None and saved_pos.get('y') is not None:
            x = saved_pos['x']
            y = saved_pos['y']
        else:
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
            self.apply_window_icon(add_window)
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
        
        def on_favorites_close():
            """Save window position before closing"""
            self.settings['favorites_window_position'] = {
                'x': favorites_window.winfo_x(),
                'y': favorites_window.winfo_y()
            }
            self.save_settings()
            favorites_window.destroy()
        
        favorites_window.protocol("WM_DELETE_WINDOW", on_favorites_close)
        
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
    
    def start_rename_monitoring(self):
        """Start monitoring and renaming Roblox windows"""
        if self.rename_thread and self.rename_thread.is_alive():
            return
        
        self.rename_stop_event.clear()
        self.renamed_pids.clear()
        self.rename_thread = threading.Thread(target=self._rename_monitoring_worker, daemon=True)
        self.rename_thread.start()
        print("[INFO] Rename monitoring started")
    
    def stop_rename_monitoring(self):
        """Stop rename monitoring"""
        if self.rename_thread:
            self.rename_stop_event.set()
            self.rename_thread = None
            self.renamed_pids.clear()
            print("[INFO] Rename monitoring stopped")
    
    def _rename_monitoring_worker(self):
        """Monitor for new Roblox PIDs and renames them"""
        import psutil
        
        while not self.rename_stop_event.is_set():
            try:
                current_pids = set()
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                            pid = proc.info['pid']
                            if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                                current_pids.add(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                new_pids = current_pids - self.renamed_pids
                
                for pid in new_pids:
                    if self.rename_stop_event.is_set():
                        break
                    
                    user_id, _ = self._get_user_id_from_pid(pid)
                    
                    if user_id:
                        username = RobloxAPI.get_username_from_user_id(user_id)
                        
                        if username:
                            self._rename_roblox_window(pid, username)
                            self.renamed_pids.add(pid)
                            print(f"[INFO] Renamed Roblox window for PID {pid} to '{username}'")
                    
                    time.sleep(0.5)
                
                self.renamed_pids = self.renamed_pids.intersection(current_pids)
                
            except Exception as e:
                print(f"[ERROR] Error in rename monitoring: {e}")
            
            time.sleep(2)
    
    def _rename_roblox_window(self, pid, username):
        """Rename a Roblox window by PID"""
        try:
            def enum_windows_callback(hwnd, pid_target):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid_target:
                    if win32gui.IsWindowVisible(hwnd):
                        current_title = win32gui.GetWindowText(hwnd)
                        if 'roblox' in current_title.lower():
                            win32gui.SetWindowText(hwnd, username)
                            return False
                return True
            
            win32gui.EnumWindows(enum_windows_callback, pid)
        except Exception as e:
            print(f"[ERROR] Failed to rename window for PID {pid}: {e}")
    
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
        if account in self.auto_rejoin_threads:
            existing_thread = self.auto_rejoin_threads[account]
            if existing_thread.is_alive():
                print(f"[Auto-Rejoin] Thread already running for {account}")
                return
            else:
                print(f"[Auto-Rejoin] Cleaning up dead thread for {account}")
                del self.auto_rejoin_threads[account]
        
        if account not in self.auto_rejoin_configs:
            print(f"[Auto-Rejoin] No config found for {account}")
            return
        
        stop_event = threading.Event()
        self.auto_rejoin_stop_events[account] = stop_event
        
        thread = threading.Thread(
            target=self.auto_rejoin_worker_for_account,
            args=(account,),
            daemon=True,
            name=f"AutoRejoin-{account}"  
        )
        self.auto_rejoin_threads[account] = thread
        thread.start()
        print(f"[Auto-Rejoin] Started thread {thread.name} for {account}")
        if len(self.auto_rejoin_threads) == 1:
            self._start_global_screenshot_loop()
    
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

        if not self.auto_rejoin_threads:
            self._stop_global_screenshot_loop()

        print(f"[Auto-Rejoin] Stopped for {account}")
    
    def stop_all_auto_rejoin(self):
        """Stop all auto-rejoin threads"""
        for account in list(self.auto_rejoin_threads.keys()):
            self.stop_auto_rejoin_for_account(account)
        self._stop_global_screenshot_loop()

    def _start_global_screenshot_loop(self):
        if self._webhook_screenshot_thread and self._webhook_screenshot_thread.is_alive():
            return
        self._webhook_screenshot_thread = threading.Thread(
            target=self._global_screenshot_worker, daemon=True, name="WebhookScreenshot"
        )
        self._webhook_screenshot_thread.start()
        print("[INFO] Global hourly webhook screenshot started")

    def _stop_global_screenshot_loop(self):
        if self._webhook_screenshot_thread is None:
            return
        self._webhook_screenshot_thread = None
        print("[INFO] Global hourly webhook screenshot stopped")

    def _global_screenshot_worker(self):
        time.sleep(3600)
        while self._webhook_screenshot_thread is threading.current_thread():
            wh_cfg = self.settings.get('rejoin_webhook', {})
            wh_url = wh_cfg.get('url', '').strip()
            if wh_url and self.auto_rejoin_threads:
                active = ", ".join(
                    acc for acc, t in self.auto_rejoin_threads.items() if t.is_alive()
                )
                self._send_webhook_screenshot(wh_url, f"Hourly screenshot — active accounts: {active}")
            time.sleep(3600)
    
    def is_roblox_running(self):
        """Check if any Roblox window exists"""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Roblox")
            return hwnd != 0
        except:
            return False
    
    def is_player_in_game(self, user_id, cookie, expected_place_id):
        """Check if player is still in the same game using Presence API.
        Returns (in_game, place_id, game_id, error_msg) — error_msg is None on success."""
        try:
            presence = RobloxAPI.get_player_presence(user_id, cookie)

            if presence:
                in_game = presence.get('in_game', False)
                place_id = presence.get('place_id')

                print(f"[Auto-Rejoin] Presence check - in_game: {in_game}, place_id: {place_id}, expected: {expected_place_id}")

                if in_game:
                    try:
                        if int(place_id) == int(expected_place_id):
                            print(f"[Auto-Rejoin] Player is in correct game")
                            return True, place_id, presence.get('game_id'), None
                    except (ValueError, TypeError):
                        pass

                print(f"[Auto-Rejoin] Player NOT in game or wrong place_id")
                return False, None, None, None
            else:
                print(f"[Auto-Rejoin] Presence API returned None")
                return False, None, None, "Presence API returned None — cookie may be invalid"
        except Exception as e:
            print(f"[Auto-Rejoin] Error checking player status: {e}")
            traceback.print_exc()
            return False, None, None, f"Presence check exception: {e}"
    
    def _check_roblox_process_exists(self, account):
        """Check if the tracked Roblox process for this account still exists"""
        if account not in self.auto_rejoin_pids:
            return False
        
        pid = self.auto_rejoin_pids[account]
        try:
            result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                  capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
            return f"{pid}" in result.stdout
        except Exception as e:
            print(f"[Auto-Rejoin] Error checking process {pid}: {e}")
            return False
    
    def auto_rejoin_worker_for_account(self, account):
        """Background worker that monitors for disconnection and rejoins for a specific account."""   
        config = self.auto_rejoin_configs.get(account, {})
        stop_event = self.auto_rejoin_stop_events.get(account)
        
        if not stop_event:
            return
        
        stagger_delay = random.uniform(6.0, 9.0)
        time.sleep(stagger_delay)
        
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
        
        if 'user_id_cache' not in self.settings:
            self.settings['user_id_cache'] = {}
        
        user_id = RobloxAPI.get_user_id_from_username(
            account,
            use_cache=True,
            cache_dict=self.settings['user_id_cache']
        )
        if not user_id:
            print(f"[Auto-Rejoin] Could not get user ID for {account}")
            return
        
        try:
            self.save_settings()
        except Exception as e:
            print(f"[Auto-Rejoin] Warning: Could not save user ID cache: {e}")
        
        print(f"[Auto-Rejoin] Started monitoring {account} for game {place_id}")

        consecutive_failed_checks = 0
        max_consecutive_fails = 2

        if account in self.auto_rejoin_pids:
            print(f"[Auto-Rejoin] [{account}] Using pre-matched PID {self.auto_rejoin_pids[account]}")
        else:
            print(f"[Auto-Rejoin] [{account}] No pre-matched PID - launching game...")
            success = self._launch_and_track_pid(account, place_id, private_server, job_id)
            if not success:
                retry_count += 1
                wh_cfg_il = self.settings.get('rejoin_webhook', {})
                wh_url_il = wh_cfg_il.get('url', '').strip()
                if wh_url_il:
                    _ping_il = wh_cfg_il.get('ping_user_id', '') if wh_cfg_il.get('enable_ping') else None
                    self._send_webhook_embed(
                        wh_url_il, "Launch Failed",
                        f"**{account}** failed to launch place `{place_id}` (attempt {retry_count}/{max_retries}).",
                        15287107, ping_user_id=_ping_il or None
                    )
                if retry_count >= max_retries:
                    print(f"[Auto-Rejoin] [{account}] Max retries ({max_retries}) reached on initial launch. Stopping.")
                    return
            time.sleep(10)
        
        while not stop_event.is_set():
            try:
                wh_cfg = self.settings.get('rejoin_webhook', {})
                wh_url = wh_cfg.get('url', '').strip()

                check_presence = config.get('check_presence', True)
                disconnect_detected = False
                game_id = ''
                
                if check_presence:
                    in_game, current_place_id, game_id, pres_err = self.is_player_in_game(user_id, cookie, place_id)
                    if pres_err:
                        if wh_url:
                            _ping_pe = wh_cfg.get('ping_user_id', '') if wh_cfg.get('enable_ping') else None
                            self._send_webhook_embed(
                                wh_url, "Presence Check Error",
                                f"**{account}**\n{pres_err}",
                                16776960,
                                ping_user_id=_ping_pe or None
                            )
                    disconnect_detected = not in_game
                    
                    if disconnect_detected:
                        consecutive_failed_checks += 1
                        if consecutive_failed_checks < max_consecutive_fails:
                            print(f"[Auto-Rejoin] [{account}] Presence check failed ({consecutive_failed_checks}/{max_consecutive_fails}), will verify next check")
                            disconnect_detected = False
                            time.sleep(check_interval)
                            continue
                    else:
                        consecutive_failed_checks = 0
                else:
                    presence = RobloxAPI.get_player_presence(user_id, cookie)
                    
                    if presence:
                        in_game = presence.get('in_game', False)
                        current_place_id = presence.get('place_id')
                        game_id = presence.get('game_id', '')
                        
                        print(f"[Auto-Rejoin] [{account}] Presence check (any game mode) - in_game: {in_game}, place_id: {current_place_id}")
                        
                        if in_game:
                            print(f"[Auto-Rejoin] [{account}] Player is in a game (place_id: {current_place_id})")
                            disconnect_detected = False
                            consecutive_failed_checks = 0
                        else:
                            consecutive_failed_checks += 1
                            if consecutive_failed_checks < max_consecutive_fails:
                                print(f"[Auto-Rejoin] [{account}] Not in any game ({consecutive_failed_checks}/{max_consecutive_fails}), will verify next check")
                                disconnect_detected = False
                                time.sleep(check_interval)
                                continue
                            else:
                                print(f"[Auto-Rejoin] [{account}] Player not in any game")
                                disconnect_detected = True
                    else:
                        consecutive_failed_checks += 1
                        if consecutive_failed_checks < max_consecutive_fails:
                            print(f"[Auto-Rejoin] [{account}] Presence API failed ({consecutive_failed_checks}/{max_consecutive_fails}), will verify next check")
                            disconnect_detected = False
                            time.sleep(check_interval)
                            continue
                        else:
                            print(f"[Auto-Rejoin] [{account}] Presence API returned None")
                            disconnect_detected = True
                
                if disconnect_detected:
                    retry_count += 1
                    consecutive_failed_checks = 0
                    print(f"[Auto-Rejoin] [{account}] Disconnection detected! Rejoining... (Attempt {retry_count}/{max_retries})")

                    _ping_id = wh_cfg.get('ping_user_id', '') if wh_cfg.get('enable_ping') else None
                    if wh_url:
                        self._send_webhook_embed(
                            wh_url,
                            "Account Disconnected",
                            f"**{account}** disconnected from place `{place_id}`.\nRejoin attempt **{retry_count}/{max_retries}**.",
                            15287107,
                            ping_user_id=_ping_id or None
                        )
                    
                    if account in self.auto_rejoin_pids:
                        old_pid = self.auto_rejoin_pids[account]
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', str(old_pid)], 
                                         capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                            time.sleep(1)
                            print(f"[Auto-Rejoin] [{account}] Closed old Roblox instance (PID: {old_pid})")
                        except Exception as e:
                            print(f"[Auto-Rejoin] [{account}] Error closing instance (PID: {old_pid}): {e}")
                        del self.auto_rejoin_pids[account]
                    
                    rejoin_job_id = job_id if job_id else (game_id if game_id else '')
                    success = self._launch_and_track_pid(account, place_id, private_server, rejoin_job_id)
                    
                    if success:
                        print(f"[Auto-Rejoin] [{account}] Rejoin attempt successful")
                        if wh_url:
                            self._send_webhook_embed(
                                wh_url,
                                "Rejoin Successful",
                                f"**{account}** has rejoined place `{place_id}`.",
                                5438822,
                                ping_user_id=_ping_id or None
                            )
                        retry_count = 0
                        time.sleep(10)
                    else:
                        if wh_url:
                            self._send_webhook_embed(
                                wh_url, "Rejoin Failed",
                                f"**{account}** failed to relaunch for place `{place_id}` (attempt {retry_count}/{max_retries}).",
                                15287107, ping_user_id=_ping_id or None
                            )
                        if retry_count >= max_retries:
                            print(f"[Auto-Rejoin] [{account}] Max retries ({max_retries}) reached. Stopping.")
                            if wh_url:
                                self._send_webhook_embed(
                                    wh_url, "Auto Rejoin Stopped",
                                    f"**{account}** reached max retries ({max_retries}). Auto-rejoin stopped.",
                                    15287107, ping_user_id=_ping_id or None
                                )
                            break
                        time.sleep(check_interval)
                else:
                    print(f"[Auto-Rejoin] [{account}] Still in game {place_id}")
                    retry_count = 0
                    time.sleep(check_interval)
                    
            except Exception as e:
                print(f"[Auto-Rejoin] [{account}] Error: {e}")
                wh_cfg_ex = self.settings.get('rejoin_webhook', {})
                wh_url_ex = wh_cfg_ex.get('url', '').strip()
                if wh_url_ex:
                    _ping_ex = wh_cfg_ex.get('ping_user_id', '') if wh_cfg_ex.get('enable_ping') else None
                    self._send_webhook_embed(
                        wh_url_ex, "Error",
                        f"**{account}**\n`{e}`",
                        15287107, ping_user_id=_ping_ex or None
                    )
                time.sleep(check_interval)
    
    def _launch_and_track_pid(self, account, place_id, private_server, job_id):
        with self.auto_rejoin_launch_lock:
            pids_before = self._get_roblox_pids()
            
            launcher_pref = self.settings.get("roblox_launcher", "default")
            success = self.manager.launch_roblox(account, place_id, private_server, launcher_pref, job_id)
            
            if not success:
                return False
            
            print(f"[Auto-Rejoin] [{account}] Game launched successfully")
            
            time.sleep(5)
            
            pids_after = self._get_roblox_pids()
            new_pids = pids_after - pids_before
            
            if not new_pids:
                print(f"[Auto-Rejoin] [{account}] No new Roblox processes detected")
                return False
            
            available_pids = new_pids - set(self.auto_rejoin_pids.values())
            
            if available_pids:
                new_pid = max(available_pids)
                self.auto_rejoin_pids[account] = new_pid
                print(f"[Auto-Rejoin] [{account}] Successfully tracked PID {new_pid}")
                return True
            else:
                print(f"[Auto-Rejoin] [{account}] All new PIDs are already tracked by other accounts")
                return False
    
    def _get_roblox_pids(self):
        """Get all currently running RobloxPlayerBeta.exe PIDs using psutil."""
        try:
            pids = set()
            for p in psutil.process_iter(["pid", "name"]):
                if p.info["name"] and p.info["name"].lower() == "robloxplayerbeta.exe":
                    pid = p.info["pid"]
                    if self._is_valid_roblox_game_client(pid, "robloxplayerbeta.exe"):
                        pids.add(pid)
            return pids
        except Exception as e:
            print(f"[Auto-Rejoin] Error getting Roblox PIDs: {e}")
            return set()
    
    def _is_pid_roblox_process(self, pid):
        """Check if a specific PID is still a running RobloxPlayerBeta.exe process"""
        try:
            process = psutil.Process(pid)
            return process.is_running() and process.name().lower() == "robloxplayerbeta.exe"
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception as e:
            print(f"[Auto-Rejoin] Error checking PID {pid}: {e}")
            return False
    
    def _is_valid_roblox_game_client(self, pid, process_name_lower=None):
        """Check if PID is a valid Roblox game client (process name + window title check)"""
        try:
            if process_name_lower is None:
                try:
                    process = psutil.Process(pid)
                    process_name_lower = process.name().lower()
                except:
                    return False
            
            if process_name_lower != "robloxplayerbeta.exe":
                return False
            
            has_roblox_window = [False]
            
            def enum_callback(hwnd, _):
                try:
                    _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                    if window_pid == pid:
                        window_title = win32gui.GetWindowText(hwnd)
                        if window_title and "roblox" in window_title.lower():
                            has_roblox_window[0] = True
                            return False
                except:
                    pass
                return True
            
            win32gui.EnumWindows(enum_callback, None)
            return has_roblox_window[0]
            
        except Exception as e:
            return process_name_lower == "robloxplayerbeta.exe" if process_name_lower else False
    
    def _match_pids_to_accounts(self, accounts):
        """Match all running Roblox PIDs to accounts"""
        print(f"[Auto-Rejoin] Starting global PID matching for {len(accounts)} account(s)...")
        
        if 'user_id_cache' not in self.settings:
            self.settings['user_id_cache'] = {}
        
        account_user_ids = {}
        for account in accounts:
            user_id = RobloxAPI.get_user_id_from_username(
                account,
                use_cache=True,
                cache_dict=self.settings['user_id_cache']
            )
            if user_id:
                account_user_ids[account] = str(user_id)
                print(f"[Auto-Rejoin] {account} -> User ID: {user_id}")
            else:
                print(f"[Auto-Rejoin] {account} -> Could not get user ID")
        
        try:
            self.save_settings()
        except Exception as e:
            print(f"[Auto-Rejoin] Warning: Could not save user ID cache: {e}")
        
        all_pids = self._get_roblox_pids()
        print(f"[Auto-Rejoin] Found {len(all_pids)} Roblox process(es)")
        
        if not all_pids:
            return {}
        
        used_logs = set()
        pid_user_ids = {}
        for pid in all_pids:
            if pid in self.auto_rejoin_pids.values():
                print(f"[Auto-Rejoin] PID {pid} already tracked, skipping")
                continue
            
            user_id, matched_log = self._get_user_id_from_pid(pid, used_logs)
            if user_id:
                pid_user_ids[pid] = str(user_id)
                print(f"[Auto-Rejoin] PID {pid} -> User ID: {user_id}")
            else:
                print(f"[Auto-Rejoin] PID {pid} -> Could not extract user ID")
        
        matches = {}
        for account, account_user_id in account_user_ids.items():
            if account in self.auto_rejoin_pids:
                continue
                
            for pid, pid_user_id in pid_user_ids.items():
                if account_user_id == pid_user_id:
                    matches[account] = pid
                    self.auto_rejoin_pids[account] = pid
                    print(f"[Auto-Rejoin] MATCHED: {account} (user {account_user_id}) -> PID {pid}")
                    del pid_user_ids[pid]
                    break
        
        unmatched = [acc for acc in accounts if acc not in matches and acc not in self.auto_rejoin_pids]
        if unmatched:
            print(f"[Auto-Rejoin] Unmatched accounts (will launch new): {unmatched}")
        
        return matches
    
    def _get_user_id_from_pid(self, pid, used_logs=None):
        """Get user ID from a Roblox process PID"""
        if used_logs is None:
            used_logs = set()
            
        try:
            process = psutil.Process(pid)
            if not (process.is_running() and process.name().lower() == "robloxplayerbeta.exe"):
                return None, None
            
            create_time_local = datetime.fromtimestamp(process.create_time())
            create_time_utc = datetime.fromtimestamp(process.create_time(), tz=timezone.utc).replace(tzinfo=None)
            
            logs_dir = os.path.join(os.getenv("LOCALAPPDATA"), "Roblox", "logs")
            if not os.path.exists(logs_dir):
                return None, None
            
            time_window = timedelta(seconds=10)
            matching_logs = []
            
            for filename in os.listdir(logs_dir):
                if not filename.endswith("_last.log"):
                    continue
                
                full_path = os.path.join(logs_dir, filename)
                
                if full_path in used_logs:
                    continue
                
                match = re.search(r'(\d{8}T\d{6}Z)', filename)
                if not match:
                    continue
                
                timestamp_str = match.group(1)
                try:
                    log_time = datetime.strptime(timestamp_str, "%Y%m%dT%H%M%SZ")
                    time_diff = (log_time - create_time_utc).total_seconds()
                    
                    if 0 <= time_diff <= 10:
                        matching_logs.append((time_diff, full_path, log_time))
                except ValueError:
                    continue
            
            matching_logs.sort(key=lambda x: x[0])
            
            for time_diff, log_path, log_time in matching_logs:
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(50000)
                    
                    if "userid:" in content:
                        user_id = content.split("userid:")[1].split(",")[0].strip()
                        if user_id.isdigit():
                            used_logs.add(log_path)
                            return user_id, log_path
                except Exception as e:
                    print(f"[Auto-Rejoin] Error reading log {log_path}: {e}")
                    continue
            
            return None, None
            
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None, None
        except Exception as e:
            print(f"[Auto-Rejoin] Error getting user ID for PID {pid}: {e}")
            return None, None
      
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
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            KEYEVENTF_KEYUP = 0x0002
            SW_RESTORE = 9
            SW_MINIMIZE = 6
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            MOUSEEVENTF_RIGHTDOWN = 0x0008
            MOUSEEVENTF_RIGHTUP = 0x0010
            
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
            
            roblox_pids = set()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                        pid = proc.info['pid']
                        if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                            roblox_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if not roblox_pids:
                return
            
            roblox_windows = []
            
            def enum_windows_callback(hwnd, lParam):
                if user32.IsWindowVisible(hwnd):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in roblox_pids:
                        roblox_windows.append((hwnd, pid.value))
                return True
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
            
            if not roblox_windows:
                return
            
            original_hwnd = user32.GetForegroundWindow()
            current_thread_id = kernel32.GetCurrentThreadId()
            
            for hwnd, pid in roblox_windows:
                try:
                    was_minimized = user32.IsIconic(hwnd)
                    if was_minimized:
                        user32.ShowWindow(hwnd, SW_RESTORE)
                        time.sleep(0.05)
                    
                    target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)
                    user32.AttachThreadInput(current_thread_id, target_thread_id, True)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(current_thread_id, target_thread_id, False)
                    time.sleep(0.1)
                    
                    if is_mouse:
                        if action.upper() == 'LMB':
                            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            time.sleep(0.05)
                            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        elif action.upper() == 'RMB':
                            user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                            time.sleep(0.05)
                            user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                        print(f"[Anti-AFK] Sent {action} to PID {pid}")
                    else:
                        scan_code = user32.MapVirtualKeyW(vk_code, 0)
                        user32.keybd_event(vk_code, scan_code, 0, 0)
                        time.sleep(0.05)
                        user32.keybd_event(vk_code, scan_code, KEYEVENTF_KEYUP, 0)
                        print(f"[Anti-AFK] Sent '{action}' to PID {pid}")
                    
                    if was_minimized:
                        user32.ShowWindow(hwnd, SW_MINIMIZE)
                    
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"[Anti-AFK] Error on PID {pid}: {e}")
            
            if original_hwnd:
                try:
                    prev_thread_id = user32.GetWindowThreadProcessId(original_hwnd, None)
                    user32.AttachThreadInput(current_thread_id, prev_thread_id, True)
                    user32.BringWindowToTop(original_hwnd)
                    user32.SetForegroundWindow(original_hwnd)
                    user32.AttachThreadInput(current_thread_id, prev_thread_id, False)
                except:
                    pass
            
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
            
            roblox_pids = set()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                        pid = proc.info['pid']
                        if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                            roblox_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if not roblox_pids:
                print("[Anti-AFK] No RobloxPlayerBeta.exe processes found")
                return
            
            def enum_windows_callback(hwnd, lParam):
                if user32.IsWindowVisible(hwnd):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in roblox_pids:
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
    
    def apply_and_lock_roblox_settings(self):
        """Apply local Roblox settings and lock file"""
        try:
            import xml.etree.ElementTree as ET
            
            local_settings_path = os.path.join(self.data_folder, "roblox_settings.xml")
            roblox_settings_path = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Roblox",
                "GlobalBasicSettings_13.xml"
            )
            
            if not os.path.exists(local_settings_path):
                if os.path.exists(roblox_settings_path):
                    shutil.copy2(roblox_settings_path, local_settings_path)
                    print(f"[INFO] Created local Roblox settings file")
                else:
                    print(f"[WARNING] Roblox settings file not found, skipping auto-apply")
                    return
            
            try:
                os.chmod(roblox_settings_path, stat.S_IWRITE | stat.S_IREAD)
            except:
                pass
            
            shutil.copy2(local_settings_path, roblox_settings_path)
            print(f"[INFO] Applied local settings to Roblox")
            
            os.chmod(roblox_settings_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            print(f"[INFO] Locked Roblox settings to read-only")
            
        except Exception as e:
            print(f"[ERROR] Failed to apply and lock Roblox settings: {e}")
    
    def open_roblox_settings_window(self):
        """Open Roblox Settings window to view/edit GlobalBasicSettings_13.xml"""
        import xml.etree.ElementTree as ET
        
        settings_window = tk.Toplevel(self.root)
        self.apply_window_icon(settings_window)
        settings_window.title("Roblox Settings")
        settings_window.geometry("500x400")
        settings_window.configure(bg=self.BG_DARK)
        settings_window.resizable(False, False)
        settings_window.minsize(600, 400)
        
        if self.settings.get("enable_topmost", False):
            settings_window.attributes("-topmost", True)
        
        settings_window.transient(self.root)
        
        roblox_settings_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Roblox",
            "GlobalBasicSettings_13.xml"
        )
        
        local_settings_path = os.path.join(self.data_folder, "roblox_settings.xml")
        
        settings_data = {}
        xml_tree = None
        
        def ensure_local_settings_file():
            """Create local settings file if it doesn't exist by copying from Roblox"""
            if not os.path.exists(local_settings_path):
                if os.path.exists(roblox_settings_path):
                    try:
                        shutil.copy2(roblox_settings_path, local_settings_path)
                        print(f"[INFO] Created local Roblox settings file: {local_settings_path}")
                    except Exception as e:
                        print(f"[ERROR] Failed to create local settings file: {e}")
        
        def parse_settings():
            """Parse the local XML settings file"""
            nonlocal settings_data, xml_tree
            settings_data.clear()
            
            ensure_local_settings_file()
            
            if not os.path.exists(local_settings_path):
                return False
            
            try:
                xml_tree = ET.parse(local_settings_path)
                root = xml_tree.getroot()
                
                properties = root.find(".//Properties")
                if properties is None:
                    return False
                
                for child in properties:
                    tag = child.tag
                    name = child.get("name", "")
                    
                    if name:
                        if tag == "Vector2":
                            x_elem = child.find("X")
                            y_elem = child.find("Y")
                            value = f"{x_elem.text if x_elem is not None else '0'}, {y_elem.text if y_elem is not None else '0'}"
                        else:
                            value = child.text if child.text else ""
                        
                        settings_data[name] = {
                            "type": tag,
                            "value": value,
                            "element": child
                        }
                
                return True
            except Exception as e:
                print(f"[ERROR] Failed to parse settings: {e}")
                return False
        
        def refresh_list(filter_text=""):
            """Refresh the settings list, optionally filtering by search text"""
            settings_list.delete(0, tk.END)
            
            for name, data in sorted(settings_data.items()):
                if filter_text.lower() in name.lower() or filter_text.lower() in str(data["value"]).lower():
                    display = f"{name}: {data['value']}"
                    if len(display) > 60:
                        display = display[:57] + "..."
                    settings_list.insert(tk.END, display)
        
        def on_search(*args):
            """Filter list based on search input"""
            refresh_list(search_var.get())
        
        def on_select(event):
            """Handle list selection"""
            selection = settings_list.curselection()
            if not selection:
                return
            
            selected_text = settings_list.get(selection[0])
            selected_name = selected_text.split(":")[0]
            
            if selected_name in settings_data:
                data = settings_data[selected_name]
                selected_name_label.config(text=f"Selected: {selected_name}")
                type_label.config(text=f"Type: {data['type']}")
                value_entry.delete(0, tk.END)
                value_entry.insert(0, data["value"])
        
        def set_value():
            """Set value locally (in memory)"""
            selection = settings_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a setting first.")
                return
            
            selected_text = settings_list.get(selection[0])
            selected_name = selected_text.split(":")[0]
            new_value = value_entry.get()
            
            if selected_name in settings_data:
                data = settings_data[selected_name]
                element = data["element"]
                
                if data["type"] == "Vector2":
                    parts = new_value.split(",")
                    if len(parts) == 2:
                        x_elem = element.find("X")
                        y_elem = element.find("Y")
                        if x_elem is not None:
                            x_elem.text = parts[0].strip()
                        if y_elem is not None:
                            y_elem.text = parts[1].strip()
                else:
                    element.text = new_value
                
                settings_data[selected_name]["value"] = new_value
                save_settings_to_local()
                refresh_list(search_var.get())
                messagebox.showinfo("Set", f"Value for '{selected_name}' set and saved to local file.")
        
        def refresh_settings():
            """Reload settings from local XML file"""
            if parse_settings():
                refresh_list(search_var.get())
                messagebox.showinfo("Refreshed", "Settings reloaded from local file.")
            else:
                messagebox.showerror("Error", f"Could not load settings from:\n{local_settings_path}")
        
        def save_settings_to_local():
            """Save settings to local XML file"""
            nonlocal xml_tree
            if xml_tree is None:
                messagebox.showerror("Error", "No settings loaded to save.")
                return False
            
            try:
                xml_tree.write(local_settings_path, encoding="utf-8", xml_declaration=True)
                print(f"[INFO] Settings saved to local file: {local_settings_path}")
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings: {e}")
                return False
        
        def apply_settings_to_roblox():
            """Apply local settings to Roblox's GlobalBasicSettings_13.xml"""
            if not os.path.exists(local_settings_path):
                messagebox.showerror("Error", "No local settings file found.")
                return False
            
            try:
                try:
                    os.chmod(roblox_settings_path, stat.S_IWRITE | stat.S_IREAD)
                except:
                    pass
                
                shutil.copy2(local_settings_path, roblox_settings_path)
                print(f"[INFO] Applied settings to Roblox: {roblox_settings_path}")
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Failed to apply settings: {e}")
                return False
        
        def lock_roblox_settings():
            """Lock Roblox settings file to read-only"""
            if not os.path.exists(roblox_settings_path):
                print(f"[WARNING] Roblox settings file not found: {roblox_settings_path}")
                return False
            
            try:
                os.chmod(roblox_settings_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
                print(f"[INFO] Locked Roblox settings to read-only")
                return True
            except Exception as e:
                print(f"[ERROR] Failed to lock settings: {e}")
                return False
        
        def unlock_roblox_settings():
            """Unlock Roblox settings file"""
            if not os.path.exists(roblox_settings_path):
                print(f"[WARNING] Roblox settings file not found: {roblox_settings_path}")
                return False
            
            try:
                os.chmod(roblox_settings_path, stat.S_IWRITE | stat.S_IREAD)
                print(f"[INFO] Unlocked Roblox settings (writable)")
                return True
            except Exception as e:
                print(f"[ERROR] Failed to unlock settings: {e}")
                return False
        
        def toggle_lock_settings():
            """Handle Lock Settings checkbox toggle"""
            enabled = lock_settings_var.get()
            self.settings["lock_roblox_settings"] = enabled
            self.save_settings()
            
            if enabled:
                if save_settings_to_local():
                    if apply_settings_to_roblox():
                        if lock_roblox_settings():
                            messagebox.showinfo("Locked", "Settings applied and locked to read-only!")
                        else:
                            messagebox.showwarning("Warning", "Settings applied but failed to lock.")
            else:
                if unlock_roblox_settings():
                    messagebox.showinfo("Unlocked", "Roblox settings file is now writable!")
        
        main_frame = ttk.Frame(settings_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        lock_settings_var = tk.BooleanVar(value=self.settings.get("lock_roblox_settings", False))
        
        search_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="Search:", style="Dark.TLabel").pack(side="left", padx=(0, 5))
        
        search_var = tk.StringVar()
        search_var.trace("w", on_search)
        search_entry = ttk.Entry(search_frame, textvariable=search_var, style="Dark.TEntry")
        search_entry.pack(side="left", fill="x", expand=True)
        
        content_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        content_frame.pack(fill="both", expand=True)
        
        list_frame = ttk.Frame(content_frame, style="Dark.TFrame")
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ttk.Label(list_frame, text="Roblox Settings", style="Dark.TLabel", 
                  font=(self.FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        list_container = ttk.Frame(list_frame, style="Dark.TFrame")
        list_container.pack(fill="both", expand=True)
        
        settings_list = tk.Listbox(
            list_container,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white",
            font=(self.FONT_FAMILY, 9),
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightcolor=self.BG_LIGHT,
            highlightbackground=self.BG_LIGHT,
            exportselection=False
        )
        settings_list.pack(side="left", fill="both", expand=True)
        settings_list.bind("<<ListboxSelect>>", on_select)
        
        list_scrollbar = ttk.Scrollbar(list_container, command=settings_list.yview)
        list_scrollbar.pack(side="right", fill="y")
        settings_list.config(yscrollcommand=list_scrollbar.set)
        
        edit_frame = ttk.Frame(content_frame, style="Dark.TFrame", width=200)
        edit_frame.pack(side="right", fill="y", padx=(10, 0))
        edit_frame.pack_propagate(False)
        
        ttk.Label(edit_frame, text="Edit Setting", style="Dark.TLabel",
                  font=(self.FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(0, 10))
        
        selected_name_label = ttk.Label(edit_frame, text="Selected: (none)", style="Dark.TLabel",
                                         font=(self.FONT_FAMILY, 9))
        selected_name_label.pack(anchor="w", pady=(0, 5))
        
        type_label = ttk.Label(edit_frame, text="Type: -", style="Dark.TLabel",
                               font=(self.FONT_FAMILY, 9))
        type_label.pack(anchor="w", pady=(0, 10))
        
        ttk.Label(edit_frame, text="Set Value:", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        value_entry = ttk.Entry(edit_frame, style="Dark.TEntry")
        value_entry.pack(fill="x", pady=(0, 10))
        
        ttk.Button(edit_frame, text="Set", style="Dark.TButton", command=set_value).pack(fill="x", pady=(0, 5))
        ttk.Button(edit_frame, text="Refresh", style="Dark.TButton", command=refresh_settings).pack(fill="x", pady=(0, 5))
        ttk.Button(edit_frame, text="Apply to Roblox", style="Dark.TButton", command=lambda: apply_settings_to_roblox() and messagebox.showinfo("Applied", "Settings applied to Roblox!")).pack(fill="x", pady=(0, 5))
        
        ttk.Checkbutton(
            edit_frame,
            text="Lock settings (auto-apply)",
            variable=lock_settings_var,
            command=toggle_lock_settings,
            style="Dark.TCheckbutton"
        ).pack(anchor="w", pady=(10, 0))

        if parse_settings():
            refresh_list()
        else:
            settings_list.insert(tk.END, "Could not load settings file.")
            settings_list.insert(tk.END, "Make sure Roblox has been run at least once.")