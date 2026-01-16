"""
Roblox API interaction utilities
Handles authentication, info, and game launching
"""

import os
import time
import random
import requests
import subprocess
import shutil
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
    def quarantine_installers():
        """Move RobloxPlayerInstaller.exe files to quarantine to prevent installer popups"""
        local_appdata = os.getenv('LOCALAPPDATA')
        if not local_appdata:
            return
        
        versions_path = Path(local_appdata) / 'Roblox' / 'Versions'
        quarantine_path = Path(local_appdata) / 'RobloxAccountManager' / 'Quarantine'
        
        if not versions_path.exists():
            return
        
        quarantine_path.mkdir(parents=True, exist_ok=True)
        
        try:
            for folder in versions_path.iterdir():
                if folder.is_dir() and folder.name.startswith('version-'):
                    installer = folder / 'RobloxPlayerInstaller.exe'
                    if installer.exists():
                        try:
                            version_id = folder.name.split('-')[1]
                            version_quarantine = quarantine_path / version_id
                            version_quarantine.mkdir(exist_ok=True)
                            
                            dest = version_quarantine / 'RobloxPlayerInstaller.exe'
                            if not dest.exists():
                                shutil.move(str(installer), str(dest))
                                print(f"[Quarantine] Moved installer from {folder.name}")
                        except Exception as e:
                            print(f"[Quarantine] Failed to move installer from {folder.name}: {e}")
        except Exception as e:
            print(f"[Quarantine] Error accessing versions folder: {e}")
    
    @staticmethod
    def restore_installers():
        """Restore RobloxPlayerInstaller.exe files from quarantine"""
        local_appdata = os.getenv('LOCALAPPDATA')
        if not local_appdata:
            return
        
        versions_path = Path(local_appdata) / 'Roblox' / 'Versions'
        quarantine_path = Path(local_appdata) / 'RobloxAccountManager' / 'Quarantine'
        
        if not quarantine_path.exists():
            return
        
        try:
            for version_folder in quarantine_path.iterdir():
                if not version_folder.is_dir():
                    continue
                
                installer_q = version_folder / 'RobloxPlayerInstaller.exe'
                if not installer_q.exists():
                    continue
                
                roblox_folder = versions_path / f'version-{version_folder.name}'
                if not roblox_folder.exists():
                    continue
                
                installer_restore = roblox_folder / 'RobloxPlayerInstaller.exe'
                try:
                    shutil.move(str(installer_q), str(installer_restore))
                    print(f"[Restore] Restored installer to {roblox_folder.name}")
                except Exception as e:
                    print(f"[Restore] Failed to restore installer to {roblox_folder.name}: {e}")
            
            try:
                shutil.rmtree(str(quarantine_path), ignore_errors=True)
                print("[Restore] Cleaned up quarantine folder")
            except:
                pass
        except Exception as e:
            print(f"[Restore] Error restoring installers: {e}")
    
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
    def get_csrf_token(cookie):
        """Get CSRF token for authenticated requests"""
        url = "https://auth.roblox.com/v2/logout"
        headers = {
            'Cookie': f'.ROBLOSECURITY={cookie}'
        }
        
        try:
            response = requests.post(url, headers=headers, timeout=5)
            return response.headers.get('x-csrf-token')
        except:
            return None
    
    @staticmethod
    def get_user_id_from_username(username):
        """Get user ID from username"""
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {
            "usernames": [username],
            "excludeBannedUsers": False
        }
        
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('data') and len(data['data']) > 0:
                    return data['data'][0]['id']
        except:
            pass
        return None
    
    @staticmethod
    def get_player_presence(user_id, cookie):
        """Get player's current presence (online status and game info)"""
        url = "https://presence.roblox.com/v1/presence/users"
        
        csrf_token = RobloxAPI.get_csrf_token(cookie)
        if not csrf_token:
            print("[ERROR] Failed to get CSRF token")
            return None
        
        headers = {
            'Cookie': f'.ROBLOSECURITY={cookie}',
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': csrf_token
        }
        
        payload = {
            "userIds": [user_id]
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('userPresences') and len(data['userPresences']) > 0:
                    presence = data['userPresences'][0]
                    
                    result = {
                        'user_id': presence.get('userId'),
                        'in_game': presence.get('userPresenceType') == 2,
                        'status': presence.get('userPresenceType', 0),
                        'last_location': presence.get('lastLocation', 'Unknown')
                    }
                    
                    if presence.get('userPresenceType') == 2:
                        result['place_id'] = presence.get('placeId')
                        result['root_place_id'] = presence.get('rootPlaceId')
                        result['universe_id'] = presence.get('universeId')
                        result['game_id'] = presence.get('gameId')
                    
                    return result
            else:
                print(f"[ERROR] Presence API returned status {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to get player presence: {e}")
        
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
    def launch_roblox(username, cookie, game_id, private_server_id="", launcher_preference="default", job_id=""):
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
            print(f"Launcher: {launcher_preference}")
            
            return RobloxAPI._execute_launch(url, launcher_preference)

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
        elif job_id:
            url += "&gameInstanceId=" + str(job_id)

        url += (
            "+browsertrackerid:" + str(browser_tracker_id) +
            "+robloxLocale:en_us+gameLocale:en_us"
        )

        print(f"Launching Roblox...")
        print(f"Account: {username}")
        print(f"Game ID: {game_id}")
        if private_server_code:
            print(f"Private Server: {private_server_code}")
        elif job_id:
            print(f"Job ID: {job_id}")
        print(f"Launcher: {launcher_preference}")
        
        return RobloxAPI._execute_launch(url, launcher_preference)
    
    @staticmethod
    def _execute_launch(url, launcher_preference):
        """Execute the Roblox launch with the specified launcher"""
        try:
            if launcher_preference == "bloxstrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    messagebox.showerror("Error", "Could not find LOCALAPPDATA directory.")
                    return False
                
                bloxstrap_path = Path(local_appdata) / 'Bloxstrap' / 'Bloxstrap.exe'
                if not bloxstrap_path.exists():
                    messagebox.showerror(
                        "Bloxstrap Not Found",
                        f"Bloxstrap is not installed.\n\nExpected location:\n{bloxstrap_path}\n\nPlease install Bloxstrap or select a different launcher."
                    )
                    return False
                
                subprocess.Popen([str(bloxstrap_path), "-player", url], creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Bloxstrap!")
                return True
            
            elif launcher_preference == "fishstrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    messagebox.showerror("Error", "Could not find LOCALAPPDATA directory.")
                    return False
                
                fishstrap_path = Path(local_appdata) / 'Fishstrap' / 'Fishstrap.exe'
                if not fishstrap_path.exists():
                    messagebox.showerror(
                        "Fishstrap Not Found",
                        f"Fishstrap is not installed.\n\nExpected location:\n{fishstrap_path}\n\nPlease install Fishstrap or select a different launcher."
                    )
                    return False
                
                subprocess.Popen([str(fishstrap_path), "-player", url], creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Fishstrap!")
                return True
            
            elif launcher_preference == "client":
                RobloxAPI.quarantine_installers()
                
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    messagebox.showerror("Error", "Could not find LOCALAPPDATA directory.")
                    return False
                
                versions_dir = Path(local_appdata) / 'Roblox' / 'Versions'
                if not versions_dir.exists():
                    messagebox.showerror(
                        "Roblox Client Not Found",
                        f"Roblox client directory not found.\n\nExpected location:\n{versions_dir}\n\nPlease install Roblox or select a different launcher."
                    )
                    return False
                
                version_folders = [d for d in versions_dir.iterdir() if d.is_dir() and d.name.startswith('version-')]
                if not version_folders:
                    messagebox.showerror(
                        "Roblox Client Not Found",
                        f"No Roblox version found in:\n{versions_dir}\n\nPlease reinstall Roblox or select a different launcher."
                    )
                    return False
                
                latest_version = max(version_folders, key=lambda x: x.stat().st_mtime)
                client_path = latest_version / 'RobloxPlayerBeta.exe'
                
                if not client_path.exists():
                    messagebox.showerror(
                        "Roblox Client Not Found",
                        f"RobloxPlayerBeta.exe not found in:\n{latest_version}\n\nPlease reinstall Roblox or select a different launcher."
                    )
                    return False
                
                subprocess.Popen([str(client_path), url], creationflags=subprocess.CREATE_NO_WINDOW)
                print(f"[SUCCESS] Launched with Roblox Client from {latest_version.name}!")
                return True
            
            else:  # default
                os.startfile(url)
                print("[SUCCESS] Roblox launched successfully!")
                return True
                
        except Exception as e:
            print(f"[ERROR] Failed to launch Roblox: {e}")
            messagebox.showerror("Launch Error", f"Failed to launch Roblox:\n\n{str(e)}")
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
            
            return is_valid
            
        except Exception as e:
            print(f"Account: {username}")
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
