"""
UI Module for Roblox Account Manager
Contains the main AccountManagerUI class
"""

import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import threading
import msvcrt
from utils.localization import init_localization, get_localization


class AccountManagerUI:
    def __init__(self, root, manager):
        self.root = root
        self.manager = manager
        
        # Load settings first to get language preference
        self.data_folder = "AccountManagerData"
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
        
        self.settings_file = os.path.join(self.data_folder, "ui_settings.json")
        self.load_settings()
        
        # Initialize localization with saved language
        language = self.settings.get("language", "en_US")
        init_localization(language)
        self.loc = get_localization()
        
        self.root.title(self.loc.get("app_title"))
        
        # Modern color palette - Define first
        self.BG_DARK = "#1e1e2e"
        self.BG_MID = "#2a2a3e"
        self.BG_LIGHT = "#363654"
        self.BG_HOVER = "#424264"
        self.FG_TEXT = "#e0e0e0"
        self.FG_SECONDARY = "#a0a0b0"
        self.FG_ACCENT = "#7289da"
        self.FG_ACCENT_HOVER = "#5b6eae"
        self.FG_SUCCESS = "#43b581"
        self.FG_WARNING = "#faa61a"
        self.FG_ERROR = "#f04747"
        self.BORDER_COLOR = "#40405a"
        
        self.root.geometry("450x620")
        self.root.configure(bg=self.BG_DARK)
        self.root.resizable(False, False)
        
        self.multi_roblox_handle = None
        
        # Debounce timers for performance optimization
        self.save_timer = None
        self.game_name_timer = None
        self.search_timer = None

        style = ttk.Style()
        style.theme_use("clam")

        # Modern rounded button style
        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        style.configure("Dark.TButton", 
            background=self.BG_LIGHT, 
            foreground=self.FG_TEXT, 
            font=("Segoe UI", 9),
            borderwidth=0,
            focuscolor='none',
            relief="flat"
        )
        style.map("Dark.TButton", 
            background=[("active", self.BG_HOVER), ("pressed", self.FG_ACCENT)]
        )
        style.configure("Accent.TButton",
            background=self.FG_ACCENT,
            foreground="white",
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
            focuscolor='none',
            relief="flat"
        )
        style.map("Accent.TButton",
            background=[("active", self.FG_ACCENT_HOVER), ("pressed", "#4a5a8e")]
        )
        style.configure("Dark.TEntry", 
            fieldbackground=self.BG_MID, 
            background=self.BG_MID, 
            foreground=self.FG_TEXT,
            bordercolor=self.BORDER_COLOR,
            lightcolor=self.BORDER_COLOR,
            darkcolor=self.BORDER_COLOR,
            insertcolor=self.FG_TEXT
        )

        main_frame = ttk.Frame(self.root, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        header_frame = ttk.Frame(left_frame, style="Dark.TFrame")
        header_frame.pack(fill="x", anchor="w", pady=(0, 10))
        
        self.account_count_label = ttk.Label(
            header_frame, 
            text=self.loc.get("labels.accounts", count=0), 
            style="Dark.TLabel",
            font=("Segoe UI Semibold", 11)
        )
        self.account_count_label.pack(side="left")
        
        encryption_status = ""
        encryption_color = self.FG_TEXT
        if self.manager.encryption_config.is_encryption_enabled():
            method = self.manager.encryption_config.get_encryption_method()
            if method == 'hardware':
                encryption_status = self.loc.get("encryption_status.hardware")
                encryption_color = self.FG_SUCCESS
            elif method == 'password':
                encryption_status = self.loc.get("encryption_status.password")
                encryption_color = "#87CEEB"
        else:
            encryption_status = self.loc.get("encryption_status.not_encrypted")
            encryption_color = self.FG_WARNING
            
        status_label = tk.Label(
            header_frame,
            text=encryption_status,
            bg=self.BG_DARK,
            fg=encryption_color,
            font=("Segoe UI", 8, "bold")
        )
        status_label.pack(side="right", padx=(5, 0))
        
        # Search box for filtering accounts
        search_frame = ttk.Frame(left_frame, style="Dark.TFrame")
        search_frame.pack(fill="x", pady=(0, 8))
        
        search_container = tk.Frame(search_frame, bg=self.BG_MID, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        search_container.pack(fill="x")
        
        ttk.Label(search_container, text="🔍", style="Dark.TLabel", font=("Segoe UI", 10), background=self.BG_MID).pack(side="left", padx=(8, 5))
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_change)
        
        self.search_entry = tk.Entry(
            search_container,
            textvariable=self.search_var,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Segoe UI", 9),
            border=0,
            insertbackground=self.FG_ACCENT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white"
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=6)
        
        # Clear search button with modern style
        clear_btn = tk.Button(
            search_container,
            text="✕",
            bg=self.BG_MID,
            fg=self.FG_SECONDARY,
            activebackground=self.BG_HOVER,
            activeforeground=self.FG_ERROR,
            font=("Segoe UI", 9, "bold"),
            border=0,
            cursor="hand2",
            command=self.clear_search,
            pady=2,
            padx=8
        )
        clear_btn.pack(side="right")

        list_frame = ttk.Frame(left_frame, style="Dark.TFrame")
        list_frame.pack(fill="both", expand=True)

        # Modern listbox with custom styling
        self.account_list = tk.Listbox(
            list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white",
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR,
            highlightcolor=self.FG_ACCENT,
            border=0,
            font=("Segoe UI", 10),
            width=20,
            activestyle='none'
        )
        self.account_list.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, command=self.account_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.account_list.config(yscrollcommand=scrollbar.set)

        right_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        right_frame.pack(side="right", fill="y")
        
        self.game_name_label = ttk.Label(
            right_frame, 
            text="", 
            style="Dark.TLabel", 
            font=("Segoe UI", 9),
            foreground=self.FG_SECONDARY
        )
        self.game_name_label.pack(anchor="w", pady=(0, 5))
        
        ttk.Label(
            right_frame, 
            text=self.loc.get("labels.place_id"), 
            style="Dark.TLabel", 
            font=("Segoe UI Semibold", 9)
        ).pack(anchor="w")
        
        # Modern entry with border
        place_container = tk.Frame(right_frame, bg=self.BG_MID, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        place_container.pack(fill="x", pady=(2, 8))
        
        self.place_entry = tk.Entry(
            place_container,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Segoe UI", 9),
            border=0,
            insertbackground=self.FG_ACCENT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white"
        )
        self.place_entry.pack(fill="x", padx=8, pady=6)
        self.place_entry.insert(0, self.settings.get("last_place_id", ""))
        self.place_entry.bind("<KeyRelease>", self.on_place_id_change)

        ttk.Label(
            right_frame, 
            text=self.loc.get("labels.private_server"), 
            style="Dark.TLabel", 
            font=("Segoe UI Semibold", 9)
        ).pack(anchor="w")
        
        server_container = tk.Frame(right_frame, bg=self.BG_MID, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        server_container.pack(fill="x", pady=(2, 8))
        
        self.private_server_entry = tk.Entry(
            server_container,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Segoe UI", 9),
            border=0,
            insertbackground=self.FG_ACCENT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white"
        )
        self.private_server_entry.pack(fill="x", padx=8, pady=6)
        self.private_server_entry.insert(0, self.settings.get("last_private_server", ""))
        self.private_server_entry.bind("<KeyRelease>", self.on_private_server_change)

        ttk.Button(right_frame, text=self.loc.get("buttons.join_game"), style="Accent.TButton", command=self.launch_game).pack(fill="x", pady=(0, 12))
        
        ttk.Label(
            right_frame, 
            text=self.loc.get("labels.recent_games"), 
            style="Dark.TLabel", 
            font=("Segoe UI Semibold", 9)
        ).pack(anchor="w", pady=(12, 5))
        
        game_list_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        game_list_frame.pack(fill="both", expand=True)
        
        self.game_list = tk.Listbox(
            game_list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white",
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR,
            highlightcolor=self.FG_ACCENT,
            border=0,
            font=("Segoe UI", 9),
            height=5,
            activestyle='none'
        )
        self.game_list.pack(side="left", fill="both", expand=True)
        self.game_list.bind("<<ListboxSelect>>", self.on_game_select)
        
        game_scrollbar = ttk.Scrollbar(game_list_frame, command=self.game_list.yview)
        game_scrollbar.pack(side="right", fill="y")
        self.game_list.config(yscrollcommand=game_scrollbar.set)
        
        ttk.Button(right_frame, text=self.loc.get("buttons.delete_selected"), style="Dark.TButton", command=self.delete_game_from_list).pack(fill="x", pady=(5, 0))

        ttk.Label(
            right_frame, 
            text=self.loc.get("labels.quick_actions"), 
            style="Dark.TLabel",
            font=("Segoe UI Semibold", 9)
        ).pack(anchor="w", pady=(12, 5))

        action_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        action_frame.pack(fill="x")

        ttk.Button(action_frame, text=self.loc.get("buttons.validate"), style="Dark.TButton", command=self.validate_account).pack(fill="x", pady=2)
        ttk.Button(action_frame, text=self.loc.get("buttons.edit_note"), style="Dark.TButton", command=self.edit_account_note).pack(fill="x", pady=2)
        ttk.Button(action_frame, text=self.loc.get("buttons.copy_cookie"), style="Dark.TButton", command=self.copy_account_cookie).pack(fill="x", pady=2)
        ttk.Button(action_frame, text=self.loc.get("buttons.refresh"), style="Dark.TButton", command=self.refresh_accounts).pack(fill="x", pady=2)

        bottom_frame = ttk.Frame(self.root, style="Dark.TFrame")
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Primeira linha de botões
        top_button_frame = ttk.Frame(bottom_frame, style="Dark.TFrame")
        top_button_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Button(top_button_frame, text=self.loc.get("buttons.add_account"), style="Accent.TButton", command=self.add_account).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(top_button_frame, text=self.loc.get("buttons.remove"), style="Dark.TButton", command=self.remove_account).pack(side="left", fill="x", expand=True, padx=(2, 0))
        
        # Segunda linha de botões
        bottom_button_frame = ttk.Frame(bottom_frame, style="Dark.TFrame")
        bottom_button_frame.pack(fill="x")
        
        ttk.Button(bottom_button_frame, text=self.loc.get("buttons.launch_browser"), style="Dark.TButton", command=self.launch_home).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(bottom_button_frame, text=self.loc.get("buttons.settings"), style="Dark.TButton", command=self.open_settings).pack(side="left", fill="x", expand=True, padx=(2, 0))

        self.refresh_accounts()
        self.refresh_game_list()
        self.update_game_name()

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
                    "language": "en_US"
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
                "language": "en_US"
            }
        
        if self.settings.get("enable_topmost", False):
            self.root.attributes("-topmost", True)
        
        if self.settings.get("enable_multi_roblox", False):
            self.root.after(100, self.initialize_multi_roblox)

    def save_settings(self, debounce=False):
        """Save UI settings to file with optional debouncing"""
        if debounce:
            # Cancel previous timer if exists
            if self.save_timer:
                self.root.after_cancel(self.save_timer)
            # Schedule save after 500ms of inactivity
            self.save_timer = self.root.after(500, self._do_save_settings)
        else:
            self._do_save_settings()
    
    def _do_save_settings(self):
        """Actually perform the save operation"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def on_place_id_change(self, event=None):
        """Called when place ID changes"""
        place_id = self.place_entry.get().strip()
        self.settings["last_place_id"] = place_id
        self.save_settings(debounce=True)
        
        # Debounce game name fetch to avoid excessive API calls
        if self.game_name_timer:
            self.root.after_cancel(self.game_name_timer)
        self.game_name_timer = self.root.after(800, self.update_game_name)

    def on_private_server_change(self, event=None):
        """Called when private server ID changes"""
        private_server = self.private_server_entry.get().strip()
        self.settings["last_private_server"] = private_server
        self.save_settings(debounce=True)

    def get_game_name(self, place_id):
        """Fetch game name from Roblox API"""
        if not place_id or not place_id.isdigit():
            return None
        
        try:
            place_url = f"https://apis.roblox.com/universes/v1/places/{place_id}/universe"
            place_response = requests.get(place_url, timeout=5)
            
            if place_response.status_code == 200:
                place_data = place_response.json()
                universe_id = place_data.get("universeId")
                
                if universe_id:
                    game_url = f"https://games.roblox.com/v1/games?universeIds={universe_id}"
                    game_response = requests.get(game_url, timeout=5)
                    
                    if game_response.status_code == 200:
                        game_data = game_response.json()
                        if game_data and game_data.get("data") and len(game_data["data"]) > 0:
                            return game_data["data"][0].get("name", None)
        except:
            pass
        return None

    def update_game_name(self):
        """Update the game name label"""
        place_id = self.place_entry.get().strip()
        if place_id and place_id.isdigit():
            game_name = self.get_game_name(place_id)
            if game_name:
                self.game_name_label.config(text=self.loc.get("labels.current_game", game_name=game_name))
            else:
                self.game_name_label.config(text="")
        else:
            self.game_name_label.config(text="")

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

    def refresh_accounts(self, keep_selection=False):
        """Refresh the account list with optional alphabetical sorting and filtering"""
        # Save current selection
        current_selection = None
        if keep_selection:
            sel = self.account_list.curselection()
            if sel:
                current_selection = self.get_selected_username()
        
        self.account_list.delete(0, tk.END)
        
        # Get search filter
        search_term = self.search_var.get().lower().strip()
        
        # Sort accounts alphabetically and filter by search
        sorted_accounts = sorted(self.manager.accounts.items())
        displayed_count = 0
        selection_index = None
        
        for username, data in sorted_accounts:
            note = data.get('note', '') if isinstance(data, dict) else ''
            display_text = f"{username}"
            if note:
                display_text += f" • {note}"
            
            # Filter by search term
            if search_term and search_term not in username.lower() and search_term not in note.lower():
                continue
            
            self.account_list.insert(tk.END, display_text)
            
            # Track index for re-selection
            if keep_selection and current_selection == username:
                selection_index = displayed_count
            
            displayed_count += 1
        
        # Update account count
        total = len(self.manager.accounts)
        if search_term:
            self.account_count_label.config(text=self.loc.get("labels.accounts_filtered", filtered=displayed_count, total=total))
        else:
            self.account_count_label.config(text=self.loc.get("labels.accounts", count=total))
        
        # Restore selection
        if selection_index is not None:
            self.account_list.selection_set(selection_index)
            self.account_list.see(selection_index)
    
    def get_selected_username(self):
        """Get the currently selected username"""
        selection = self.account_list.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an account first.")
            return None
        
        # Extract username from display text (before the bullet if note exists)
        display_text = self.account_list.get(selection[0])
        username = display_text.split(' • ')[0]
        return username
    
    def clear_search(self):
        """Clear the search box"""
        self.search_var.set('')
        self.search_entry.focus_set()
    
    def on_search_change(self, *args):
        """Called when search text changes"""
        # Debounce search to avoid excessive filtering
        if self.search_timer:
            self.root.after_cancel(self.search_timer)
        self.search_timer = self.root.after(300, lambda: self.refresh_accounts(keep_selection=False))

    def add_account(self):
        """Add a new account using browser automation"""
        messagebox.showinfo(self.loc.get("dialog_titles.add_account"), self.loc.get("messages.add_account_info"))
        
        def add_account_thread():
            """Thread function to add account without blocking UI"""
            try:
                success = self.manager.add_account()
                self.root.after(0, lambda: self._add_account_complete(success))
            except Exception as e:
                self.root.after(0, lambda: self._add_account_error(str(e)))
        
        thread = threading.Thread(target=add_account_thread, daemon=True)
        thread.start()
    
    def _add_account_complete(self, success):
        """Called when account addition completes (on main thread)"""
        if success:
            self.refresh_accounts(keep_selection=True)
            messagebox.showinfo(self.loc.get("dialog_titles.success"), self.loc.get("messages.add_account_success"))
        else:
            messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.add_account_error"))
    
    def _add_account_error(self, error_msg):
        """Called when account addition encounters an error (on main thread)"""
        messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.add_account_error_detail", error=error_msg))
    
    def import_cookie(self):
        """Import an account using a .ROBLOSECURITY cookie"""
        import_window = tk.Toplevel(self.root)
        import_window.title(self.loc.get("window_titles.import_cookie"))
        import_window.geometry("480x320")
        import_window.configure(bg=self.BG_DARK)
        import_window.resizable(True, True)
        import_window.minsize(400, 280)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 480) // 2
        y = main_y + (main_height - 320) // 2
        import_window.geometry(f"480x320+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            import_window.attributes("-topmost", True)
        
        import_window.transient(self.root)
        import_window.grab_set()
        
        main_frame = ttk.Frame(import_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text=self.loc.get("dialogs.import_title"),
            style="Dark.TLabel",
            font=("Segoe UI Semibold", 13)
        ).pack(anchor="w", pady=(0, 15))
        
        ttk.Label(
            main_frame, 
            text=self.loc.get("labels.cookie_label"), 
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(0, 5))
        
        cookie_frame_container = tk.Frame(main_frame, bg=self.BG_MID, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        cookie_frame_container.pack(fill="both", expand=True, pady=(0, 15))
        
        cookie_text = tk.Text(
            cookie_frame_container,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Consolas", 9),
            height=5,
            wrap="word",
            border=0,
            insertbackground=self.FG_ACCENT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white"
        )
        cookie_text.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        
        cookie_scrollbar = ttk.Scrollbar(cookie_frame_container, command=cookie_text.yview)
        cookie_scrollbar.pack(side="right", fill="y")
        cookie_text.config(yscrollcommand=cookie_scrollbar.set)
        
        def do_import():
            cookie = cookie_text.get("1.0", "end-1c").strip()
            
            if not cookie:
                messagebox.showwarning(self.loc.get("dialog_titles.missing_information"), self.loc.get("messages.missing_cookie"))
                return
            
            try:
                success, username = self.manager.import_cookie_account(cookie)
                if success:
                    self.refresh_accounts(keep_selection=True)
                    messagebox.showinfo(self.loc.get("dialog_titles.success"), self.loc.get("messages.import_success", username=username))
                    import_window.destroy()
                else:
                    messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.import_error"))
            except Exception as e:
                messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.import_error_detail", error=str(e)))
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(0, 0))
        
        ttk.Button(
            button_frame,
            text=self.loc.get("buttons.import"),
            style="Accent.TButton",
            command=do_import
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text=self.loc.get("buttons.cancel"),
            style="Dark.TButton",
            command=import_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def remove_account(self):
        """Remove the selected account"""
        username = self.get_selected_username()
        if username:
            confirm = messagebox.askyesno(self.loc.get("dialog_titles.confirm_delete"), self.loc.get("messages.delete_confirm", username=username))
            if confirm:
                self.manager.delete_account(username)
                self.refresh_accounts()
                messagebox.showinfo(self.loc.get("dialog_titles.success"), self.loc.get("messages.delete_success", username=username))

    def validate_account(self):
        """Validate the selected account"""
        username = self.get_selected_username()
        if username:
            is_valid = self.manager.validate_account(username)
            if is_valid:
                messagebox.showinfo(self.loc.get("dialog_titles.validation"), self.loc.get("messages.validate_success", username=username))
            else:
                messagebox.showwarning(self.loc.get("dialog_titles.validation"), self.loc.get("messages.validate_error", username=username))
    
    def copy_account_cookie(self):
        """Copy the selected account's cookie to clipboard"""
        username = self.get_selected_username()
        if not username:
            return
        
        cookie = self.manager.get_account_cookie(username)
        if cookie:
            self.root.clipboard_clear()
            self.root.clipboard_append(cookie)
            self.root.update()
            
            # Visual feedback
            messagebox.showinfo(self.loc.get("dialog_titles.copied"), self.loc.get("messages.cookie_copied", username=username))
        else:
            messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.cookie_error", username=username))
    
    def edit_account_note(self):
        """Edit note for the selected account"""
        username = self.get_selected_username()
        if not username:
            return
        
        current_note = self.manager.get_account_note(username)
        
        note_window = tk.Toplevel(self.root)
        note_window.title(self.loc.get("window_titles.edit_note", username=username))
        note_window.geometry("420x280")
        note_window.configure(bg=self.BG_DARK)
        note_window.resizable(True, True)
        note_window.minsize(350, 240)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 420) // 2
        y = main_y + (main_height - 280) // 2
        note_window.geometry(f"420x280+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            note_window.attributes("-topmost", True)
        
        note_window.transient(self.root)
        note_window.grab_set()
        
        main_frame = ttk.Frame(note_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text=self.loc.get("dialogs.edit_note_title"),
            style="Dark.TLabel",
            font=("Segoe UI Semibold", 13)
        ).pack(anchor="w", pady=(0, 5))
        
        ttk.Label(
            main_frame,
            text=self.loc.get("labels.account", username=username),
            style="Dark.TLabel",
            font=("Segoe UI", 9),
            foreground=self.FG_SECONDARY
        ).pack(anchor="w", pady=(0, 15))
        
        ttk.Label(
            main_frame, 
            text=self.loc.get("labels.note"), 
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(0, 5))
        
        note_container = tk.Frame(main_frame, bg=self.BG_MID, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        note_container.pack(fill="both", expand=True, pady=(0, 15))
        
        note_text = tk.Text(
            note_container,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Segoe UI", 10),
            height=4,
            wrap="word",
            border=0,
            insertbackground=self.FG_ACCENT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white"
        )
        note_text.pack(fill="both", expand=True, padx=8, pady=8)
        note_text.insert("1.0", current_note)
        note_text.focus_set()
        
        def save_note():
            new_note = note_text.get("1.0", "end-1c").strip()
            self.manager.set_account_note(username, new_note)
            self.refresh_accounts(keep_selection=True)
            messagebox.showinfo(self.loc.get("dialog_titles.success"), self.loc.get("messages.note_updated", username=username))
            note_window.destroy()
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(0, 0))
        
        ttk.Button(
            button_frame,
            text=self.loc.get("buttons.save"),
            style="Accent.TButton",
            command=save_note
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text=self.loc.get("buttons.cancel"),
            style="Dark.TButton",
            command=note_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def launch_home(self):
        """Launch Chrome to Roblox home with the selected account logged in"""
        username = self.get_selected_username()
        if not username:
            return

        try:
            success = self.manager.launch_home(username)
            if success:
                messagebox.showinfo(self.loc.get("dialog_titles.success"), self.loc.get("messages.browser_success"))
            else:
                messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.browser_error"))
        except Exception as e:
            messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.launch_error", error=str(e)))

    def launch_game(self):
        """Launch Roblox game with the selected account"""
        username = self.get_selected_username()
        if not username:
            return

        game_id = self.place_entry.get().strip()
        if not game_id:
            messagebox.showwarning(self.loc.get("dialog_titles.missing_info"), self.loc.get("messages.missing_place_id"))
            return

        if not game_id.isdigit():
            messagebox.showerror(self.loc.get("dialog_titles.invalid_input"), self.loc.get("messages.invalid_place_id"))
            return

        private_server = self.private_server_entry.get().strip()

        if self.settings.get("confirm_before_launch", False):
            game_name = self.get_game_name(game_id)
            if not game_name:
                game_name = f"Place {game_id}"
            
            confirm = messagebox.askyesno(self.loc.get("dialog_titles.confirm_launch"), self.loc.get("messages.launch_confirm", game_name=game_name))
            if not confirm:
                return

        try:
            success = self.manager.launch_roblox(username, game_id, private_server)
            if success:
                game_name = self.get_game_name(game_id)
                if game_name:
                    self.add_game_to_list(game_id, game_name, private_server)
                else:
                    self.add_game_to_list(game_id, f"Place {game_id}", private_server)
                
                messagebox.showinfo(self.loc.get("dialog_titles.success"), self.loc.get("messages.game_launched"))
            else:
                messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.browser_error"))
        except Exception as e:
            messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.launch_error", error=str(e)))

    def enable_multi_roblox(self):
        """Enable Multi Roblox + 773 fix"""
        # hello programmers! I know you're reading this code, because you want to know how did I implement this feature in Python. (and most importantly, the 773 fix)
        # because of that, I'll leave some comments here to help you understand.
        import subprocess
        import win32event
        import win32api
        
        # first, we check if roblox is running, this is very important.
        # if roblox is running, we cannot enable multi roblox, because the mutex is already created by the running instance.
        # so we ask the user for permission to close all roblox processes.
        try:
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq RobloxPlayerBeta.exe'], 
                                  capture_output=True, text=True, encoding='utf-8', errors='replace') # checks running processes
            
            if result.stdout and 'RobloxPlayerBeta.exe' in result.stdout:
                response = messagebox.askquestion( # ask user for permission
                    self.loc.get("dialog_titles.roblox_running"),
                    self.loc.get("messages.roblox_running"),
                    icon='warning'
                )
                
                if response == 'yes':
                    subprocess.run(['taskkill', '/F', '/IM', 'RobloxPlayerBeta.exe'], 
                                 capture_output=True, text=True, encoding='utf-8', errors='replace') # closes roblox
                    messagebox.showinfo(self.loc.get("dialog_titles.success"), self.loc.get("messages.roblox_closed"))
                else:
                    return False
            
            # then here's the magic:
            # to enable multi roblox, we create the mutex before roblox creates it.
            # this means, when roblox starts, it cannot be created by roblox again.
            # thus, allowing multiple instances to run. Simple, right? (doesn't fix 773 yet)
            mutex = win32event.CreateMutex(None, True, "ROBLOX_singletonEvent") 
            
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
            messagebox.showerror(self.loc.get("dialog_titles.error"), self.loc.get("messages.multi_roblox_error", error=str(e)))
            return False
    
    def disable_multi_roblox(self):
        """Disable Multi Roblox and release resources"""
        try:
            if self.multi_roblox_handle:
                if self.multi_roblox_handle.get('file'):
                    try:
                        self.multi_roblox_handle['file'].close()
                    except:
                        pass
                
                if self.multi_roblox_handle.get('mutex'):
                    try:
                        import win32event
                        win32event.ReleaseMutex(self.multi_roblox_handle['mutex'])
                    except:
                        pass
                
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
        settings_window.title(self.loc.get("window_titles.settings"))
        settings_window.geometry("340x480")
        settings_window.configure(bg=self.BG_DARK)
        settings_window.resizable(True, True)
        settings_window.minsize(320, 420)
        
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        if self.settings.get("enable_topmost", False):
            settings_window.attributes("-topmost", True)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        settings_width = 340
        settings_height = 480
        
        x = main_x + (main_width - settings_width) // 2
        y = main_y + (main_height - settings_height) // 2
        
        settings_window.geometry(f"{settings_width}x{settings_height}+{x}+{y}")
        
        main_frame = ttk.Frame(settings_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_label = ttk.Label(
            main_frame, 
            text=self.loc.get("settings.title"), 
            style="Dark.TLabel", 
            font=("Segoe UI Semibold", 14)
        )
        title_label.pack(anchor="w", pady=(0, 20))
        
        topmost_var = tk.BooleanVar(value=self.settings.get("enable_topmost", False))
        multi_roblox_var = tk.BooleanVar(value=self.settings.get("enable_multi_roblox", False))
        confirm_launch_var = tk.BooleanVar(value=self.settings.get("confirm_before_launch", False))
        
        # Custom checkbox style
        checkbox_frame_bg = self.BG_MID
        
        def create_checkbox_container(parent, var, text, command):
            container = tk.Frame(parent, bg=checkbox_frame_bg, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
            container.pack(fill="x", pady=3)
            
            check = tk.Checkbutton(
                container,
                text=text,
                variable=var,
                command=command,
                bg=checkbox_frame_bg,
                fg=self.FG_TEXT,
                activebackground=checkbox_frame_bg,
                activeforeground=self.FG_TEXT,
                selectcolor=self.BG_LIGHT,
                font=("Segoe UI", 10),
                border=0,
                highlightthickness=0,
                cursor="hand2"
            )
            check.pack(anchor="w", padx=10, pady=8)
            return container
        
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
        
        create_checkbox_container(
            main_frame,
            topmost_var,
            self.loc.get("settings.keep_on_top"),
            auto_save_setting("enable_topmost", topmost_var)
        )
        
        create_checkbox_container(
            main_frame,
            multi_roblox_var,
            self.loc.get("settings.enable_multi_roblox"),
            on_multi_roblox_toggle
        )
        
        create_checkbox_container(
            main_frame,
            confirm_launch_var,
            self.loc.get("settings.confirm_before_launch"),
            auto_save_setting("confirm_before_launch", confirm_launch_var)
        )
        
        ttk.Label(main_frame, text="", style="Dark.TLabel").pack(pady=8)
        
        # Language selector
        language_frame = tk.Frame(main_frame, bg=checkbox_frame_bg, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        language_frame.pack(fill="x", pady=3)
        
        inner_lang_frame = tk.Frame(language_frame, bg=checkbox_frame_bg)
        inner_lang_frame.pack(fill="x", padx=10, pady=8)
        
        ttk.Label(
            inner_lang_frame, 
            text=self.loc.get("settings.language"), 
            style="Dark.TLabel",
            font=("Segoe UI", 10),
            background=checkbox_frame_bg
        ).pack(side="left")
        
        # Get available languages
        available_languages = self.loc.get_available_languages()
        current_language = self.settings.get("language", "en_US")
        
        language_var = tk.StringVar(value=current_language)
        
        def on_language_change(*args):
            new_language = language_var.get()
            if new_language != self.settings.get("language"):
                self.settings["language"] = new_language
                self.save_settings()
                
                # Show restart message
                lang_name = available_languages.get(new_language, new_language)
                messagebox.showinfo(
                    self.loc.get("dialog_titles.language_changed"),
                    self.loc.get("messages.restart_required", language=lang_name)
                )
        
        language_combo = ttk.Combobox(
            inner_lang_frame,
            textvariable=language_var,
            values=list(available_languages.values()),
            state="readonly",
            width=18,
            font=("Segoe UI", 9)
        )
        
        # Map display names back to codes
        lang_code_map = {v: k for k, v in available_languages.items()}
        current_display = available_languages.get(current_language, "English")
        language_combo.set(current_display)
        
        def on_combo_select(event):
            selected_display = language_combo.get()
            selected_code = lang_code_map.get(selected_display, "en_US")
            language_var.set(selected_code)
            on_language_change()
        
        language_combo.bind("<<ComboboxSelected>>", on_combo_select)
        language_combo.pack(side="right")
        
        ttk.Label(main_frame, text="", style="Dark.TLabel").pack(pady=8)
        
        max_games_frame = tk.Frame(main_frame, bg=checkbox_frame_bg, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        max_games_frame.pack(fill="x", pady=3)
        
        inner_frame = tk.Frame(max_games_frame, bg=checkbox_frame_bg)
        inner_frame.pack(fill="x", padx=10, pady=8)
        
        ttk.Label(
            inner_frame, 
            text=self.loc.get("labels.max_recent_games"), 
            style="Dark.TLabel",
            font=("Segoe UI", 10),
            background=checkbox_frame_bg
        ).pack(side="left")
        
        max_games_var = tk.IntVar(value=self.settings.get("max_recent_games", 10))
        
        def on_max_games_change():
            new_value = max_games_var.get()
            self.settings["max_recent_games"] = new_value
            self.save_settings()
            if len(self.settings["game_list"]) > new_value:
                self.settings["game_list"] = self.settings["game_list"][:new_value]
                self.save_settings()
                self.refresh_game_list()
        
        max_games_spinner = tk.Spinbox(
            inner_frame,
            from_=5,
            to=50,
            textvariable=max_games_var,
            width=8,
            bg=self.BG_LIGHT,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_HOVER,
            font=("Segoe UI", 9),
            command=on_max_games_change,
            border=1,
            relief="solid",
            highlightthickness=0
        )
        max_games_spinner.pack(side="right")
        
        # Spacer to push buttons down
        ttk.Frame(main_frame, style="Dark.TFrame", height=15).pack(pady=5)
        
        # Button container to ensure visibility
        button_container = ttk.Frame(main_frame, style="Dark.TFrame")
        button_container.pack(fill="x", side="bottom")
        
        ttk.Button(
            button_container,
            text=self.loc.get("buttons.import_cookie"),
            style="Dark.TButton",
            command=lambda: [settings_window.destroy(), self.import_cookie()]
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            button_container,
            text=self.loc.get("buttons.close"),
            style="Dark.TButton",
            command=settings_window.destroy
        ).pack(fill="x", pady=(0, 0)) 