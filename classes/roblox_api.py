"""
Roblox API interaction utilities
Handles authentication, info, and game launching
"""

import os
import time
import random
import requests
import subprocess
from pathlib import Path
from tkinter import messagebox



class RobloxAPI:
    """Handles all Roblox API interactions"""
    
    @staticmethod
    def detect_custom_launcher():
        """Detect if Bloxstrap or Fishstrap is installed and return launcher path"""
        local_appdata = os.getenv('LOCALAPPDATA')
        if not local_appdata:
            return None, None
        
        bloxstrap_path = Path(local_appdata) / 'Bloxstrap' / 'Bloxstrap.exe'
        if bloxstrap_path.exists():
            return str(bloxstrap_path), 'Bloxstrap'
        
        fishstrap_path = Path(local_appdata) / 'Fishstrap' / 'Fishstrap.exe'
        if fishstrap_path.exists():
            return str(fishstrap_path), 'Fishstrap'
        
        return None, None
    
    @staticmethod
    def extract_private_server_code(private_server_input):
        """Extract private server code from URL or return the code directly"""
        if not private_server_input:
            return ""
        
        if private_server_input.isdigit():
            return private_server_input
        else:
            print("[ERROR] Wrong Format, Private Server ID must contain only numbers")
            messagebox.showerror(
                "Wrong Format",
                "Private Server ID must contain only numbers.\n\n"
                f"Invalid input: {private_server_input}\n\n"
                "Example format: 12345678901234567890123456789012"
            )
            return None
    
    @staticmethod
    def get_username_from_api(roblosecurity_cookie):
        """Get username using Roblox API"""
        try:
            headers = {
                'Cookie': f'.ROBLOSECURITY={roblosecurity_cookie}'
            }
            
            response = requests.get(
                'https://users.roblox.com/v1/users/authenticated',
                headers=headers,
                timeout=3
            )
            
            if response.status_code == 200:
                user_data = response.json()
                return user_data.get('name', 'Unknown')
            
        except Exception as e:
            print(f"Error getting username from API: {e}")
        
        return "Unknown"
    
    @staticmethod
    def get_game_name(place_id):
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
    
    @staticmethod
    def get_auth_ticket(roblosecurity_cookie):
        """Get authentication ticket for launching Roblox games"""
        url = "https://auth.roblox.com/v1/authentication-ticket/"
        headers = {
            "User-Agent": "Roblox/WinInet",
            "Referer": "https://www.roblox.com/develop",
            "RBX-For-Gameauth": "true",
            "Content-Type": "application/json",
            "Cookie": f".ROBLOSECURITY={roblosecurity_cookie}"
        }

        try:
            response = requests.post(url, headers=headers, timeout=5)
            if response.status_code == 403 and "x-csrf-token" in response.headers:
                csrf_token = response.headers["x-csrf-token"]
            else:
                print(f"Failed to get CSRF token, status: {response.status_code}")
                return None

            headers["X-CSRF-TOKEN"] = csrf_token
            response2 = requests.post(url, headers=headers, timeout=5)
            if response2.status_code == 200:
                auth_ticket = response2.headers.get("rbx-authentication-ticket")
                if auth_ticket:
                    return auth_ticket
                else:
                    print("Authentication ticket header missing in response.")
                    return None
            else:
                print(f"Failed to get auth ticket, status: {response2.status_code}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None
    
    @staticmethod
    def launch_roblox(username, cookie, game_id, private_server_id=""):
        """Launch Roblox game with specified account"""
        print(f"Getting authentication ticket for {username}...")
        auth_ticket = RobloxAPI.get_auth_ticket(cookie)
        
        if not auth_ticket:
            print("[ERROR] Failed to get authentication ticket")
            return False
        
        print("[SUCCESS] Got authentication ticket!")
        
        private_server_code = RobloxAPI.extract_private_server_code(private_server_id)
        
        if private_server_id and private_server_code is None:
            print("[ERROR] Invalid private server code. Launch aborted.")
            return False
        
        browser_tracker_id = random.randint(55393295400, 55393295500)
        launch_time = int(time.time() * 1000)
        
        if not game_id or game_id == "":
            url = (
                "roblox-player:1+launchmode:play+gameinfo:" + auth_ticket +
                "+launchtime:" + str(launch_time) +
                "+browsertrackerid:" + str(browser_tracker_id) +
                "+robloxLocale:en_us+gameLocale:en_us"
            )
            print(f"Launching Roblox Home...")
            print(f"Account: {username}")
            
            try:
                os.system(f'start "" "{url}"')
                print("[SUCCESS] Roblox home launched successfully!")
                return True
            except Exception as e:
                print(f"[ERROR] Failed to launch Roblox: {e}")
                return False

        url = (
            "roblox-player:1+launchmode:play+gameinfo:" + auth_ticket +
            "+launchtime:" + str(launch_time) +
            "+placelauncherurl:https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGame" +
            "&browserTrackerId=" + str(browser_tracker_id) +
            "&placeId=" + str(game_id) +
            "&isPlayTogetherGame=false"
        )

        if private_server_code:
            url += "&linkCode=" + private_server_code

        url += (
            "+browsertrackerid:" + str(browser_tracker_id) +
            "+robloxLocale:en_us+gameLocale:en_us"
        )

        print(f"Launching Roblox...")
        print(f"Account: {username}")
        print(f"Game ID: {game_id}")
        if private_server_code:
            print(f"Private Server: {private_server_code}")
        
        try:
            os.system(f'start "" "{url}"')
            print("[SUCCESS] Roblox launched successfully!")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to launch Roblox: {e}")
            return False
    
    @staticmethod
    def validate_account(username, cookie):
        """Validate if an account's cookie is still valid and show detailed token info"""
        try:
            headers = {
                'Cookie': f'.ROBLOSECURITY={cookie}'
            }
            
            response = requests.get(
                'https://users.roblox.com/v1/users/authenticated',
                headers=headers,
                timeout=3
            )
            
            is_valid = response.status_code == 200
            
            print(f"\n{'='*60}")
            print(f"ACCOUNT VALIDATION: {username}")
            print(f"{'='*60}")
            print(f"Valid: {'Yes' if is_valid else 'No'}")
            
            if cookie:
                if len(cookie) > 60:
                    token_preview = f"{cookie[:50]}...{cookie[-10:]}"
                else:
                    token_preview = cookie
                print(f"Token: {token_preview}")
                print(f"Token Length: {len(cookie)} characters")
            else:
                print("Token: (No token found)")
            
            if is_valid and response.status_code == 200:
                try:
                    user_data = response.json()
                    print(f"User ID: {user_data.get('id', 'Unknown')}")
                    print(f"Display Name: {user_data.get('displayName', 'Unknown')}")
                    print(f"Username: {user_data.get('name', 'Unknown')}")
                except:
                    print("Additional info: Could not retrieve user details")
            else:
                print(f"Status Code: {response.status_code}")
                if response.status_code == 401:
                    print("Reason: Token expired or invalid")
                elif response.status_code == 403:
                    print("Reason: Access forbidden")
                else:
                    print("Reason: Unknown error")
            
            print(f"{'='*60}")
            return is_valid
            
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"ACCOUNT VALIDATION: {username}")
            print(f"{'='*60}")
            print(f"Valid: No")
            if cookie:
                if len(cookie) > 60:
                    token_preview = f"{cookie[:50]}...{cookie[-10:]}"
                else:
                    token_preview = cookie
                print(f"Token: {token_preview}")
            print(f"Error: {str(e)}")
            print(f"{'='*60}")
            return False
