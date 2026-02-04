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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
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
                        self._migrate_accounts(decrypted_data)
                        return decrypted_data
                    except Exception as e:
                        raise ValueError(f"Decryption failed. Wrong password or corrupted data.")
                
                if isinstance(data, dict):
                    self._migrate_accounts(data)
                return data if isinstance(data, dict) else {}
            except ValueError:
                raise
            except Exception as e:
                print(f"[ERROR] Error loading accounts: {e}")
                return {}
        return {}
    
    def _migrate_accounts(self, accounts):
        """Migrate old account data to include new fields"""
        for username, account_data in accounts.items():
            if isinstance(account_data, dict):
                if 'note' not in account_data:
                    account_data['note'] = ''
    
    def save_accounts(self):
        """Save accounts to JSON file"""
        with open(self.accounts_file, 'w', encoding='utf-8') as f:
            if self.encryptor:
                encrypted_package = self.encryptor.encrypt_data(self.accounts)
                encrypted_data = {
                    'encrypted': True,
                    'data': encrypted_package
                }
                json.dump(encrypted_data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(self.accounts, f, indent=2, ensure_ascii=False)
    
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
        
        while time.time() - start_time < timeout:
            try:
                check_count += 1
                
                try:
                    current_url = driver.current_url.lower()
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
                    import json
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
            print(f"[ERROR] Account '{username}' not found")
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
    
    def launch_roblox(self, username, game_id, private_server_id="", launcher_preference="default", job_id=""):
        """Launch Roblox game with specified account"""
        if username not in self.accounts:
            print(f"[ERROR] Account '{username}' not found")
            return False
        
        cookie = self.accounts[username]['cookie']
        return RobloxAPI.launch_roblox(username, cookie, game_id, private_server_id, launcher_preference, job_id)
    
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