import os
import json
import time
import tempfile
import subprocess
import threading
import random
import warnings
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import requests

warnings.filterwarnings("ignore")
os.environ['WDM_LOG_LEVEL'] = '0'

class RobloxAccountManager:
    def __init__(self):
        self.accounts_file = "saved_accounts.json"
        self.accounts = self.load_accounts()
        self.temp_profile_dir = None
        
    def load_accounts(self):
        """Load saved accounts from JSON file"""
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_accounts(self):
        """Save accounts to JSON file"""
        with open(self.accounts_file, 'w', encoding='utf-8') as f:
            json.dump(self.accounts, f, indent=2, ensure_ascii=False)
    
    def create_temp_profile(self):
        """Create a temporary Chrome profile directory"""
        self.temp_profile_dir = tempfile.mkdtemp(prefix="roblox_login_")
        return self.temp_profile_dir
    
    def cleanup_temp_profile(self):
        """Clean up temporary profile directory"""
        if self.temp_profile_dir and os.path.exists(self.temp_profile_dir):
            try:
                import shutil
                shutil.rmtree(self.temp_profile_dir)
            except:
                pass
    
    def setup_chrome_driver(self):
        """Setup Chrome driver with maximum speed optimizations"""
        profile_dir = self.create_temp_profile()
        
        chrome_options = Options()
        chrome_options.add_argument(f"--user-data-dir={profile_dir}")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--silent")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--disable-gpu-logging")
        chrome_options.add_argument("--disable-dev-tools")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-features=TranslateUI,BlinkGenPropertyTrees")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-component-extensions-with-background-pages")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--disable-hang-monitor")
        chrome_options.add_argument("--disable-prompt-on-repost")
        chrome_options.add_argument("--disable-domain-reliability")
        chrome_options.add_argument("--disable-component-update")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--aggressive-cache-discard")
        
        try:
            service = Service(
                ChromeDriverManager().install(),
                log_path=os.devnull
            )
            
            import sys
            original_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            sys.stderr.close()
            sys.stderr = original_stderr
            
            return driver
        except Exception as e:
            if 'original_stderr' in locals():
                sys.stderr = original_stderr
            print(f"Error setting up Chrome driver: {e}")
            print("Please make sure Google Chrome is installed on your system")
            return None
    
    def wait_for_login(self, driver, timeout=300):
        """Ultra-fast login detection using ONLY URL method"""
        print("🚀 Please log into your Roblox account - Browser will close upon login!")
        print("🔍 Using URL-only detection for maximum speed...")
        
        detector_script = """
        window.ultraFastDetection = {
            detected: false,
            method: null,
            debug: []
        };
        
        function instantDetect() {
            const now = Date.now();
            window.ultraFastDetection.debug.push('URL Check at: ' + now);
            
            const url = window.location.href.toLowerCase();
            window.ultraFastDetection.debug.push('Current URL: ' + url);
            
            if (url.includes('/login') || url.includes('/signup')) {
                window.ultraFastDetection.debug.push('Still on login/signup page - not logged in');
                return false;
            }
            
            if (url.includes('/home') || url.includes('/games') || 
                url.includes('/catalog') || url.includes('/avatar') ||
                url.includes('/discover') || url.includes('/friends') ||
                url.includes('/profile') || url.includes('/groups') ||
                url.includes('/develop') || url.includes('/create') ||
                url.includes('/transactions') || url.includes('/my/avatar') ||
                url.includes('roblox.com/users/') && !url.includes('/login')) {
                
                window.ultraFastDetection.detected = true;
                window.ultraFastDetection.method = 'url_only';
                window.ultraFastDetection.debug.push('✅ DETECTED via URL! Page: ' + url);
                return true;
            }
            
            window.ultraFastDetection.debug.push('Not detected - still checking...');
            return false;
        }
        
        instantDetect();
        
        const ultraInterval = setInterval(() => {
            if (instantDetect()) {
                clearInterval(ultraInterval);
            }
        }, 25);
        
        let lastHref = location.href;
        new MutationObserver(() => {
            if (location.href !== lastHref) {
                lastHref = location.href;
                window.ultraFastDetection.debug.push('URL changed to: ' + location.href);
                if (instantDetect()) {
                    clearInterval(ultraInterval);
                }
            }
        }).observe(document, {subtree: true, childList: true});
        
        ['beforeunload', 'unload', 'pagehide'].forEach(event => {
            window.addEventListener(event, instantDetect);
        });
        """
        
        try:
            driver.execute_script(detector_script)
            print("✅ Detection script injected successfully")
        except Exception as e:
            print(f"⚠ Warning: Could not inject detection script: {e}")
        
        start_time = time.time()
        last_debug_time = 0
        
        while time.time() - start_time < timeout:
            try:
                result = driver.execute_script("return window.ultraFastDetection;")
                
                if result and result.get('detected'):
                    method = result.get('method', 'url_only')
                    print(f"✅ LOGIN DETECTED! Method: {method} - Closing browser instantly...")
                    return True
                
                current_time = time.time()
                if current_time - last_debug_time > 5:
                    last_debug_time = current_time
                    try:
                        current_url = driver.current_url
                        print(f"🔍 Still checking... Current URL: {current_url}")
                        
                        if result and result.get('debug'):
                            recent_debug = result.get('debug', [])[-3:]
                            for debug_msg in recent_debug:
                                print(f"   Debug: {debug_msg}")
                        
                        if ('/home' in current_url or '/games' in current_url or 
                            '/catalog' in current_url or '/avatar' in current_url or
                            '/discover' in current_url or '/friends' in current_url or
                            '/profile' in current_url or '/groups' in current_url or
                            '/develop' in current_url or '/create' in current_url) and '/login' not in current_url:
                            print("✅ LOGIN DETECTED via manual URL check!")
                            return True
                                
                    except Exception as e:
                        print(f"   Debug error: {e}")
                
                time.sleep(0.025)
                
            except WebDriverException:
                return False
        
        print("⚠ Login timeout. Please try again.")
        return False
    
    def extract_user_info(self, driver):
        """Extract username and cookie with ultra-fast detection"""
        try:
            roblosecurity_cookie = None
            cookies = driver.get_cookies()
            
            for cookie in cookies:
                if cookie['name'] == '.ROBLOSECURITY':
                    roblosecurity_cookie = cookie['value']
                    break
            
            if not roblosecurity_cookie:
                return None, None
            
            username = None
            try:
                result = driver.execute_script("return window.ultraFastDetection;")
                if result and result.get('username'):
                    username = result.get('username')
                    print(f"✅ Username detected from page: {username}")
            except:
                pass
            
            if not username:
                try:
                    username_selectors = [
                        "[data-testid='navigation-user-display-name']",
                        "[data-testid='user-menu-button']",
                        ".font-header-2.text-color-secondary-alt",
                        "#nav-username",
                        ".navigation-user-name"
                    ]
                    
                    for selector in username_selectors:
                        try:
                            element = driver.find_element(By.CSS_SELECTOR, selector)
                            if element and element.text.strip():
                                username = element.text.strip()
                                break
                        except:
                            continue
                            
                except Exception:
                    pass
            
            if not username:
                username = self.get_username_from_api(roblosecurity_cookie)
            
            if not username:
                username = "Unknown"
            
            return username, roblosecurity_cookie
            
        except Exception as e:
            print(f"Error extracting user info: {e}")
            return None, None
    
    def get_username_from_api(self, roblosecurity_cookie):
        """Get username using Roblox API"""
        try:
            headers = {
                'Cookie': f'.ROBLOSECURITY={roblosecurity_cookie}'
            }
            
            response = requests.get(
                'https://users.roblox.com/v1/users/authenticated',
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                user_data = response.json()
                return user_data.get('name', 'Unknown')
            
        except Exception as e:
            print(f"Error getting username from API: {e}")
        
        return "Unknown"
    
    def get_auth_ticket(self, roblosecurity_cookie):
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
            response = requests.post(url, headers=headers, timeout=10)
            if response.status_code == 403 and "x-csrf-token" in response.headers:
                csrf_token = response.headers["x-csrf-token"]
            else:
                print(f"Failed to get CSRF token, status: {response.status_code}")
                return None

            headers["X-CSRF-TOKEN"] = csrf_token
            response2 = requests.post(url, headers=headers, timeout=10)
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
    
    def launch_roblox(self, username, game_id, private_server_id=""):
        """Launch Roblox game with specified account"""
        if username not in self.accounts:
            print(f"✗ Account '{username}' not found")
            return False
        
        cookie = self.accounts[username]['cookie']
        
        print(f"🎮 Getting authentication ticket for {username}...")
        auth_ticket = self.get_auth_ticket(cookie)
        
        if not auth_ticket:
            print("✗ Failed to get authentication ticket")
            return False
        
        print(f"✅ Got authentication ticket!")
        
        browser_tracker_id = random.randint(55393295400, 55393295500)
        launch_time = int(time.time() * 1000)

        url = (
            "roblox-player:1+launchmode:play+gameinfo:" + auth_ticket +
            "+launchtime:" + str(launch_time) +
            "+placelauncherurl:https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGame" +
            "&browserTrackerId=" + str(browser_tracker_id) +
            "&placeId=" + str(game_id) +
            "&isPlayTogetherGame=false"
        )

        if private_server_id:
            url += "&linkCode=" + private_server_id

        url += (
            "+browsertrackerid:" + str(browser_tracker_id) +
            "+robloxLocale:en_us+gameLocale:en_us"
        )

        print(f"🚀 Launching Roblox...")
        print(f"   Account: {username}")
        print(f"   Game ID: {game_id}")
        if private_server_id:
            print(f"   Private Server: {private_server_id}")
        
        try:
            os.system(f'start "" "{url}"')
            print("✅ Roblox launched successfully!")
            return True
        except Exception as e:
            print(f"✗ Failed to launch Roblox: {e}")
            return False
    
    def add_account(self):
        """Add a new account through browser login"""
        driver = self.setup_chrome_driver()
        if not driver:
            return False
        
        try:
            print("Opening Roblox login page...")
            driver.get("https://www.roblox.com/login")
            
            if self.wait_for_login(driver):
                username, cookie = self.extract_user_info(driver)
                
                if username and cookie:
                    self.accounts[username] = {
                        'username': username,
                        'cookie': cookie,
                        'added_date': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    self.save_accounts()
                    
                    print(f"✓ Successfully added account: {username}")
                    return True
                else:
                    print("✗ Failed to extract account information")
                    return False
            else:
                print("✗ Login was not completed")
                return False
                
        except Exception as e:
            print(f"Error during account addition: {e}")
            return False
        finally:
            try:
                driver.quit()
            except:
                pass
            self.cleanup_temp_profile()
    
    def list_accounts(self):
        """List all saved accounts"""
        if not self.accounts:
            print("No accounts saved.")
            return
        
        print("\nSaved Accounts:")
        print("-" * 50)
        for i, (username, data) in enumerate(self.accounts.items(), 1):
            added_date = data.get('added_date', 'Unknown')
            print(f"{i}. {username} (Added: {added_date})")
    
    def delete_account(self, username):
        """Delete a saved account"""
        if username in self.accounts:
            del self.accounts[username]
            self.save_accounts()
            print(f"✓ Deleted account: {username}")
            return True
        else:
            print(f"✗ Account '{username}' not found")
            return False
    
    def get_account_cookie(self, username):
        """Get cookie for a specific account"""
        if username in self.accounts:
            return self.accounts[username]['cookie']
        return None
    
    def validate_account(self, username):
        """Validate if an account's cookie is still valid and show detailed token info"""
        cookie = self.get_account_cookie(username)
        if not cookie:
            print(f"✗ Account '{username}' not found")
            return False
        
        try:
            headers = {
                'Cookie': f'.ROBLOSECURITY={cookie}'
            }
            
            response = requests.get(
                'https://users.roblox.com/v1/users/authenticated',
                headers=headers,
                timeout=10
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

def main():
    manager = RobloxAccountManager()
    
    while True:
        print("\n" + "="*50)
        print("🚀 ROBLOX ACCOUNT MANAGER")
        print("="*50)
        print("1. Add new account")
        print("2. List saved accounts")
        print("3. Delete account")
        print("4. Validate account")
        print("5. Launch Roblox game")
        print("6. Exit")
        print("-" * 50)
        
        choice = input("Select an option (1-6): ").strip()
        
        if choice == '1':
            print("\n🚀 Adding new account...")
            manager.add_account()
            
        elif choice == '2':
            manager.list_accounts()
            
        elif choice == '3':
            manager.list_accounts()
            if manager.accounts:
                username = input("\nEnter username to delete: ").strip()
                manager.delete_account(username)
            
        elif choice == '4':
            manager.list_accounts()
            if manager.accounts:
                username = input("\nEnter username to validate: ").strip()
                is_valid = manager.validate_account(username)
            else:
                print("No accounts to validate.")
            
        elif choice == '5':
            manager.list_accounts()
            if manager.accounts:
                username = input("\nEnter username to launch with: ").strip()
                if username in manager.accounts:
                    game_id = input("Enter Game/Place ID: ").strip()
                    private_server = input("Enter Private Server ID (leave blank for public): ").strip()
                    
                    if game_id.isdigit():
                        success = manager.launch_roblox(username, game_id, private_server)
                        if success:
                            print("🎮 Check your desktop - Roblox should be launching!")
                    else:
                        print("✗ Invalid Game ID. Please enter a valid number.")
                else:
                    print(f"✗ Account '{username}' not found")
            else:
                print("No accounts available to launch with.")
            
        elif choice == '6':
            print("Goodbye!")
            break
            
        else:
            print("Invalid option. Please try again.")

if __name__ == "__main__":
    main()