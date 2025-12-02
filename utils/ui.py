"""
UI Module for Roblox Account Manager
Contains the main AccountManagerUI class
"""

import os
import json
import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import threading
import msvcrt
import ctypes
import webbrowser
from io import StringIO
from datetime import datetime


class AccountManagerUI:
    def __init__(self, root, manager):
        self.root = root
        self.manager = manager
        self.APP_VERSION = "2.3.0"
        self._game_name_after_id = None
        
        self.console_output = []
        self.console_window = None
        self.console_text_widget = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
        sys.stdout = self
        sys.stderr = self
        
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass
        
        self.root.title("Roblox Account Manager - Made by evanovar")
        self.root.geometry("450x520")
        self.root.configure(bg="#2b2b2b")
        self.root.resizable(False, False)
        
        self.data_folder = "AccountManagerData"
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
        
        self.settings_file = os.path.join(self.data_folder, "ui_settings.json")
        self.load_settings()
        
        self.multi_roblox_handle = None

        self.BG_DARK = "#2b2b2b"
        self.BG_MID = "#3a3a3a"
        self.BG_LIGHT = "#4b4b4b"
        self.FG_TEXT = "white"
        self.FG_ACCENT = "#0078D7"

        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        style.configure("Dark.TButton", background=self.BG_MID, foreground=self.FG_TEXT, font=("Segoe UI", 9))
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
            
        status_label = tk.Label(
            header_frame,
            text=encryption_status,
            bg=self.BG_DARK,
            fg=encryption_color,
            font=("Segoe UI", 8, "bold")
        )
        status_label.pack(side="right", padx=(5, 0))

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
        
        # Drag and drop state
        self.drag_data = {"item": None, "index": None}
        
        # Bind drag and drop events
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

        ttk.Button(right_frame, text="Join Place ID", style="Dark.TButton", command=self.launch_game).pack(fill="x", pady=(0, 10))
        
        ttk.Label(right_frame, text="Recent games", style="Dark.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))
        
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
        
        ttk.Button(bottom_frame, text="Remove", style="Dark.TButton", command=self.remove_account).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(bottom_frame, text="Launch Roblox Home", style="Dark.TButton", command=self.launch_home).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(bottom_frame, text="Settings", style="Dark.TButton", command=self.open_settings).pack(side="left", fill="x", expand=True, padx=(2, 0))
        
        self.root.bind("<Button-1>", self.hide_dropdown_on_click_outside)
        self.root.bind("<Configure>", self.on_root_configure)

        self.refresh_accounts()
        self.refresh_game_list()
        self.update_game_name()
        
        # Check for updates in background
        threading.Thread(target=self.check_for_updates, daemon=True).start()

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
                    "enable_topmost": False,
                    "enable_multi_roblox": False,
                    "confirm_before_launch": False,
                    "max_recent_games": 10,
                    "enable_multi_select": False
                }
        except:
            self.settings = {
                "last_place_id": "",
                "last_private_server": "",
                "game_list": [],
                "enable_topmost": False,
                "enable_multi_roblox": False,
                "confirm_before_launch": False,
                "max_recent_games": 10,
                "enable_multi_select": False
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
                
                current_parts = tuple(map(int, self.APP_VERSION.split(".")))
                latest_parts = tuple(map(int, latest_version.split(".")))
                
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


    def save_settings(self):
        """Save UI settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

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
                from classes.roblox_api import RobloxAPI
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
        """Start dragging an account"""
        widget = event.widget
        index = widget.nearest(event.y)
        if index >= 0:
            self.drag_data["index"] = index
            self.drag_data["item"] = widget.get(index)
            widget.selection_clear(0, tk.END)
            widget.selection_set(index)
    
    def on_drag_motion(self, event):
        """Handle drag motion - highlight drop position"""
        widget = event.widget
        index = widget.nearest(event.y)
        if index >= 0 and self.drag_data["index"] is not None:
            widget.selection_clear(0, tk.END)
            widget.selection_set(index)
    
    def on_drag_release(self, event):
        """Release drag and reorder accounts"""
        if self.drag_data["index"] is None:
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
            
            widget.selection_clear(0, tk.END)
            widget.selection_set(drop_index)
        
        self.drag_data = {"item": None, "index": None}
    
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
            success_count = 0
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, "", ""):
                        success_count += 1
                except Exception as e:
                    print(f"Failed to launch Roblox home for {uname}: {e}")
            
            def on_done():
                if success_count > 0:
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
            from classes.roblox_api import RobloxAPI
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
            success_count = 0
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, pid, psid):
                        success_count += 1
                except Exception as e:
                    print(f"Failed to launch game for {uname}: {e}")

            def on_done():
                if success_count > 0:
                    from classes.roblox_api import RobloxAPI
                    gname = RobloxAPI.get_game_name(pid)
                    if gname:
                        self.add_game_to_list(pid, gname, psid)
                    else:
                        self.add_game_to_list(pid, f"Place {pid}", psid)
                    if len(selected_usernames) == 1:
                        messagebox.showinfo("Success", "Roblox is launching! Check your desktop.")
                    else:
                        messagebox.showinfo("Success", f"Roblox is launching for {success_count} account(s)! Check your desktop.")
                else:
                    messagebox.showerror("Error", "Failed to launch Roblox.")

            self.root.after(0, on_done)

        threading.Thread(target=worker, args=(usernames, game_id, private_server), daemon=True).start()

    def enable_multi_roblox(self):
        """Enable Multi Roblox + 773 fix"""
        # hello programmers! I know you're reading this code, because you want to know how did I implement this feature in Python. (and most importantly, the 773 fix)
        # because of that, I'll leave some comments here to help you understand.
        import subprocess
        import win32event
        import win32api
        
        if self.multi_roblox_handle is not None:
            self.disable_multi_roblox()
        
        # first, we check if roblox is running, this is very important.
        # if roblox is running, we cannot enable multi roblox, because the mutex is already created by the running instance.
        # so we ask the user for permission to close all roblox processes.
        try:
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq RobloxPlayerBeta.exe'], 
                                  capture_output=True, text=True, encoding='utf-8', errors='replace') # checks running processes
            
            if result.stdout and 'RobloxPlayerBeta.exe' in result.stdout:
                response = messagebox.askquestion( # ask user for permission
                    "Roblox Already Running",
                    "A Roblox instance is already running.\n\n"
                    "To use Multi Roblox, you need to close all Roblox instances first.\n\n"
                    "Do you want to close all Roblox instances now?",
                    icon='warning'
                )
                
                if response == 'yes':
                    subprocess.run(['taskkill', '/F', '/IM', 'RobloxPlayerBeta.exe'], 
                                 capture_output=True, text=True, encoding='utf-8', errors='replace') # closes roblox
                    messagebox.showinfo("Success", "All Roblox instances have been closed.")
                else:
                    return False
            
            # then here's the magic:
            # to enable multi roblox, we create the mutex before roblox creates it.
            # this means, when roblox starts, it cannot be created by roblox again.
            # thus, allowing multiple instances to run. Simple, right? (doesn't fix 773 yet)
            mutex = win32event.CreateMutex(None, True, "ROBLOX_singletonEvent")
            print("[INFO] Multi Roblox activated.")
            
            # check if mutex already existed (GetLastError returns ERROR_ALREADY_EXISTS = 183)
            if win32api.GetLastError() == 183:
                print("[WARNING] Mutex already exists. Taking ownership...")
            
            # now let's get over on the 773 fix part
            # first, we need to find the RobloxCookies.dat file
            cookies_path = os.path.join(
                os.getenv('LOCALAPPDATA'),
                r'Roblox\LocalStorage\RobloxCookies.dat'
            )
            
            cookie_file = None
            if os.path.exists(cookies_path):
                try:
                    # to actually apply the 773 fix, we need to lock the cookies file
                    # this prevents roblox from accessing it, which causes error 773 to not appear
                    # and there, you have it, multi roblox + 773 fix!
                    cookie_file = open(cookies_path, 'r+b')
                    msvcrt.locking(cookie_file.fileno(), msvcrt.LK_NBLCK, os.path.getsize(cookies_path))
                    print("[INFO] Error 773 fix applied.")

                except OSError:
                    print("[ERROR] Could not lock RobloxCookies.dat. It may already be locked.")

            else:
                print("[ERROR] Cookies file not found. 773 fix skipped.")

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
                        self.multi_roblox_handle['file'].close()
                    except Exception as file_error:
                        print(f"[ERROR] Failed to close cookie file: {file_error}")
                
                if self.multi_roblox_handle.get('mutex'):
                    try:
                        import win32event
                        import win32api
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

    def open_settings(self):
        """Open the Settings window"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("300x300")
        settings_window.configure(bg=self.BG_DARK)
        settings_window.resizable(False, False)
        
        settings_window.transient(self.root)
        # Removed grab_set() to allow interaction with console window
        
        if self.settings.get("enable_topmost", False):
            settings_window.attributes("-topmost", True)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        settings_width = 300
        settings_height = 355
        
        x = main_x + (main_width - settings_width) // 2
        y = main_y + (main_height - settings_height) // 2
        
        settings_window.geometry(f"{settings_width}x{settings_height}+{x}+{y}")
        
        main_frame = ttk.Frame(settings_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        title_label = ttk.Label(
            main_frame, 
            text="Settings", 
            style="Dark.TLabel", 
            font=("Segoe UI", 14, "bold")
        )
        title_label.pack(anchor="w", pady=(0, 10))
        
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
        
        multi_roblox_check = ttk.Checkbutton(
            main_frame,
            text="Enable Multi Roblox + 773 fix",
            variable=multi_roblox_var,
            style="Dark.TCheckbutton",
            command=on_multi_roblox_toggle
        )
        multi_roblox_check.pack(anchor="w", pady=2)
        
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
            fg="white",
            buttonbackground=self.BG_LIGHT,
            font=("Segoe UI", 9),
            command=on_max_games_change
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
        close_button.pack(fill="x", pady=(3, 0)) 

        version_label = ttk.Label(
            main_frame,
            text=f"Version: {self.APP_VERSION}",
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        )
        version_label.pack(anchor="e", pady=(6, 0))
    
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