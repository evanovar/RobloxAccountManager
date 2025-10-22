"""
UI Module for Roblox Account Manager
Contains the main AccountManagerUI class
"""

import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import requests


class AccountManagerUI:
    def __init__(self, root, manager):
        self.root = root
        self.manager = manager
        self.root.title("Roblox Account Manager")
        self.root.geometry("450x500")
        self.root.configure(bg="#2b2b2b")
        self.root.resizable(False, False)
        
        # Settings file for UI data
        self.settings_file = "ui_settings.json"
        self.load_settings()

        # Define colors
        self.BG_DARK = "#2b2b2b"
        self.BG_MID = "#3a3a3a"
        self.BG_LIGHT = "#4b4b4b"
        self.FG_TEXT = "white"
        self.FG_ACCENT = "#0078D7"

        # Style setup
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        style.configure("Dark.TButton", background=self.BG_MID, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        style.map("Dark.TButton", background=[("active", self.BG_LIGHT)])
        style.configure("Dark.TEntry", fieldbackground=self.BG_MID, background=self.BG_MID, foreground=self.FG_TEXT)

        # Main frame
        main_frame = ttk.Frame(self.root, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Left side (accounts list)
        left_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Encryption status label
        encryption_status = ""
        if self.manager.encryption_config.is_encryption_enabled():
            method = self.manager.encryption_config.get_encryption_method()
            if method == 'hardware':
                encryption_status = " 🔒 [Hardware Encrypted]"
            elif method == 'password':
                encryption_status = " 🔐 [Password Encrypted]"
        
        ttk.Label(left_frame, text=f"Account List{encryption_status}", style="Dark.TLabel").pack(anchor="w")

        list_frame = ttk.Frame(left_frame, style="Dark.TFrame")
        list_frame.pack(fill="both", expand=True)

        self.account_list = tk.Listbox(
            list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 10),
            width=20,
        )
        self.account_list.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, command=self.account_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.account_list.config(yscrollcommand=scrollbar.set)

        # Right side (place info)
        right_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        right_frame.pack(side="right", fill="y")
        
        # Game name display (placeholder)
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
        
        # Game list section
        ttk.Label(right_frame, text="Game List", style="Dark.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))
        
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
            height=6,
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
        ttk.Button(action_frame, text="Refresh List", style="Dark.TButton", command=self.refresh_accounts).pack(fill="x", pady=2)

        # Bottom buttons
        bottom_frame = ttk.Frame(self.root, style="Dark.TFrame")
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Button(bottom_frame, text="Add Account", style="Dark.TButton", command=self.add_account).pack(side="left", expand=True, padx=5)
        ttk.Button(bottom_frame, text="Remove", style="Dark.TButton", command=self.remove_account).pack(side="left", expand=True, padx=5)
        ttk.Button(bottom_frame, text="Launch Home", style="Dark.TButton", command=self.launch_home).pack(side="left", expand=True, padx=5)
        ttk.Button(bottom_frame, text="Exit", style="Dark.TButton", command=self.root.quit).pack(side="left", expand=True, padx=5)

        # Load accounts and game list
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
                    "game_list": []
                }
        except:
            self.settings = {
                "last_place_id": "",
                "last_private_server": "",
                "game_list": []
            }

    def save_settings(self):
        """Save UI settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

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

    def get_game_name(self, place_id):
        """Fetch game name from Roblox API"""
        if not place_id or not place_id.isdigit():
            return None
        
        try:
            # First, get the universe ID from the place ID
            place_url = f"https://apis.roblox.com/universes/v1/places/{place_id}/universe"
            place_response = requests.get(place_url, timeout=5)
            
            if place_response.status_code == 200:
                place_data = place_response.json()
                universe_id = place_data.get("universeId")
                
                if universe_id:
                    # Now get the game details using universe ID
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
                self.game_name_label.config(text=f"Current: {game_name}")
            else:
                self.game_name_label.config(text="")
        else:
            self.game_name_label.config(text="")

    def add_game_to_list(self, place_id, game_name, private_server=""):
        """Add a game to the saved list (max 10)"""
        # Check if already exists with same place_id and private_server
        for game in self.settings["game_list"]:
            if game["place_id"] == place_id and game.get("private_server", "") == private_server:
                return  # Already in list
        
        # Add new game
        self.settings["game_list"].insert(0, {
            "place_id": place_id,
            "name": game_name,
            "private_server": private_server
        })
        
        # Keep only last 10
        if len(self.settings["game_list"]) > 10:
            self.settings["game_list"] = self.settings["game_list"][:10]
        
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
            
            # Load private server if it exists
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
        for username in self.manager.accounts.keys():
            self.account_list.insert(tk.END, username)

    def get_selected_username(self):
        """Get the currently selected username"""
        selection = self.account_list.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an account first.")
            return None
        return self.account_list.get(selection[0])

    def add_account(self):
        """Add a new account using browser automation"""
        try:
            messagebox.showinfo("Add Account", "Browser will open for account login.\nPlease log in and wait for the process to complete.")
            self.manager.add_account()
            self.refresh_accounts()
            messagebox.showinfo("Success", "Account added successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add account: {str(e)}")

    def remove_account(self):
        """Remove the selected account"""
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

    def launch_home(self):
        """Launch Chrome to Roblox home with the selected account logged in"""
        username = self.get_selected_username()
        if not username:
            return

        try:
            success = self.manager.launch_home(username)
            if success:
                messagebox.showinfo("Success", "Chrome launched with your account! Browser will stay open.")
            else:
                messagebox.showerror("Error", "Failed to launch Chrome.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch: {str(e)}")

    def launch_game(self):
        """Launch Roblox game with the selected account"""
        username = self.get_selected_username()
        if not username:
            return

        game_id = self.place_entry.get().strip()
        if not game_id:
            messagebox.showwarning("Missing Info", "Please enter a Place ID.")
            return

        if not game_id.isdigit():
            messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
            return

        private_server = self.private_server_entry.get().strip()

        try:
            success = self.manager.launch_roblox(username, game_id, private_server)
            if success:
                # Add to game list with private server
                game_name = self.get_game_name(game_id)
                if game_name:
                    self.add_game_to_list(game_id, game_name, private_server)
                else:
                    self.add_game_to_list(game_id, f"Place {game_id}", private_server)
                
                messagebox.showinfo("Success", "Roblox is launching! Check your desktop.")
            else:
                messagebox.showerror("Error", "Failed to launch Roblox.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch: {str(e)}")
