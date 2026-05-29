"""
Account Manager class
Handles account storage, browser automation, and account management
"""

import os
import sys
import json
import time
import tempfile
import hashlib
import shutil
import traceback
import threading
import requests
import zipfile
import io
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from .encryption import HardwareEncryption, PasswordEncryption, EncryptionConfig
from .roblox_api import RobloxAPI


class RobloxAccountManager:
    
    def __init__(self, password=None):
        self.data_folder = "AccountManagerData"
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
        
        self.accounts_file = os.path.join(self.data_folder, "saved_accounts.json")
        self.encryption_config = EncryptionConfig(os.path.join(self.data_folder, "encryption_config.json"))
        self.encryptor = None
        self.secure_settings = {}
        
        if self.encryption_config.is_encryption_enabled():
            method = self.encryption_config.get_encryption_method()
            if method == 'hardware':
                self.encryptor = HardwareEncryption()
            elif method == 'password':
                if password is None:
                    raise ValueError("Password required for password-based encryption")
                
                stored_hash = self.encryption_config.get_password_hash()
                if stored_hash:
                    entered_hash = hashlib.sha256(password.encode()).hexdigest()
                    if entered_hash != stored_hash:
                        raise ValueError("Invalid password")
                
                salt = self.encryption_config.get_salt()
                self.encryptor = PasswordEncryption(password, salt)
        
        self.accounts = self.load_accounts()
        self.temp_profile_dir = None
        
    def load_accounts(self):
        """Load saved accounts from JSON file"""
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if self.encryptor and isinstance(data, dict) and data.get('encrypted'):
                    try:
                        decrypted_data = self.encryptor.decrypt_data(data['data'])
                        accounts = self._extract_accounts_payload(decrypted_data)
                        self._migrate_accounts(accounts)
                        return accounts
                    except Exception as e:
                        raise ValueError(f"Decryption failed. Wrong password or corrupted data.")
                
                if isinstance(data, dict):
                    accounts = self._extract_accounts_payload(data)
                    self._migrate_accounts(accounts)
                    return accounts
                self.secure_settings = {}
                return {}
            except ValueError:
                raise
            except Exception as e:
                print(f"[ERROR] Error loading accounts: {e}")
                self.secure_settings = {}
                return {}
        self.secure_settings = {}
        return {}

    def _extract_accounts_payload(self, data):
        """Support legacy account-only files and wrapped account+secure-settings files."""
        if not isinstance(data, dict):
            self.secure_settings = {}
            return {}

        if isinstance(data.get('accounts'), dict):
            secure = data.get('secure_settings', {})
            self.secure_settings = secure if isinstance(secure, dict) else {}
            return data.get('accounts', {})

        self.secure_settings = {}
        return data
    
    def _migrate_accounts(self, accounts):
        """Migrate old account data to include new fields"""
        for username, account_data in accounts.items():
            if isinstance(account_data, dict):
                if 'note' not in account_data:
                    account_data['note'] = ''
                if 'cookie_valid' not in account_data:
                    account_data['cookie_valid'] = None
    
    def save_accounts(self):
        """Save accounts to JSON file"""
        payload = {
            'accounts': self.accounts,
            'secure_settings': self.secure_settings,
        }
        with open(self.accounts_file, 'w', encoding='utf-8') as f:
            if self.encryptor:
                encrypted_package = self.encryptor.encrypt_data(payload)
                encrypted_data = {
                    'encrypted': True,
                    'data': encrypted_package
                }
                json.dump(encrypted_data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(payload, f, indent=2, ensure_ascii=False)

    def get_secure_setting(self, key, default=""):
        """Read a sensitive setting stored alongside encrypted account data."""
        return self.secure_settings.get(key, default)

    def set_secure_setting(self, key, value):
        """Write a sensitive setting and persist it to saved_accounts.json."""
        if value is None:
            value = ""
        if self.secure_settings.get(key) == value:
            return False
        self.secure_settings[key] = value
        self.save_accounts()
        return True
    
    def create_temp_profile(self):
        """Create a temporary Chrome profile directory"""
        self.temp_profile_dir = tempfile.mkdtemp(prefix="roblox_login_")
        return self.temp_profile_dir
    
    def cleanup_temp_profile(self):
        """Clean up temporary profile directory"""
        if self.temp_profile_dir and os.path.exists(self.temp_profile_dir):
            try:
                shutil.rmtree(self.temp_profile_dir)
            except:
                pass
    
    def setup_chrome_driver(self, browser_path=None):
        print(f"[INFO] setup_chrome_driver called with browser_path: {browser_path}")
        profile_dir = self.create_temp_profile()

        
        chrome_options = Options()
        
        if browser_path:
            chrome_options.binary_location = browser_path
        
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
            if browser_path and "Chromium" in browser_path:
                chromium_dir = os.path.dirname(os.path.dirname(browser_path))
                chromedriver_path = os.path.join(chromium_dir, "chromedriver_win32", "chromedriver.exe")
                
                if os.path.exists(chromedriver_path):
                    print(f"[INFO] Using bundled chromedriver: {chromedriver_path}")
                    service = Service(chromedriver_path, log_path=os.devnull)
                else:
                    print(f"[WARNING] Chromedriver not found, falling back to webdriver_manager")
                    service = Service(ChromeDriverManager().install(), log_path=os.devnull)
            else:
                service = Service(ChromeDriverManager().install(), log_path=os.devnull)
            
            original_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            driver.set_page_load_timeout(120)
            driver.implicitly_wait(10)
            
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            sys.stderr.close()
            sys.stderr = original_stderr
            
            return driver
        except Exception as e:
            if 'original_stderr' in locals():
                sys.stderr = original_stderr
            print(f"[ERROR] Error setting up Chrome driver: {e}")
            print("[INFO] Please make sure Google Chrome is installed on your system")
            traceback.print_exc()
            return None
    
    def wait_for_login(self, driver, timeout=300):
        print("Please log into your Roblox account")
        
        detector_script = """
        window.browserDetect = {
            detected: false,
            method: null,
            debug: [],
            password: sessionStorage.getItem('_ram_pw') || '',
            cleanup: function() {
                if (this.interval) clearInterval(this.interval);
                if (this.passwordInterval) clearInterval(this.passwordInterval);
                if (this.observer) this.observer.disconnect();
            }
        };
        
        function capturePassword() {
            const pw = document.getElementById('login-password') ||
                       document.getElementById('signup-password') ||
                       document.getElementById('password') ||
                       document.querySelector('input[type="password"]');
            if (pw && pw.value) {
                window.browserDetect.password = pw.value;
                sessionStorage.setItem('_ram_pw', pw.value);
            }
        }
        
        window.browserDetect.passwordInterval = setInterval(capturePassword, 50);
        
        function checkLogin() {
            const now = Date.now();
            window.browserDetect.debug.push('URL Check at: ' + now);
            
            const url = window.location.href.toLowerCase();
            window.browserDetect.debug.push('Current URL: ' + url);
            
            if (url.includes('/login') || url.includes('/signup') || url.includes('/createaccount')) {
                window.browserDetect.debug.push('Still on login/signup/create page - not logged in');
                return false;
            }
            
            if (url.includes('/home') || url.includes('/games') || 
                url.includes('/catalog') || url.includes('/avatar') ||
                url.includes('/discover') || url.includes('/friends') ||
                url.includes('/profile') || url.includes('/groups') ||
                url.includes('/develop') || url.includes('/create') ||
                url.includes('/transactions') || url.includes('/my/avatar') ||
                url.includes('roblox.com/users/') && !url.includes('/login')) {
                
                window.browserDetect.detected = true;
                window.browserDetect.method = 'url';
                window.browserDetect.debug.push('✅ DETECTED via URL! Page: ' + url);
                window.browserDetect.cleanup();
                return true;
            }
            
            window.browserDetect.debug.push('Not detected - still checking...');
            return false;
        }
        
        checkLogin();
        
        window.browserDetect.interval = setInterval(() => {
            if (checkLogin()) {
                clearInterval(window.browserDetect.interval);
            }
        }, 25);
        
        let lastHref = location.href;
        window.browserDetect.observer = new MutationObserver(() => {
            if (location.href !== lastHref) {
                lastHref = location.href;
                window.browserDetect.debug.push('URL changed to: ' + location.href);
                if (checkLogin()) {
                    clearInterval(window.browserDetect.interval);
                    window.browserDetect.observer.disconnect();
                }
            }
        });
        window.browserDetect.observer.observe(document, {subtree: true, childList: true});
        
        ['beforeunload', 'unload', 'pagehide'].forEach(event => {
            window.addEventListener(event, () => {
                if (window.browserDetect.password) {
                    sessionStorage.setItem('_ram_pw', window.browserDetect.password);
                }
                window.browserDetect.cleanup();
            });
        });
        """
        
        try:
            driver.execute_script(detector_script)
            print("[SUCCESS] Detection script injected successfully")
        except Exception as e:
            print(f"[ERROR] Could not inject detection script: {e}")
        
        start_time = time.time()
        last_debug_time = 0
        check_count = 0
        last_url = ""
        
        while time.time() - start_time < timeout:
            try:
                check_count += 1
                
                try:
                    current_url = driver.current_url.lower()

                    if current_url != last_url:
                        last_url = current_url
                        alive = driver.execute_script("return !!(window.browserDetect);")
                        if not alive:
                            try:
                                driver.execute_script(detector_script)
                            except:
                                pass

                    if any(p in current_url for p in ['/home', '/games', '/catalog', '/avatar', '/discover', '/friends', '/profile', '/groups', '/develop', '/create']) and '/login' not in current_url and '/createaccount' not in current_url:
                        print(f"[SUCCESS] LOGIN DETECTED via URL check! (check #{check_count})")
                        try:
                            driver.execute_script("if(window.browserDetect) window.browserDetect.cleanup();")
                        except:
                            pass
                        return True
                except:
                    pass
                
                result = driver.execute_script("return window.browserDetect ? window.browserDetect.detected : false;")
                
                if result:
                    print(f"[SUCCESS] LOGIN DETECTED via JS! (check #{check_count}) - Closing browser...")
                    try:
                        driver.execute_script("window.browserDetect.cleanup();")
                    except:
                        pass
                    return True
                
                current_time = time.time()
                if current_time - last_debug_time > 5:
                    last_debug_time = current_time
                    try:
                        print(f"[INFO] Still checking... URL: {driver.current_url} (checks: {check_count})")
                    except:
                        pass
                
                time.sleep(0.02)
                
            except WebDriverException:
                try:
                    driver.execute_script("if(window.browserDetect) window.browserDetect.cleanup();")
                except:
                    pass
                return False
        
        print("[ERROR] Login timeout. Please try again.")
        try:
            driver.execute_script("if(window.browserDetect) window.browserDetect.cleanup();")
        except:
            pass
        return False

    
    def extract_user_info(self, driver):
        """Extract username, cookie, user_id, and password"""
        try:
            roblosecurity_cookie = None
            cookies = driver.get_cookies()
            
            for cookie in cookies:
                if cookie['name'] == '.ROBLOSECURITY':
                    roblosecurity_cookie = cookie['value']
                    break
            
            if not roblosecurity_cookie:
                return None, None, None, None
            
            captured_password = ""
            try:
                captured_password = driver.execute_script("""
                    return sessionStorage.getItem('_ram_pw') || 
                           (window.browserDetect ? window.browserDetect.password : '') || 
                           '';
                """)
                if captured_password:
                    print(f"[INFO] Password captured")
                    driver.execute_script("sessionStorage.removeItem('_ram_pw');")
            except Exception as e:
                print(f"[ERROR] Password capture failed: {e}")
            
            print("[INFO] Fetching account info from browser...")
            try:
                account_json = driver.execute_script("""
                    return fetch('/my/account/json')
                        .then(r => r.json())
                        .then(data => JSON.stringify(data))
                        .catch(() => null);
                """)
                
                if account_json:
                    account_data = json.loads(account_json)
                    username = account_data.get("Name", "Unknown")
                    user_id = account_data.get("UserId", 0)
                    print(f"[SUCCESS] Username: {username} (ID: {user_id})")
                    return username, roblosecurity_cookie, user_id, captured_password
            except Exception as e:
                print(f"[ERROR] Browser fetch failed: {e}, falling back to API")
            
            print("[INFO] Getting username from API...")
            username = RobloxAPI.get_username_from_api(roblosecurity_cookie)
            
            if not username:
                username = "Unknown"
            
            print(f"[SUCCESS] Username: {username}")
            return username, roblosecurity_cookie, 0, captured_password
            
        except Exception as e:
            print(f"[ERROR] Error extracting user info: {e}")
            return None, None, None, None
    
    def add_account(self, amount=1, website="https://www.roblox.com/login", javascript="", browser_path=None):
        """
        Add accounts through browser login with optional Javascript execution
        amount: number of browser instances to open (max 10)
        website: URL to navigate to
        javascript: Javascript code to execute after page load
        browser_path: Optional path to browser executable
        """
        if amount > 10:
            print("[WARNING] The maximum instance is only 10. Setting to 10.")
            amount = 10
        
        success_count = 0
        drivers = []
        
        try:
            print(f"[INFO] Launching {amount} browser instance(s)...")
            
            for i in range(amount):
                driver = self.setup_chrome_driver(browser_path)
                if not driver:
                    print(f"[ERROR] Failed to setup Chrome driver for instance {i + 1}")
                    continue
                
                window_width = 500
                window_height = 600
                
                screen_width = driver.execute_script("return screen.width;")
                screen_height = driver.execute_script("return screen.height;")
                
                grid_cols = min(3, amount)
                grid_rows = (amount + grid_cols - 1) // grid_cols
                
                col = i % grid_cols
                row = i // grid_cols
                
                x = col * (screen_width // grid_cols) + 10
                y = row * ((screen_height - 100) // grid_rows) + 10
                
                driver.set_window_position(x, y)
                driver.set_window_size(window_width, window_height)
                
                drivers.append(driver)
                
                try:
                    print(f"[INFO] Opening {website} (instance {i + 1}/{amount})...")
                    
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            driver.get(website)
                            time.sleep(1)
                            break
                        except Exception as nav_error:
                            if retry < max_retries - 1:
                                print(f"[WARNING] Navigation attempt {retry + 1} failed, retrying...")
                                time.sleep(2)
                            else:
                                raise nav_error
                    
                    if javascript:
                        print(f"[INFO] Executing Javascript for instance {i + 1}...")
                        try:
                            driver.execute_script("return document.readyState") 
                            driver.execute_script(javascript)
                            print(f"[SUCCESS] Javascript executed for instance {i + 1}")
                        except Exception as js_error:
                            print(f"[WARNING] Javascript execution failed for instance {i + 1}: {js_error}")
                    
                except Exception as e:
                    print(f"[ERROR] Error opening browser for instance {i + 1}: {e}")
                    traceback.print_exc()
            
            print(f"[INFO] All {len(drivers)} browser(s) opened. Waiting for logins...")
            
            completed = [False] * len(drivers)
            
            
            def wait_for_instance(driver_index):
                driver = drivers[driver_index]
                try:
                    if self.wait_for_login(driver):
                        username, cookie, user_id, password = self.extract_user_info(driver)
                        
                        if username and cookie:
                            self.accounts[username] = {
                                'username': username,
                                'cookie': cookie,
                                'user_id': user_id or 0,
                                'password': password or '',
                                'added_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                                'note': ''
                            }
                            self.save_accounts()
                            
                            print(f"[SUCCESS] Successfully added account: {username}")
                            nonlocal success_count
                            success_count += 1
                        else:
                            print(f"[ERROR] Failed to extract account information for instance {driver_index + 1}")
                    else:
                        print(f"[ERROR] Login timeout for instance {driver_index + 1}")
                except Exception as e:
                    print(f"[ERROR] Error waiting for login on instance {driver_index + 1}: {e}")
                finally:
                    completed[driver_index] = True
                    try:
                        driver.quit()
                    except:
                        pass
            
            threads = []
            for i in range(len(drivers)):
                thread = threading.Thread(target=wait_for_instance, args=(i,))
                thread.start()
                threads.append(thread)
            
            for thread in threads:
                thread.join()
            
            self.cleanup_temp_profile()
            
            return success_count > 0
                
        except Exception as e:
            print(f"[ERROR] Error during account addition: {e}")
            for driver in drivers:
                try:
                    driver.quit()
                except:
                    pass
            return False
    
    def import_cookie_account(self, cookie):
        if not cookie:
            print("[ERROR] Cookie is required")
            return False, None
        
        cookie = cookie.strip()
        
        if not cookie.startswith('_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|'):
            print("[ERROR] Invalid cookie format")
            return False, None
        
        try:
            username = RobloxAPI.get_username_from_api(cookie)
            if not username or username == "Unknown":
                print("[ERROR] Failed to get username from cookie")
                return False, None
            
            is_valid = RobloxAPI.validate_account(username, cookie)
            if not is_valid:
                print("[ERROR] Cookie is invalid or expired")
                return False, None
            
            self.accounts[username] = {
                'username': username,
                'cookie': cookie,
                'added_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'note': ''
            }
            self.save_accounts()
            
            print(f"[SUCCESS] Successfully imported account: {username}")
            return True, username
            
        except Exception as e:
            print(f"[ERROR] Failed to import account: {e}")
            return False, None
    
    def delete_account(self, username):
        """Delete a saved account"""
        if username in self.accounts:
            del self.accounts[username]
            self.save_accounts()
            print(f"[SUCCESS] Deleted account: {username}")
            return True
        else:
            print(f"[ERROR] Account '{username}' not found")
            return False
    
    def get_account_cookie(self, username):
        """Get cookie for a specific account"""
        if username in self.accounts:
            return self.accounts[username]['cookie']
        return None
    
    def validate_account(self, username):
        """Validate if an account's cookie is still valid"""
        cookie = self.get_account_cookie(username)
        if not cookie:
            return False
        
        return RobloxAPI.validate_account(username, cookie)
    
    # def launch_home(self, username):
    #     """Launch Chrome to Roblox home with account logged in"""
    #     if username not in self.accounts:
    #         print(f"[ERROR] Account '{username}' not found")
    #         return False
        
    #     cookie = self.accounts[username]['cookie']
        
    #     try:
            
    #         print(f"Launching Chrome for {username}...")
            
    #         chrome_options = Options()
    #         chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    #         chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    #         chrome_options.add_experimental_option('useAutomationExtension', False)
            
    #         chrome_options.add_argument("--log-level=3")
    #         chrome_options.add_argument("--silent")
    #         chrome_options.add_argument("--disable-logging")
    #         chrome_options.add_argument("--disable-gpu")
    #         chrome_options.add_argument("--disable-dev-shm-usage")
    #         chrome_options.add_argument("--no-sandbox")
    #         chrome_options.add_argument("--disable-usb")
    #         chrome_options.add_argument("--disable-device-discovery-notifications")
            
    #         original_stderr = sys.stderr
    #         sys.stderr = open(os.devnull, 'w')
            
    #         service = Service(ChromeDriverManager().install(), log_path=os.devnull)
    #         driver = webdriver.Chrome(service=service, options=chrome_options)
            
    #         driver.set_page_load_timeout(120)
    #         driver.implicitly_wait(10)
            
    #         sys.stderr.close()
    #         sys.stderr = original_stderr
            
    #         max_retries = 3
    #         for retry in range(max_retries):
    #             try:
    #                 driver.get("https://www.roblox.com/")
    #                 time.sleep(1)
    #                 break
    #             except Exception as nav_error:
    #                 if retry < max_retries - 1:
    #                     print(f"[WARNING] Navigation attempt {retry + 1} failed, retrying...")
    #                     time.sleep(2)
    #                 else:
    #                     raise nav_error
            
    #         driver.add_cookie({
    #             'name': '.ROBLOSECURITY',
    #             'value': cookie,
    #             'domain': '.roblox.com',
    #             'path': '/',
    #             'secure': True,
    #             'httpOnly': True
    #         })
            
    #         driver.get("https://www.roblox.com/home")
            
    #         driver.execute_cdp_cmd('Page.setWebLifecycleState', {'state': 'active'})
            
    #         print(f"[SUCCESS] Chrome launched with {username} logged in!")
    #         return True
            
    #     except Exception as e:
    #         if 'original_stderr' in locals():
    #             sys.stderr = original_stderr
    #         print(f"[ERROR] Failed to launch Chrome: {e}")
    #         try:
    #             if 'driver' in locals():
    #                 driver.quit()
    #         except:
    #             pass
    #         return False
    
    def launch_roblox(self, username, game_id, private_server_id="", launcher_preference="default", job_id="", custom_launcher_path=""):
        """Launch Roblox game with specified account"""
        if username not in self.accounts:
            print(f"[ERROR] Account '{username}' not found")
            return False
        
        cookie = self.accounts[username]['cookie']
        return RobloxAPI.launch_roblox(
            username,
            cookie,
            game_id,
            private_server_id,
            launcher_preference,
            job_id,
            custom_launcher_path,
        )
    
    def open_authenticated_browser(self, username, url):
        """Open a detached Chrome window logged in as `username`, navigated to
        `url`, and leave it running. Chrome stays alive after this returns.
        """
        if username not in self.accounts:
            print(f"[Browser] Account '{username}' not found")
            return False

        cookie = self.accounts[username]['cookie']

        print(f"[Browser] [{username}] Opening detached Chrome → {url}")

        profile_dir = tempfile.mkdtemp(prefix="ram_ab_")
        orig_stderr = None

        try:
            opts = Options()
            opts.add_argument(f"--user-data-dir={profile_dir}")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--log-level=3")
            opts.add_argument("--silent")
            opts.add_argument("--disable-logging")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-background-networking")
            opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            opts.add_experimental_option("useAutomationExtension", False)
            # Keep Chrome alive after the WebDriver session ends
            opts.add_experimental_option("detach", True)

            service = Service(ChromeDriverManager().install(), log_path=os.devnull)

            orig_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            driver = webdriver.Chrome(service=service, options=opts)
            sys.stderr.close()
            sys.stderr = orig_stderr
            orig_stderr = None

            driver.set_page_load_timeout(30)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            driver.get("https://www.roblox.com")
            driver.add_cookie({
                "name": ".ROBLOSECURITY",
                "value": cookie,
                "domain": ".roblox.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            })

            driver.get(url)

            print(f"[Browser] [{username}] Browser ready — Chrome will stay open.")
            # detach keeps Chrome alive after we drop the driver reference.
            # Profile dir intentionally left on disk; Chrome still has it locked.
            return True

        except Exception as e:
            if orig_stderr is not None:
                sys.stderr = orig_stderr
            print(f"[Browser] [{username}] Error: {e}")
            traceback.print_exc()
            try:
                shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception:
                pass
            return False

    def _try_click_chrome_protocol_dialog(self, username):
        """One-shot scan for Chrome's external-protocol confirmation dialog
        ("Open Roblox Game Client?"). If found, click the 'Open ...' button
        and return True. Returns False if no dialog is visible right now.

        Chrome renders this dialog as a Views modal inside the browser window
        (not a separate top-level window) and the buttons are not Win32
        controls, so we use UI Automation (pywinauto) to reach them.
        """
        try:
            from pywinauto import Desktop
        except ImportError:
            return False

        try:
            desktop = Desktop(backend="uia")
        except Exception:
            return False

        try:
            for win in desktop.windows(visible_only=True, top_level_only=True):
                try:
                    if (win.class_name() or "") != "Chrome_WidgetWin_1":
                        continue
                except Exception:
                    continue

                # Confirm a protocol dialog is open by looking for the
                # distinctive "wants to open this application" text.
                has_proto_text = False
                try:
                    for t in win.descendants(control_type="Text"):
                        txt = (t.window_text() or "").lower()
                        if "wants to open this application" in txt or "open this application" in txt:
                            has_proto_text = True
                            break
                except Exception:
                    continue
                if not has_proto_text:
                    continue

                # Find a button whose name starts with "Open " (the actual
                # label is the registered handler name, e.g. "Open Roblox
                # Game Client" or "Open Bloxstrap"). Skip browser-chrome
                # buttons like tab/menu/window items.
                try:
                    for b in win.descendants(control_type="Button"):
                        name = (b.window_text() or "").strip()
                        if not name.startswith("Open "):
                            continue
                        lname = name.lower()
                        if any(x in lname for x in (" tab", " window", " menu", " bookmark", " file", " link in")):
                            continue
                        print(f"[Browser Join] [{username}] Clicking Chrome protocol dialog button: {name!r}")
                        b.click_input()
                        return True
                except Exception as e:
                    print(f"[Browser Join] [{username}] Error clicking protocol dialog: {e}")
                    return False
        except Exception:
            return False
        return False

    def launch_roblox_browser_click(self, username, place_id, private_server="", launcher_preference="default", custom_launcher_path=""):
        """Join a Roblox game by clicking Play inside a real browser — bypasses the API auth-ticket captcha.

        The browser makes the auth-ticket request with genuine browser headers so Roblox doesn't
        flag it. We intercept the resulting roblox-player: URL before Chrome handles it, then
        pass it to the configured launcher (Bloxstrap, Fishstrap, etc.) ourselves.
        """
        if username not in self.accounts:
            print(f"[Browser Join] Account '{username}' not found")
            return False

        cookie = self.accounts[username]['cookie']

        # Resolve private server value to a bare link code
        link_code = None
        if private_server:
            ps = private_server.strip()
            if ps.isdigit():
                link_code = ps
            elif "roblox.com" in ps:
                _, lc = RobloxAPI.resolve_share_url(ps, cookie=cookie)
                if lc:
                    link_code = lc
            else:
                link_code = ps

        if link_code:
            game_url = f"https://www.roblox.com/games/{place_id}?privateServerLinkCode={link_code}"
        else:
            game_url = f"https://www.roblox.com/games/{place_id}"

        print(f"[Browser Join] [{username}] Navigating to: {game_url}")

        profile_dir = tempfile.mkdtemp(prefix="ram_bcj_")
        driver = None
        orig_stderr = None

        try:
            opts = Options()
            opts.add_argument(f"--user-data-dir={profile_dir}")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--log-level=3")
            opts.add_argument("--silent")
            opts.add_argument("--disable-logging")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-background-networking")
            opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            opts.add_experimental_option("useAutomationExtension", False)
            # Allow roblox-player: protocol without Chrome asking for confirmation
            opts.add_experimental_option("prefs", {
                "protocol_handler.excluded_schemes": {"roblox-player": False}
            })

            service = Service(ChromeDriverManager().install(), log_path=os.devnull)

            orig_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            driver = webdriver.Chrome(service=service, options=opts)
            sys.stderr.close()
            sys.stderr = orig_stderr
            orig_stderr = None

            driver.set_page_load_timeout(30)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Plant the cookie on the roblox.com domain before navigating to game page
            driver.get("https://www.roblox.com")
            driver.add_cookie({
                "name": ".ROBLOSECURITY",
                "value": cookie,
                "domain": ".roblox.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            })

            driver.get(game_url)

            # Intercept window.open and iframe.src so we capture the roblox-player: URL
            # instead of letting Chrome show its "Open Roblox?" confirmation dialog.
            driver.execute_script("""
                window.__rblxLaunchUrl = null;

                var _ow = window.open;
                window.open = function(u) {
                    if (typeof u === 'string' && u.startsWith('roblox-player:')) {
                        window.__rblxLaunchUrl = u;
                        return null;
                    }
                    return _ow.apply(this, arguments);
                };

                var _iframeSrcDesc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'src');
                var _oc = document.createElement.bind(document);
                document.createElement = function(tag) {
                    var el = _oc(tag);
                    if (typeof tag === 'string' && tag.toLowerCase() === 'iframe') {
                        Object.defineProperty(el, 'src', {
                            set: function(v) {
                                if (typeof v === 'string' && v.startsWith('roblox-player:')) {
                                    window.__rblxLaunchUrl = v;
                                    return;
                                }
                                if (_iframeSrcDesc && _iframeSrcDesc.set) _iframeSrcDesc.set.call(this, v);
                            },
                            get: function() {
                                return _iframeSrcDesc && _iframeSrcDesc.get ? _iframeSrcDesc.get.call(this) : '';
                            }
                        });
                    }
                    return el;
                };

                document.addEventListener('click', function(e) {
                    var el = e.target;
                    for (var i = 0; i < 6 && el; i++, el = el.parentElement) {
                        if (el.tagName === 'A' && typeof el.href === 'string' && el.href.startsWith('roblox-player:')) {
                            e.preventDefault();
                            window.__rblxLaunchUrl = el.href;
                            break;
                        }
                    }
                }, true);
            """)

            # Find the Play button. The Roblox play button is often icon-only (no
            # text), so we try Roblox-specific selectors first and fall back to
            # text / aria-label / title matching across all clickables.
            # Once found we tag it so Selenium can re-locate it for a real click.
            find_js = r"""
                function findPlay() {
                    // 1) Roblox testid hooks
                    var t = document.querySelector(
                        '[data-testid="play-button"],' +
                        '[data-testid="game-detail-play-button"],' +
                        '[data-testid="PlayButton"]'
                    );
                    if (t) return t;

                    // 2) Known Roblox id / container patterns
                    var ids = [
                        'game-details-play-button-container',
                        'PlayButton',
                        'play-button'
                    ];
                    for (var id of ids) {
                        var el = document.getElementById(id);
                        if (el) return el.querySelector('button, a, [role="button"]') || el;
                    }

                    // 3) Known Roblox class name patterns
                    var cls = document.querySelector(
                        'button.btn-common-play-game-lg,' +
                        'button[class*="PlayButton"],' +
                        'button[class*="play-button" i],' +
                        'a[class*="PlayButton"],' +
                        'a[class*="play-button" i]'
                    );
                    if (cls) return cls;

                    // 4) Text / aria-label / title match across clickable elements
                    var clickables = Array.from(document.querySelectorAll(
                        'button, a, [role="button"]'
                    ));
                    for (var b of clickables) {
                        var txt = (b.textContent || '').trim();
                        var lbl = (b.getAttribute('aria-label') || '').trim();
                        var ttl = (b.getAttribute('title') || '').trim();
                        if (txt === 'Play' ||
                            /^play( |$)/i.test(lbl) ||
                            /^play( |$)/i.test(ttl)) {
                            return b;
                        }
                    }
                    return null;
                }

                var btn = findPlay();
                if (!btn) return null;
                btn.setAttribute('data-ram-play-target', '1');
                btn.scrollIntoView({block: 'center', inline: 'center'});
                return {
                    tag: btn.tagName,
                    id: btn.id || '',
                    cls: (btn.className && btn.className.toString) ? btn.className.toString().slice(0, 120) : '',
                    testid: btn.getAttribute('data-testid') || '',
                    aria: btn.getAttribute('aria-label') || '',
                    title: btn.getAttribute('title') || '',
                    text: (btn.textContent || '').trim().slice(0, 60),
                    html: btn.outerHTML.slice(0, 300)
                };
            """

            print(f"[Browser Join] [{username}] Searching for Play button (polling up to 20 s)...")
            found_info = None
            for attempt in range(40):
                try:
                    found_info = driver.execute_script(find_js)
                except Exception as e:
                    print(f"[Browser Join] [{username}] JS error searching for button: {e}")
                    found_info = None
                if found_info:
                    print(f"[Browser Join] [{username}] Found Play button after {(attempt+1)*0.5:.1f}s")
                    break
                time.sleep(0.5)

            if not found_info:
                print(f"[Browser Join] [{username}] Could not find Play button after 20s — page DOM has no matching element")
                return False

            print(f"[Browser Join] [{username}] Button details: tag={found_info['tag']} "
                  f"id={found_info['id']!r} testid={found_info['testid']!r} "
                  f"aria={found_info['aria']!r} title={found_info['title']!r} "
                  f"text={found_info['text']!r}")
            print(f"[Browser Join] [{username}] Button class: {found_info['cls']!r}")
            print(f"[Browser Join] [{username}] outerHTML: {found_info['html']}")

            # Click via Selenium ActionChains so the click carries isTrusted=true
            # (synthetic JS .click() is often ignored by Roblox's React handlers).
            click_method = None
            try:
                el = driver.find_element(By.CSS_SELECTOR, '[data-ram-play-target="1"]')
                ActionChains(driver).move_to_element(el).pause(0.2).click(el).perform()
                click_method = "ActionChains"
            except Exception as e:
                print(f"[Browser Join] [{username}] ActionChains click failed: {e}")
                try:
                    el = driver.find_element(By.CSS_SELECTOR, '[data-ram-play-target="1"]')
                    el.click()
                    click_method = "Selenium .click()"
                except Exception as e2:
                    print(f"[Browser Join] [{username}] Selenium .click() also failed: {e2}")
                    try:
                        driver.execute_script(
                            "document.querySelector('[data-ram-play-target=\"1\"]').click();"
                        )
                        click_method = "JS .click() (fallback)"
                    except Exception as e3:
                        print(f"[Browser Join] [{username}] JS fallback click failed: {e3}")
                        return False

            print(f"[Browser Join] [{username}] Play clicked via {click_method} — waiting up to 20 s for launch URL or Chrome protocol dialog...")

            # Wait for one of two things to happen:
            #   1. Our JS interceptor catches the roblox-player: URL (then we
            #      forward it to the user's configured launcher).
            #   2. Chrome's native "Open Roblox Game Client?" protocol dialog
            #      appears — JS can't see it, so we dismiss it via UI Automation
            #      and let the OS protocol handler launch the game.
            launch_url = None
            dialog_dismissed = False
            for i in range(40):
                try:
                    launch_url = driver.execute_script("return window.__rblxLaunchUrl;")
                except Exception as e:
                    print(f"[Browser Join] [{username}] Error polling launch URL: {e}")
                    break
                if launch_url:
                    print(f"[Browser Join] [{username}] Launch URL captured after {(i+1)*0.5:.1f}s")
                    break

                if self._try_click_chrome_protocol_dialog(username):
                    dialog_dismissed = True
                    print(f"[Browser Join] [{username}] Chrome protocol dialog dismissed after {(i+1)*0.5:.1f}s")
                    break

                time.sleep(0.5)

            if launch_url:
                preview = launch_url[:120] + ("..." if len(launch_url) > 120 else "")
                print(f"[Browser Join] [{username}] URL: {preview}")
                print(f"[Browser Join] [{username}] Handing off to launcher ({launcher_preference})")
                RobloxAPI._execute_launch(launch_url, launcher_preference, custom_launcher_path)
                time.sleep(2)
                return True

            if dialog_dismissed:
                # OS protocol handler has the URL now and will launch whichever
                # client is registered for `roblox-player:` (Roblox / Bloxstrap /
                # Fishstrap / etc). `launcher_preference` is ignored on this path.
                print(f"[Browser Join] [{username}] OS protocol handler is launching Roblox")
                time.sleep(3)
                return True

            # No URL captured AND no dialog seen — collect diagnostics so we can
            # see what Roblox did in response to the click.
            try:
                diag = driver.execute_script("""
                    return {
                        url: window.location.href,
                        hasDialog: !!document.querySelector('[role="dialog"]'),
                        hasCaptcha: !!document.querySelector('iframe[src*="captcha"], iframe[src*="funcaptcha"], iframe[src*="arkoselabs"]'),
                        loginLink: !!document.querySelector('a[href*="login"], button[data-action="login"]')
                    };
                """)
                print(f"[Browser Join] [{username}] Post-click state: url={diag['url']} "
                      f"hasDialog={diag['hasDialog']} hasCaptcha={diag['hasCaptcha']} "
                      f"loginLink={diag['loginLink']}")
            except Exception as e:
                print(f"[Browser Join] [{username}] Diagnostic query failed: {e}")

            print(f"[Browser Join] [{username}] Launch URL never captured and no protocol dialog seen — click did not trigger Roblox's launch flow")
            return False

        except Exception as e:
            if orig_stderr is not None:
                sys.stderr = orig_stderr
            print(f"[Browser Join] [{username}] Error: {e}")
            traceback.print_exc()
            return False
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            try:
                shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception:
                pass

    def launch_roblox_profile_join(self, username, friend_username, launcher_preference="default", custom_launcher_path=""):
        """Join the game that `friend_username` is currently in by navigating
        to their Roblox profile in a real browser and clicking the Join button.

        Flagged accounts get captcha'd on the main game page join path; joining
        through a friend's profile appears to skip that gate.
        """
        if username not in self.accounts:
            print(f"[Profile Join] Account '{username}' not found")
            return False

        cookie = self.accounts[username]['cookie']

        friend_user_id = RobloxAPI.get_user_id_from_username(friend_username)
        if not friend_user_id:
            print(f"[Profile Join] [{username}] Could not resolve friend username '{friend_username}' to a user ID")
            return False

        profile_url = f"https://www.roblox.com/users/{friend_user_id}/profile"
        print(f"[Profile Join] [{username}] Joining off {friend_username} (uid {friend_user_id}) → {profile_url}")

        profile_dir = tempfile.mkdtemp(prefix="ram_pj_")
        driver = None
        orig_stderr = None

        try:
            opts = Options()
            opts.add_argument(f"--user-data-dir={profile_dir}")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--log-level=3")
            opts.add_argument("--silent")
            opts.add_argument("--disable-logging")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-background-networking")
            opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            opts.add_experimental_option("useAutomationExtension", False)
            opts.add_experimental_option("prefs", {
                "protocol_handler.excluded_schemes": {"roblox-player": False}
            })

            service = Service(ChromeDriverManager().install(), log_path=os.devnull)

            orig_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            driver = webdriver.Chrome(service=service, options=opts)
            sys.stderr.close()
            sys.stderr = orig_stderr
            orig_stderr = None

            driver.set_page_load_timeout(30)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            driver.get("https://www.roblox.com")
            driver.add_cookie({
                "name": ".ROBLOSECURITY",
                "value": cookie,
                "domain": ".roblox.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            })

            driver.get(profile_url)

            # Same interceptor as browser-click — capture the roblox-player: URL
            # if Roblox surfaces it via window.open / iframe.src / anchor click.
            driver.execute_script("""
                window.__rblxLaunchUrl = null;

                var _ow = window.open;
                window.open = function(u) {
                    if (typeof u === 'string' && u.startsWith('roblox-player:')) {
                        window.__rblxLaunchUrl = u;
                        return null;
                    }
                    return _ow.apply(this, arguments);
                };

                var _iframeSrcDesc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'src');
                var _oc = document.createElement.bind(document);
                document.createElement = function(tag) {
                    var el = _oc(tag);
                    if (typeof tag === 'string' && tag.toLowerCase() === 'iframe') {
                        Object.defineProperty(el, 'src', {
                            set: function(v) {
                                if (typeof v === 'string' && v.startsWith('roblox-player:')) {
                                    window.__rblxLaunchUrl = v;
                                    return;
                                }
                                if (_iframeSrcDesc && _iframeSrcDesc.set) _iframeSrcDesc.set.call(this, v);
                            },
                            get: function() {
                                return _iframeSrcDesc && _iframeSrcDesc.get ? _iframeSrcDesc.get.call(this) : '';
                            }
                        });
                    }
                    return el;
                };

                document.addEventListener('click', function(e) {
                    var el = e.target;
                    for (var i = 0; i < 6 && el; i++, el = el.parentElement) {
                        if (el.tagName === 'A' && typeof el.href === 'string' && el.href.startsWith('roblox-player:')) {
                            e.preventDefault();
                            window.__rblxLaunchUrl = el.href;
                            break;
                        }
                    }
                }, true);
            """)

            # Locate the Join button on the friend's profile. The profile page's
            # Join button text is just "Join" so the text-matching fallback is
            # most likely to win here.
            find_js = r"""
                function findJoin() {
                    // 1) testid hooks
                    var t = document.querySelector(
                        '[data-testid="profile-join-button"],' +
                        '[data-testid="join-button"]'
                    );
                    if (t) return t;

                    // 2) class-based
                    var cls = document.querySelector(
                        'button[class*="ProfileJoinButton"],' +
                        'button[class*="profile-join" i],' +
                        'button[class*="JoinButton"]'
                    );
                    if (cls) return cls;

                    // 3) Text / aria-label / title — must be exactly "Join"
                    // to avoid matching "Join Group" / "Join Now" elsewhere
                    var clickables = Array.from(document.querySelectorAll(
                        'button, a, [role="button"]'
                    ));
                    for (var b of clickables) {
                        var txt = (b.textContent || '').trim();
                        var lbl = (b.getAttribute('aria-label') || '').trim();
                        if (txt === 'Join' || lbl === 'Join' || /^join$/i.test(lbl)) {
                            return b;
                        }
                    }
                    return null;
                }

                var btn = findJoin();
                if (!btn) return null;
                btn.setAttribute('data-ram-join-target', '1');
                btn.scrollIntoView({block: 'center', inline: 'center'});
                return {
                    tag: btn.tagName,
                    id: btn.id || '',
                    cls: (btn.className && btn.className.toString) ? btn.className.toString().slice(0, 120) : '',
                    testid: btn.getAttribute('data-testid') || '',
                    aria: btn.getAttribute('aria-label') || '',
                    title: btn.getAttribute('title') || '',
                    text: (btn.textContent || '').trim().slice(0, 60),
                    html: btn.outerHTML.slice(0, 300)
                };
            """

            print(f"[Profile Join] [{username}] Searching for Join button (polling up to 20 s)...")
            found_info = None
            for attempt in range(40):
                try:
                    found_info = driver.execute_script(find_js)
                except Exception as e:
                    print(f"[Profile Join] [{username}] JS error searching for button: {e}")
                    found_info = None
                if found_info:
                    print(f"[Profile Join] [{username}] Found Join button after {(attempt+1)*0.5:.1f}s")
                    break
                time.sleep(0.5)

            if not found_info:
                print(f"[Profile Join] [{username}] Could not find Join button on {friend_username}'s profile — friend may not be in a public game")
                return False

            print(f"[Profile Join] [{username}] Button details: tag={found_info['tag']} "
                  f"id={found_info['id']!r} testid={found_info['testid']!r} "
                  f"aria={found_info['aria']!r} text={found_info['text']!r}")

            click_method = None
            try:
                el = driver.find_element(By.CSS_SELECTOR, '[data-ram-join-target="1"]')
                ActionChains(driver).move_to_element(el).pause(0.2).click(el).perform()
                click_method = "ActionChains"
            except Exception as e:
                print(f"[Profile Join] [{username}] ActionChains click failed: {e}")
                try:
                    el = driver.find_element(By.CSS_SELECTOR, '[data-ram-join-target="1"]')
                    el.click()
                    click_method = "Selenium .click()"
                except Exception as e2:
                    print(f"[Profile Join] [{username}] Selenium .click() also failed: {e2}")
                    try:
                        driver.execute_script(
                            "document.querySelector('[data-ram-join-target=\"1\"]').click();"
                        )
                        click_method = "JS .click() (fallback)"
                    except Exception as e3:
                        print(f"[Profile Join] [{username}] JS fallback click failed: {e3}")
                        return False

            print(f"[Profile Join] [{username}] Join clicked via {click_method} — waiting up to 20 s for launch URL or Chrome protocol dialog...")

            launch_url = None
            dialog_dismissed = False
            for i in range(40):
                try:
                    launch_url = driver.execute_script("return window.__rblxLaunchUrl;")
                except Exception as e:
                    print(f"[Profile Join] [{username}] Error polling launch URL: {e}")
                    break
                if launch_url:
                    print(f"[Profile Join] [{username}] Launch URL captured after {(i+1)*0.5:.1f}s")
                    break

                if self._try_click_chrome_protocol_dialog(username):
                    dialog_dismissed = True
                    print(f"[Profile Join] [{username}] Chrome protocol dialog dismissed after {(i+1)*0.5:.1f}s")
                    break

                time.sleep(0.5)

            if launch_url:
                preview = launch_url[:120] + ("..." if len(launch_url) > 120 else "")
                print(f"[Profile Join] [{username}] URL: {preview}")
                print(f"[Profile Join] [{username}] Handing off to launcher ({launcher_preference})")
                RobloxAPI._execute_launch(launch_url, launcher_preference, custom_launcher_path)
                time.sleep(2)
                return True

            if dialog_dismissed:
                print(f"[Profile Join] [{username}] OS protocol handler is launching Roblox")
                time.sleep(3)
                return True

            print(f"[Profile Join] [{username}] Launch URL never captured and no protocol dialog seen — Join click did not trigger launch flow")
            return False

        except Exception as e:
            if orig_stderr is not None:
                sys.stderr = orig_stderr
            print(f"[Profile Join] [{username}] Error: {e}")
            traceback.print_exc()
            return False
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            try:
                shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception:
                pass

    def set_account_note(self, username, note):
        """Set or update note for an account"""
        if username not in self.accounts:
            print(f"[ERROR] Account '{username}' not found")
            return False

        self.accounts[username]['note'] = note
        self.save_accounts()
        print(f"[SUCCESS] Note updated for account: {username}")
        return True
    
    def get_account_note(self, username):
        """Get note for a specific account"""
        if username in self.accounts:
            return self.accounts[username].get('note', '')
        return ''
    
    def get_encryption_method(self):
        """Get current encryption method"""
        if not self.encryption_config.is_encryption_enabled():
            return None
        return self.encryption_config.get_encryption_method()
    
    def verify_password(self, password):
        """Verify password for password-based encryption"""
        if not self.encryption_config.is_encryption_enabled():
            return False
        
        method = self.encryption_config.get_encryption_method()
        if method != 'password':
            return False
        
        stored_hash = self.encryption_config.get_password_hash()
        entered_hash = hashlib.sha256(password.encode()).hexdigest()
        return entered_hash == stored_hash
    
    def get_roblox_version(self, channel="LIVE"):
        """Get current Roblox version from ClientSettings API"""
        url = f"https://clientsettings.roblox.com/v2/client-version/WindowsPlayer/channel/{channel}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                version = data.get("clientVersionUpload", "")
                if version:
                    return version
        except Exception as e:
            print(f"[ERROR] Failed to get Roblox version: {e}")
        
        return None
    
    def download_roblox_version(self, version, install_path, channel="LIVE", progress_callback=None):
        """Download and install a specific Roblox version"""
        
        HOST_PATH = "https://setup-aws.rbxcdn.com"
        BLOB_DIR = "/"
        
        EXTRACT_ROOTS = {
            "RobloxApp.zip": "",
            "redist.zip": "",
            "shaders.zip": "shaders/",
            "ssl.zip": "ssl/",
            "WebView2.zip": "",
            "WebView2RuntimeInstaller.zip": "WebView2RuntimeInstaller/",
            "content-avatar.zip": "content/avatar/",
            "content-configs.zip": "content/configs/",
            "content-fonts.zip": "content/fonts/",
            "content-sky.zip": "content/sky/",
            "content-sounds.zip": "content/sounds/",
            "content-textures2.zip": "content/textures/",
            "content-models.zip": "content/models/",
            "content-platform-fonts.zip": "PlatformContent/pc/fonts/",
            "content-platform-dictionaries.zip": "PlatformContent/pc/shared_compression_dictionaries/",
            "content-terrain.zip": "PlatformContent/pc/terrain/",
            "content-textures3.zip": "PlatformContent/pc/textures/",
            "extracontent-luapackages.zip": "ExtraContent/LuaPackages/",
            "extracontent-translations.zip": "ExtraContent/translations/",
            "extracontent-models.zip": "ExtraContent/models/",
            "extracontent-textures.zip": "ExtraContent/textures/",
            "extracontent-places.zip": "ExtraContent/places/"
        }
        
        APP_SETTINGS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Settings>
\t<ContentFolder>content</ContentFolder>
\t<BaseUrl>http://www.roblox.com</BaseUrl>
</Settings>
"""
        def log_progress(message):
            _silent_prefixes = ("DOWNLOAD_PROGRESS:", "EXTRACT_PROGRESS:", "EXTRACT_START:", "EXTRACT_COMPLETE:")
            if progress_callback:
                progress_callback(message)
            if not message.startswith(_silent_prefixes):
                print(message)
        
        try:
            if not version.startswith("version-"):
                version = f"version-{version}"
            
            if channel == "LIVE":
                channel_path = HOST_PATH
            else:
                channel_path = f"{HOST_PATH}/channel/{channel}"
            
            version_path = f"{channel_path}{BLOB_DIR}{version}-"
            manifest_url = f"{version_path}rbxPkgManifest.txt"
            
            log_progress(f"Fetching manifest...")
            response = requests.get(manifest_url, timeout=30)
            
            if response.status_code != 200:
                channel_path = f"{HOST_PATH}/channel/common"
                version_path = f"{channel_path}{BLOB_DIR}{version}-"
                manifest_url = f"{version_path}rbxPkgManifest.txt"
                response = requests.get(manifest_url, timeout=30)
            
            if response.status_code != 200:
                return False, "Failed to fetch manifest"
            
            manifest_text = response.text
            lines = [line.strip() for line in manifest_text.split('\n')]
            
            if not lines or lines[0] != "v0":
                return False, "Invalid manifest format"
            
            if "RobloxApp.zip" not in lines:
                return False, "Not a WindowsPlayer manifest"
            
            packages = [line for line in lines if line.endswith('.zip')]
            log_progress(f"Found {len(packages)} packages to download")
            
            install_path = Path(install_path)
            install_path.mkdir(parents=True, exist_ok=True)
            
            (install_path / "AppSettings.xml").write_text(APP_SETTINGS_XML)
            
            total = len(packages)
            for idx, package_name in enumerate(packages, 1):
                log_progress(f"[{idx}/{total}] Starting {package_name}...")
                
                package_url = f"{version_path}{package_name}"
                
                try:
                    response = requests.get(package_url, stream=True, timeout=60)
                    
                    if response.status_code != 200:
                        log_progress(f"Warning: Failed to download {package_name}, skipping...")
                        continue
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    chunks = []
                    last_reported_percent = -1
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            chunks.append(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                if int(percent) > last_reported_percent or downloaded >= total_size:
                                    last_reported_percent = int(percent)
                                    size_mb = downloaded / (1024 * 1024)
                                    total_mb = total_size / (1024 * 1024)
                                    log_progress(f"DOWNLOAD_PROGRESS:{package_name}:{percent:.1f}:{size_mb:.2f}:{total_mb:.2f}")
                    
                    package_data = b''.join(chunks)
                    
                except Exception as e:
                    log_progress(f"Error downloading {package_name}: {e}")
                    continue
                
                if package_name not in EXTRACT_ROOTS:
                    log_progress(f"Warning: {package_name} not in extract roots, skipping!")
                    continue
                
                extract_root = EXTRACT_ROOTS[package_name]
                
                log_progress(f"EXTRACT_START:{package_name}")
                
                try:
                    with zipfile.ZipFile(io.BytesIO(package_data)) as zf:
                        members = [m for m in zf.namelist() if not (m.endswith('/') or m.endswith('\\'))]
                        total_files = len(members)
                        
                        for file_idx, member in enumerate(members, 1):
                            fixed_path = member.replace('\\', '/')
                            extract_path = install_path / extract_root / fixed_path
                            extract_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            with zf.open(member) as source, open(extract_path, 'wb') as target:
                                target.write(source.read())
                            
                            if file_idx % 10 == 0 or file_idx == total_files:
                                percent = (file_idx / total_files) * 100
                                log_progress(f"EXTRACT_PROGRESS:{package_name}:{percent:.1f}")
                        
                        log_progress(f"EXTRACT_COMPLETE:{package_name}")
                except Exception as e:
                    log_progress(f"Error extracting {package_name}: {e}")
                    continue
            
            exe_path = install_path / "RobloxPlayerBeta.exe"
            if exe_path.exists():
                log_progress("Installation complete!")
                return True, str(install_path)
            else:
                log_progress("Warning: RobloxPlayerBeta.exe not found!")
                return False, "Installation incomplete, RobloxPlayerBeta.exe not found"
        
        except Exception as e:
            error_msg = f"Installation failed: {str(e)}"
            log_progress(error_msg)
            return False, error_msg
    
    def wipe_all_data(self):
        """Wipe all saved accounts, encryption config, and settings by deleting entire AccountManagerData folder"""
        
        try:
            if os.path.exists(self.data_folder):
                shutil.rmtree(self.data_folder)
                os.makedirs(self.data_folder, exist_ok=True)
            
            self.accounts.clear()
            self.encryption_config.reset_encryption()
            self.encryptor = None
            
            print("[SUCCESS] All data has been wiped")
        except Exception as e:
            print(f"[ERROR] Failed to wipe data: {str(e)}")
    
    def switch_encryption_method(self, new_method, password=None, salt=None):
        """Switch to a different encryption method"""
        if new_method not in ['hardware', 'password']:
            raise ValueError("Invalid encryption method. Must be 'hardware' or 'password'")
        
        current_method = self.get_encryption_method()
        if current_method == new_method:
            print("[INFO] Already using this encryption method")
            return
        
        current_data = self.accounts.copy()
        
        self.encryption_config.reset_encryption()
        
        if new_method == 'hardware':
            self.encryption_config.set_encryption_method('hardware')
            self.encryptor = HardwareEncryption()
        elif new_method == 'password':
            if password is None:
                raise ValueError("Password must be provided for password encryption")
            if salt is None:
                salt = os.urandom(32).hex()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            self.encryption_config.enable_password_encryption(salt, password_hash)
            self.encryptor = PasswordEncryption(password, salt)
        
        self.accounts = current_data
        self.save_accounts()
        print(f"[SUCCESS] Switched to {new_method} encryption")