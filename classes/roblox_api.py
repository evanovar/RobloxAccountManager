"""
Roblox API interaction utilities
Handles authentication, info, and game launching
"""

import os
import re
import time
import secrets
import requests
import subprocess
import shutil
import threading
from pathlib import Path

from .operation_result import OperationResult, unexpected_result

class RobloxAPI:
    """Handles all Roblox API interactions"""
    
    _rate_limiter_lock = threading.Lock()
    _last_request_time = None
    _min_interval = 6.0
    
    @classmethod
    def _wait_for_rate_limit(cls):
        with cls._rate_limiter_lock:
            if cls._last_request_time is not None:
                elapsed = time.time() - cls._last_request_time
                if elapsed < cls._min_interval:
                    wait_time = cls._min_interval - elapsed
                    print(f"[Rate Limiter] Waiting {wait_time:.1f}s before next API call...")
                    time.sleep(wait_time)
            cls._last_request_time = time.time()
    
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
                                print(f"[INFO] Moved installer from {folder.name}")
                        except Exception as e:
                            print(f"[ERROR] Failed to move installer from {folder.name}: {e}")
        except Exception as e:
            print(f"[ERROR] Error accessing versions folder: {e}")
    
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
                    print(f"[SUCCESS] Restored installer to {roblox_folder.name}")
                except Exception as e:
                    print(f"[ERROR] Failed to restore installer to {roblox_folder.name}: {e}")
            
            try:
                shutil.rmtree(str(quarantine_path), ignore_errors=True)
                print("[SUCCESS] Cleaned up quarantine folder")
            except:
                pass
        except Exception as e:
            print(f"[ERROR] Error restoring installers: {e}")

    @staticmethod
    def resolve_share_url(url_or_code, cookie=None):
        if not url_or_code:
            return None, None
        try:
            vip_match = re.search(
                r'roblox\.com/games/(\d+)/[^?#]*\?[^#]*privateServerLinkCode=([A-Za-z0-9]+)',
                url_or_code
            )
            if vip_match:
                return vip_match.group(1), vip_match.group(2)

            share_match = re.search(
                r'roblox\.com/share[^?#]*[?&]code=([A-Za-z0-9]+)',
                url_or_code
            )
            if not share_match:
                return None, None

            code = share_match.group(1)
            print(f"[INFO] Resolving share link code: {code[:8]}...")

            api_headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            if cookie:
                api_headers['Cookie'] = f'.ROBLOSECURITY={cookie}'

            if cookie:
                csrf_token = RobloxAPI.get_csrf_token(cookie)
                if csrf_token:
                    api_headers['X-CSRF-TOKEN'] = csrf_token

            for payload in [
                {"linkId": code, "linkType": "Server"},
                {"code": code, "type": "Server"},
            ]:
                try:
                    api_resp = requests.post(
                        "https://apis.roblox.com/sharelinks/v1/resolve-link",
                        json=payload, headers=api_headers, timeout=10
                    )
                    if api_resp.status_code == 200:
                        raw = api_resp.text
                        pid_m = re.search(r'"placeId"\s*:\s*(\d+)', raw)
                        lc_m = re.search(
                            r'"(?:linkCode|privateServerLinkCode|accessCode|linkcode)"\s*:\s*"([A-Za-z0-9_\-]+)"',
                            raw
                        )
                        if pid_m and lc_m:
                            print(f"[INFO] Resolved share link: placeId={pid_m.group(1)}")
                            return pid_m.group(1), lc_m.group(1)
                    elif api_resp.status_code == 403 and 'x-csrf-token' in api_resp.headers:
                        api_headers['X-CSRF-TOKEN'] = api_resp.headers['x-csrf-token']
                        retry = requests.post(
                            "https://apis.roblox.com/sharelinks/v1/resolve-link",
                            json=payload, headers=api_headers, timeout=10
                        )
                        if retry.status_code == 200:
                            raw = retry.text
                            pid_m = re.search(r'"placeId"\s*:\s*(\d+)', raw)
                            lc_m = re.search(
                                r'"(?:linkCode|privateServerLinkCode|accessCode|linkcode)"\s*:\s*"([A-Za-z0-9_\-]+)"',
                                raw
                            )
                            if pid_m and lc_m:
                                print(f"[INFO] Resolved share link: placeId={pid_m.group(1)}")
                                return pid_m.group(1), lc_m.group(1)
                except Exception as e:
                    print(f"[ERROR] resolve-link request failed: {e}")

        except Exception as e:
            print(f"[ERROR] Failed to resolve share URL: {e}")
        return None, None

    @staticmethod
    def get_user_info_from_api(roblosecurity_cookie) -> tuple[str, int]:
        """Get username and user ID using Roblox API"""
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
                return user_data.get('name', 'Unknown'), user_data.get('id', 0)
            
        except Exception as e:
            print(f"[ERROR] Error getting user info from API: {e}")
        
        return "Unknown", 0

    @staticmethod
    def get_username_from_api(roblosecurity_cookie):
        """Get username using Roblox API"""
        name, _ = RobloxAPI.get_user_info_from_api(roblosecurity_cookie)
        return name
    
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
    def get_user_id_from_username(username, max_retries=3, use_cache=True, cache_dict=None):
        """Get user ID from username"""
        if use_cache and cache_dict and username in cache_dict:
            cached_id = cache_dict[username]
            print(f"[INFO] Using cached user ID for '{username}': {cached_id}")
            return cached_id
        
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {
            "usernames": [username],
            "excludeBannedUsers": False
        }
        
        for attempt in range(max_retries):
            try:
                RobloxAPI._wait_for_rate_limit()
                
                response = requests.post(url, json=payload, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('data') and len(data['data']) > 0:
                        user_id = data['data'][0]['id']
                        
                        if use_cache and cache_dict is not None:
                            cache_dict[username] = user_id
                            print(f"[INFO] Stored user ID for '{username}': {user_id}")
                        
                        return user_id
                    else:
                        print(f"[WARNING] No user data found for username '{username}'")
                        return None
                elif response.status_code == 429:
                    retry_header = response.headers.get('Retry-After')
                    try:
                        retry_after = int(retry_header) if retry_header else (2 ** attempt)
                    except (ValueError, TypeError):
                        retry_after = 2 ** attempt
                    print(f"[WARNING] Rate limited getting user ID for '{username}'. Retrying in {retry_after}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_after)
                    continue
                else:
                    print(f"[WARNING] API returned status {response.status_code} for username '{username}'")
                    if attempt < max_retries - 1:
                        delay = 2 ** attempt
                        print(f"[WARNING] Retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    
            except requests.exceptions.Timeout:
                print(f"[ERROR] Timeout getting user ID for '{username}' (Attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except Exception as e:
                print(f"[ERROR] Exception getting user ID for '{username}': {e} (Attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
        
        return None
    
    @staticmethod
    def get_username_from_user_id(user_id):
        """Get username from user ID using Roblox API"""
        try:
            url = f"https://users.roblox.com/v1/users/{user_id}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('name', data.get('displayName', None))
            else:
                print(f"[WARNING] Failed to get username for user ID {user_id}: Status {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to get username for user ID {user_id}: {e}")
        
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
        if not str(roblosecurity_cookie or "").strip():
            return OperationResult.failure(
                "COOKIE_MISSING",
                "Account Cookie Missing",
                "This account does not have a Roblox security cookie.",
            )

        url = "https://auth.roblox.com/v1/authentication-ticket/"
        headers = {
            "User-Agent": "Roblox/WinInet",
            "Referer": "https://www.roblox.com/develop",
            "RBX-For-Gameauth": "true",
            "Content-Type": "application/json",
            "Cookie": f".ROBLOSECURITY={roblosecurity_cookie}"
        }

        try:
            csrf_token = ""
            for attempt in range(4):
                response = requests.post(url, headers=headers, timeout=8)
                if response.status_code == 403 and response.headers.get("x-csrf-token"):
                    csrf_token = response.headers["x-csrf-token"]
                    break
                if response.status_code in (401, 403):
                    print(
                        f"[ERROR] Authentication ticket rejected with HTTP "
                        f"{response.status_code}."
                    )
                    return OperationResult.failure(
                        "COOKIE_INVALID",
                        "Account Cookie Invalid",
                        "Roblox rejected this account cookie. Re-add or re-import the account.",
                        detail=f"Authentication ticket request returned HTTP {response.status_code}.",
                    )
                if response.status_code == 429:
                    wait = 2 ** attempt
                    print(
                        f"[WARNING] Authentication ticket request rate limited. "
                        f"Retrying in {wait}s."
                    )
                    time.sleep(wait)
                    continue
                return OperationResult.failure(
                    "AUTH_REQUEST_FAILED",
                    "Roblox Authentication Failed",
                    "Roblox did not accept the authentication request.",
                    detail=f"Initial authentication request returned HTTP {response.status_code}.",
                    retryable=response.status_code >= 500,
                )

            if not csrf_token:
                return OperationResult.failure(
                    "RATE_LIMITED",
                    "Roblox Rate Limit",
                    "Roblox temporarily rate-limited authentication. Wait a moment and try again.",
                    detail="The CSRF request remained rate limited after four attempts.",
                    retryable=True,
                )

            headers["X-CSRF-TOKEN"] = csrf_token
            for attempt in range(4):
                response = requests.post(url, headers=headers, timeout=8)
                if response.status_code == 200:
                    auth_ticket = response.headers.get("rbx-authentication-ticket")
                    if auth_ticket:
                        return OperationResult.success(data=auth_ticket)
                    return OperationResult.failure(
                        "AUTH_TICKET_MISSING",
                        "Authentication Ticket Missing",
                        "Roblox responded without an authentication ticket. Try again shortly.",
                        detail="HTTP 200 response did not include rbx-authentication-ticket.",
                        retryable=True,
                    )
                if response.status_code in (401, 403):
                    return OperationResult.failure(
                        "COOKIE_INVALID",
                        "Account Cookie Invalid",
                        "Roblox rejected this account cookie. Re-add or re-import the account.",
                        detail=f"Ticket request returned HTTP {response.status_code}.",
                    )
                if response.status_code == 429:
                    wait = 2 ** attempt
                    print(
                        f"[WARNING] Authentication ticket rate limited. "
                        f"Retrying in {wait}s."
                    )
                    time.sleep(wait)
                    continue
                return OperationResult.failure(
                    "AUTH_REQUEST_FAILED",
                    "Roblox Authentication Failed",
                    "Roblox could not issue an authentication ticket.",
                    detail=f"Ticket request returned HTTP {response.status_code}.",
                    retryable=response.status_code >= 500,
                )

            return OperationResult.failure(
                "RATE_LIMITED",
                "Roblox Rate Limit",
                "Roblox temporarily rate-limited authentication. Wait a moment and try again.",
                detail="The ticket request remained rate limited after four attempts.",
                retryable=True,
            )
        except requests.Timeout as exc:
            return OperationResult.failure(
                "NETWORK_TIMEOUT",
                "Roblox Request Timed Out",
                "Roblox did not respond in time. Check your connection and try again.",
                detail=str(exc),
                retryable=True,
            )
        except requests.ConnectionError as exc:
            return OperationResult.failure(
                "NETWORK_UNAVAILABLE",
                "Roblox Could Not Be Reached",
                "Check your internet connection and try again.",
                detail=str(exc),
                retryable=True,
            )
        except requests.RequestException as exc:
            return OperationResult.failure(
                "NETWORK_REQUEST_FAILED",
                "Roblox Request Failed",
                "The authentication request could not be completed.",
                detail=f"{type(exc).__name__}: {exc}",
                retryable=True,
            )
    
    @staticmethod
    def launch_roblox(username, cookie, game_id="", private_server_id="", launcher_preference="default", job_id="", custom_launcher_path=""):
        """Launch Roblox game with specified account"""
        if not str(username or "").strip():
            return OperationResult.failure(
                "ACCOUNT_MISSING",
                "Account Missing",
                "Select an account before launching Roblox.",
            )

        print(f"[INFO] Getting authentication ticket for {username}...")
        ticket_result = RobloxAPI.get_auth_ticket(cookie)
        if not ticket_result:
            print(
                f"[ERROR] Failed to get authentication ticket: "
                f"{ticket_result.code}"
            )
            return ticket_result
        auth_ticket = ticket_result.data

        print("[SUCCESS] Got authentication ticket!")

        browser_tracker_id = secrets.randbelow(
            8_000_000_000_000_000
        ) + 1_000_000_000_000_000
        launch_time = int(time.time() * 1000)

        if not game_id and not private_server_id:
            url = (
                "roblox-player:1+launchmode:play+gameinfo:" + auth_ticket +
                "+launchtime:" + str(launch_time) +
                "+browsertrackerid:" + str(browser_tracker_id) +
                "+robloxLocale:en_us+gameLocale:en_us"
            )
            print(f"[INFO] Launching Roblox Home for {username}")
            return RobloxAPI._execute_launch(url, launcher_preference, custom_launcher_path)

        link_code = None

        if private_server_id:
            ps = private_server_id.strip()
            if ps.isdigit():
                link_code = ps
            else:
                resolved_pid, resolved_lc = RobloxAPI.resolve_share_url(ps, cookie=cookie)
                if resolved_lc:
                    if not game_id:
                        game_id = resolved_pid
                    link_code = resolved_lc
                    print("[INFO] Private server link code extracted")
                else:
                    print("[ERROR] Invalid private server input. Expected a numeric code, VIP URL, or share link.")
                    return OperationResult.failure(
                        "PRIVATE_SERVER_INVALID",
                        "Invalid Private Server",
                        "Could not parse the private server input.\n\n"
                        "Accepted formats:\n"
                        "- Numeric link code\n"
                        "- VIP URL with privateServerLinkCode\n"
                        "- Roblox share URL"
                    )

        if not game_id:
            print("[ERROR] No Place ID provided.")
            return OperationResult.failure(
                "GAME_ID_MISSING",
                "Place ID Missing",
                "Enter a Place ID or a valid private-server link.",
            )

        url = (
            "roblox-player:1+launchmode:play+gameinfo:" + auth_ticket +
            "+launchtime:" + str(launch_time) +
            "+placelauncherurl:https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGameJob" +
            "&browserTrackerId=" + str(browser_tracker_id) +
            "&placeId=" + str(game_id) +
            "&isPlayTogetherGame=false"
        )

        if link_code:
            url += "&linkCode=" + link_code
        elif job_id:
            url += "&gameId=" + str(job_id)

        url += (
            "+browsertrackerid:" + str(browser_tracker_id) +
            "+robloxLocale:en_us+gameLocale:en_us"
        )

        print(f"[INFO] Launching Roblox for {username}...")
        print(f"[INFO] Place ID: {game_id}")
        if link_code:
            print(f"[INFO] Private server (link code: {link_code})")
        elif job_id:
            print(f"[INFO] Job ID: {job_id}")
        print(f"[INFO] Launcher: {launcher_preference}")

        return RobloxAPI._execute_launch(url, launcher_preference, custom_launcher_path)
    
    @staticmethod
    def _execute_launch(url, launcher_preference, custom_launcher_path=""):
        """Execute the Roblox launch with the specified launcher"""
        try:
            if launcher_preference == "custom":
                raw_custom_path = str(custom_launcher_path or "").strip()
                if not raw_custom_path:
                    return OperationResult.failure(
                        "CUSTOM_LAUNCHER_NOT_SET",
                        "Custom Launcher Not Set",
                        "Choose a custom launcher executable in Roblox Launcher settings.",
                    )
                custom_path = Path(raw_custom_path)
                if custom_path.suffix.lower() != ".exe":
                    return OperationResult.failure(
                        "CUSTOM_LAUNCHER_INVALID",
                        "Invalid Custom Launcher",
                        "The custom launcher must be an executable file.",
                        detail=f"Selected path: {custom_path}",
                    )
                if not custom_path.exists():
                    return OperationResult.failure(
                        "LAUNCHER_NOT_FOUND",
                        "Custom Launcher Not Found",
                        "The selected custom launcher could not be found.",
                        detail=f"Expected path: {custom_path}",
                    )

                subprocess.Popen([str(custom_path), url], creationflags=subprocess.CREATE_NO_WINDOW)
                print(f"[SUCCESS] Launched with Custom Launcher: {custom_path}")
                return OperationResult.success()

            if launcher_preference == "bloxstrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    return OperationResult.failure(
                        "LOCALAPPDATA_MISSING",
                        "Windows App Data Missing",
                        "The LOCALAPPDATA directory could not be located.",
                    )
                
                bloxstrap_path = Path(local_appdata) / 'Bloxstrap' / 'Bloxstrap.exe'
                if not bloxstrap_path.exists():
                    return OperationResult.failure(
                        "LAUNCHER_NOT_FOUND",
                        "Bloxstrap Not Found",
                        "Bloxstrap is not installed. Install it or select another launcher.",
                        detail=f"Expected path: {bloxstrap_path}",
                    )
                
                subprocess.Popen([str(bloxstrap_path), "-player", url], creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Bloxstrap!")
                return OperationResult.success()
            
            elif launcher_preference == "fishstrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    return OperationResult.failure(
                        "LOCALAPPDATA_MISSING",
                        "Windows App Data Missing",
                        "The LOCALAPPDATA directory could not be located.",
                    )
                
                fishstrap_path = Path(local_appdata) / 'Fishstrap' / 'Fishstrap.exe'
                if not fishstrap_path.exists():
                    return OperationResult.failure(
                        "LAUNCHER_NOT_FOUND",
                        "Fishstrap Not Found",
                        "Fishstrap is not installed. Install it or select another launcher.",
                        detail=f"Expected path: {fishstrap_path}",
                    )
                
                subprocess.Popen([str(fishstrap_path), "-player", url], creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Fishstrap!")
                return OperationResult.success()
            
            elif launcher_preference == "froststrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    return OperationResult.failure(
                        "LOCALAPPDATA_MISSING",
                        "Windows App Data Missing",
                        "The LOCALAPPDATA directory could not be located.",
                    )
                
                froststrap_path = Path(local_appdata) / 'Froststrap' / 'Froststrap.exe'
                if not froststrap_path.exists():
                    return OperationResult.failure(
                        "LAUNCHER_NOT_FOUND",
                        "Froststrap Not Found",
                        "Froststrap is not installed. Install it or select another launcher.",
                        detail=f"Expected path: {froststrap_path}",
                    )
                
                subprocess.Popen([str(froststrap_path), "-player", url], creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Froststrap!")
                return OperationResult.success()
            
            elif launcher_preference == "voidstrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    return OperationResult.failure(
                        "LOCALAPPDATA_MISSING",
                        "Windows App Data Missing",
                        "The LOCALAPPDATA directory could not be located.",
                    )
                
                voidstrap_path = Path(local_appdata) / 'Voidstrap' / 'Voidstrap.exe'
                if not voidstrap_path.exists():
                    return OperationResult.failure(
                        "LAUNCHER_NOT_FOUND",
                        "Voidstrap Not Found",
                        "Voidstrap is not installed. Install it or select another launcher.",
                        detail=f"Expected path: {voidstrap_path}",
                    )
                
                subprocess.Popen([str(voidstrap_path), "-player", url], creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Voidstrap!")
                return OperationResult.success()
            
            elif launcher_preference == "client":
                RobloxAPI.quarantine_installers()
                
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    return OperationResult.failure(
                        "LOCALAPPDATA_MISSING",
                        "Windows App Data Missing",
                        "The LOCALAPPDATA directory could not be located.",
                    )
                
                versions_dir = Path(local_appdata) / 'Roblox' / 'Versions'
                if not versions_dir.exists():
                    return OperationResult.failure(
                        "ROBLOX_NOT_INSTALLED",
                        "Roblox Client Not Found",
                        "Roblox Player does not appear to be installed.",
                        detail=f"Expected directory: {versions_dir}",
                    )
                
                version_folders = [d for d in versions_dir.iterdir() if d.is_dir() and d.name.startswith('version-')]
                if not version_folders:
                    return OperationResult.failure(
                        "ROBLOX_NOT_INSTALLED",
                        "Roblox Client Not Found",
                        "No installed Roblox Player version could be found.",
                        detail=f"Versions directory: {versions_dir}",
                    )
                
                latest_version = max(version_folders, key=lambda x: x.stat().st_mtime)
                client_path = latest_version / 'RobloxPlayerBeta.exe'
                
                if not client_path.exists():
                    return OperationResult.failure(
                        "ROBLOX_EXECUTABLE_MISSING",
                        "Roblox Client Not Found",
                        "The Roblox Player executable is missing. Reinstall Roblox or select another launcher.",
                        detail=f"Expected path: {client_path}",
                    )
                
                subprocess.Popen([str(client_path), url], creationflags=subprocess.CREATE_NO_WINDOW)
                print(f"[SUCCESS] Launched with Roblox Client from {latest_version.name}!")
                return OperationResult.success()
            
            elif launcher_preference == "default":
                os.startfile(url)
                print("[SUCCESS] Roblox launched successfully!")
                return OperationResult.success()

            return OperationResult.failure(
                "LAUNCHER_INVALID",
                "Invalid Roblox Launcher",
                "The configured Roblox launcher is not supported.",
                detail=f"Configured launcher: {launcher_preference}",
            )
                
        except PermissionError as exc:
            print(f"[ERROR] Roblox launch permission error: {exc}")
            return OperationResult.failure(
                "LAUNCH_PERMISSION_DENIED",
                "Roblox Launch Blocked",
                "Windows denied permission to start the selected launcher.",
                detail=str(exc),
            )
        except FileNotFoundError as exc:
            print(f"[ERROR] Roblox launcher file missing: {exc}")
            return OperationResult.failure(
                "LAUNCHER_NOT_FOUND",
                "Roblox Launcher Not Found",
                "The selected Roblox launcher could not be found.",
                detail=str(exc),
            )
        except OSError as exc:
            print(f"[ERROR] Failed to launch Roblox: {exc}")
            return OperationResult.failure(
                "ROBLOX_LAUNCH_FAILED",
                "Roblox Could Not Start",
                "Windows could not start Roblox. Check the selected launcher and try again.",
                detail=f"{type(exc).__name__}: {exc}",
            )
        except Exception as exc:
            print(f"[ERROR] Failed to launch Roblox: {exc}")
            return unexpected_result("Launching Roblox", exc)
    
    @staticmethod
    def validate_cookie(cookie):
        """Validate a Roblox security cookie with detailed status."""
        if not str(cookie or "").strip():
            return OperationResult.failure(
                "COOKIE_MISSING",
                "Account Cookie Missing",
                "No Roblox security cookie was provided.",
            )
        try:
            headers = {
                'Cookie': f'.ROBLOSECURITY={cookie}'
            }
            response = requests.get(
                'https://users.roblox.com/v1/users/authenticated',
                headers=headers,
                timeout=8
            )
            if response.status_code == 200:
                return OperationResult.success()
            if response.status_code in (401, 403):
                return OperationResult.failure(
                    "COOKIE_INVALID",
                    "Account Cookie Invalid",
                    "Roblox rejected this account cookie. Copy a new cookie and try again.",
                    detail=f"Cookie validation returned HTTP {response.status_code}.",
                )
            if response.status_code == 429:
                return OperationResult.failure(
                    "RATE_LIMITED",
                    "Roblox Rate Limit",
                    "Roblox temporarily rate-limited validation. Wait a moment and try again.",
                    detail="Cookie validation returned HTTP 429.",
                    retryable=True,
                )
            return OperationResult.failure(
                "COOKIE_VALIDATION_FAILED",
                "Cookie Could Not Be Verified",
                "Roblox could not verify the account cookie. Try again shortly.",
                detail=f"Cookie validation returned HTTP {response.status_code}.",
                retryable=response.status_code >= 500,
            )
        except requests.Timeout as exc:
            return OperationResult.failure(
                "NETWORK_TIMEOUT",
                "Roblox Request Timed Out",
                "Roblox did not respond in time. Check your connection and try again.",
                detail=str(exc),
                retryable=True,
            )
        except requests.RequestException as exc:
            return OperationResult.failure(
                "NETWORK_REQUEST_FAILED",
                "Roblox Could Not Be Reached",
                "The cookie could not be verified because Roblox could not be reached.",
                detail=f"{type(exc).__name__}: {exc}",
                retryable=True,
            )
