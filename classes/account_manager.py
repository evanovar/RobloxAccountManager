"""
Account Manager class
Handles account storage, browser automation, and account management
"""

import os
import json
import time
import tempfile
import hashlib
import shutil
import traceback
import threading
import requests

from .encryption import HardwareEncryption, PasswordEncryption, EncryptionConfig
from .operation_result import OperationResult
from .roblox_api import RobloxAPI
from utils.app_paths import get_data_dir

class RobloxAccountManager:
    
    def __init__(self, password=None):
        self.data_folder = get_data_dir()
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
        
        self.accounts_file = os.path.join(self.data_folder, "saved_accounts.json")
        self.encryption_config = EncryptionConfig(os.path.join(self.data_folder, "encryption_config.json"))
        self.encryptor = None
        self.secure_settings = {}
        self._entered_password_hash = None
        self._accounts_lock = threading.RLock()
        self._browser_setup_lock = threading.Lock()
        
        if self.encryption_config.is_encryption_enabled():
            method = self.encryption_config.get_encryption_method()
            if method == 'hardware':
                self.encryptor = HardwareEncryption()
            elif method == 'password':
                if password is None:
                    raise ValueError("Password required for password-based encryption")
                self._entered_password_hash = hashlib.sha256(password.encode()).hexdigest()
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
                        self._repair_password_hash_if_needed()
                        return accounts
                    except Exception:
                        raise ValueError("Decryption failed. Wrong password or corrupted data.")
                
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

    def _repair_password_hash_if_needed(self):
        if not self._entered_password_hash:
            return
        stored_hash = self.encryption_config.get_password_hash()
        if stored_hash == self._entered_password_hash:
            return
        if self.encryption_config.get_encryption_method() != 'password':
            return
        self.encryption_config.config['password_hash'] = self._entered_password_hash
        try:
            self.encryption_config.save_config()
        except Exception:
            pass

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
        temp_file = self.accounts_file + ".tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                if self.encryptor:
                    encrypted_package = self.encryptor.encrypt_data(payload)
                    encrypted_data = {
                        'encrypted': True,
                        'data': encrypted_package
                    }
                    json.dump(encrypted_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, self.accounts_file)
        except Exception as e:
            print(f"[WARNING] Safe atomic save failed: {e}. Falling back to original direct write.")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            # Original direct write fallback
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

    def create_temp_profile(self):
        # Create a temporary Chrome profile directory.
        self.temp_profile_dir = tempfile.mkdtemp(prefix="roblox_login_")
        return self.temp_profile_dir
    
    def cleanup_temp_profile(self, profile_dir=None):
        # Clean one temporary browser profile without touching active profiles.
        target_dir = profile_dir or self.temp_profile_dir
        if target_dir and os.path.exists(target_dir):
            try:
                shutil.rmtree(target_dir)
            except:
                pass
    
    def setup_chrome_driver(self, browser_path=None):
        print(f"[INFO] setup_chrome_driver called with browser_path: {browser_path}")
        profile_dir = self.create_temp_profile()
        # to make startup faster
        from selenium import webdriver
        from selenium.common.exceptions import SessionNotCreatedException
        from selenium.common.exceptions import WebDriverException
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager

        if browser_path and not os.path.isfile(browser_path):
            self.cleanup_temp_profile(profile_dir)
            return OperationResult.failure(
                "BROWSER_EXECUTABLE_MISSING",
                "Browser Executable Missing",
                "The selected browser executable could not be found.",
                detail=f"Expected path: {browser_path}",
            )
        
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
            with self._browser_setup_lock:
                if browser_path and "chromium" in browser_path.lower():
                    chromedriver_path = os.path.join(
                        os.path.dirname(browser_path),
                        "chromedriver.exe",
                    )
                    if os.path.exists(chromedriver_path):
                        print(f"[INFO] Using bundled chromedriver: {chromedriver_path}")
                        service = Service(chromedriver_path, log_path=os.devnull)
                    else:
                        self.cleanup_temp_profile(profile_dir)
                        return OperationResult.failure(
                            "BROWSER_DRIVER_MISSING",
                            "Chromium Driver Missing",
                            "The Chromium installation is incomplete. Download Chromium again.",
                            detail=f"Missing driver: {chromedriver_path}",
                        )
                else:
                    service = Service(ChromeDriverManager().install(), log_path=os.devnull)

                driver = webdriver.Chrome(service=service, options=chrome_options)
                driver._ram_profile_dir = profile_dir
                driver.set_page_load_timeout(120)
                driver.implicitly_wait(10)
                driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', "
                    "{get: () => undefined})"
                )
                return OperationResult.success(data=driver)
        except SessionNotCreatedException as exc:
            self.cleanup_temp_profile(profile_dir)
            print(f"[ERROR] Browser and driver versions do not match: {exc}")
            return OperationResult.failure(
                "BROWSER_DRIVER_MISMATCH",
                "Browser Driver Version Mismatch",
                "The browser and ChromeDriver versions do not match.",
                detail=str(exc),
            )
        except WebDriverException as exc:
            self.cleanup_temp_profile(profile_dir)
            print(f"[ERROR] Selenium could not start the browser: {exc}")
            return OperationResult.failure(
                "BROWSER_START_FAILED",
                "Browser Could Not Start",
                "The selected browser could not be opened.",
                detail=str(exc),
            )
        except PermissionError as exc:
            self.cleanup_temp_profile(profile_dir)
            print(f"[ERROR] Browser startup permission denied: {exc}")
            return OperationResult.failure(
                "BROWSER_PERMISSION_DENIED",
                "Browser Start Blocked",
                "Windows denied permission to start the browser.",
                detail=str(exc),
            )
        except Exception as e:
            self.cleanup_temp_profile(profile_dir)
            print(f"[ERROR] Error setting up Chrome driver: {e}")
            traceback.print_exc()
            return OperationResult.failure(
                "BROWSER_SETUP_FAILED",
                "Browser Setup Failed",
                "The browser could not be prepared. Check the Console tab or session log.",
                detail=f"{type(e).__name__}: {e}",
            )
    
    def wait_for_login(self, driver, timeout=300):
        from selenium.common.exceptions import WebDriverException
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
                window.browserDetect.debug.push('DETECTED via URL! Page: ' + url);
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
        # Extract the username, cookie, user ID, password, and avatar URL.
        try:
            roblosecurity_cookie = None
            cookies = driver.get_cookies()
            
            for cookie in cookies:
                if cookie['name'] == '.ROBLOSECURITY':
                    roblosecurity_cookie = cookie['value']
                    break
            
            if not roblosecurity_cookie:
                return None, None, None, None, ""
            
            captured_password = ""
            try:
                captured_password = driver.execute_script("""
                    return sessionStorage.getItem('_ram_pw') || 
                           (window.browserDetect ? window.browserDetect.password : '') || 
                           '';
                """)
                if captured_password:
                    print("[INFO] Password captured")
                    driver.execute_script("sessionStorage.removeItem('_ram_pw');")
            except Exception as e:
                print(f"[ERROR] Password capture failed: {e}")
            
            print("[INFO] Fetching account info from browser...")
            try:
                account_json = driver.execute_script("""
                    var infoPromise = fetch('/my/account/json')
                        .then(r => r.json())
                        .then(data => JSON.stringify(data))
                        .catch(() => null);

                    var avatarPromise = infoPromise
                        .then(raw => {
                            if (!raw) return null;
                            var uid = JSON.parse(raw).UserId;
                            if (!uid) return null;
                            return fetch(
                                'https://thumbnails.roblox.com/v1/users/avatar-headshot'
                                + '?userIds=' + uid
                                + '&size=100x100&format=Png&isCircular=true'
                            ).then(r => r.json())
                             .then(d => (d.data && d.data[0]) ? d.data[0].imageUrl : null)
                             .catch(() => null);
                        });

                    return Promise.all([infoPromise, avatarPromise])
                        .then(results => JSON.stringify({info: results[0], avatar: results[1]}))
                        .catch(() => null);
                """)

                if account_json:
                    combined    = json.loads(account_json)
                    account_data = json.loads(combined.get("info") or "{}")
                    avatar_url   = combined.get("avatar") or ""
                    username = account_data.get("Name", "Unknown")
                    user_id  = account_data.get("UserId", 0)
                    print(f"[SUCCESS] Username: {username} (ID: {user_id})")
                    return username, roblosecurity_cookie, user_id, captured_password, avatar_url
            except Exception as e:
                print(f"[ERROR] Browser fetch failed: {e}, falling back to API")
            
            print("[INFO] Getting username from API...")
            try:
                username, user_id = RobloxAPI.get_user_info_from_api(roblosecurity_cookie)
            except Exception as e:
                print(f"[WARNING] get_user_info_from_api failed: {e}. Falling back to legacy method.")
                username = RobloxAPI.get_username_from_api(roblosecurity_cookie)
                user_id = 0

            if not username:
                username = "Unknown"

            print(f"[SUCCESS] Username: {username} (ID: {user_id})")
            return username, roblosecurity_cookie, user_id, captured_password, ""

        except Exception as e:
            print(f"[ERROR] Error extracting user info: {e}")
            return None, None, None, None, ""
    
    def add_account(self, amount=1, website="https://www.roblox.com/login", javascript="", javascript_list=None, browser_path=None, password_list=None, window_slot=None, window_slot_count=None):
        # Add accounts through one or more browser instances.
        # javascript_list and password_list map each value to the same browser index.
        if javascript_list:
            amount = len(javascript_list)

        if amount > 10:
            print("[WARNING] The maximum instance is only 10. Setting to 10.")
            amount = 10
            javascript_list = javascript_list[:10] if javascript_list else javascript_list
            password_list = password_list[:10] if password_list else password_list
        
        success_count = 0
        drivers = []
        instance_passwords = []
        failures: list[OperationResult] = []
        failure_lock = threading.Lock()
        
        try:
            print(f"[INFO] Launching {amount} browser instance(s)...")
            
            for i in range(amount):
                setup_result = self.setup_chrome_driver(browser_path)
                if not setup_result:
                    print(
                        f"[ERROR] Failed to setup browser for instance "
                        f"{i + 1}: {setup_result.code}"
                    )
                    failures.append(setup_result)
                    continue
                driver = setup_result.data
                
                window_width = 500
                window_height = 600
                
                screen_width = driver.execute_script("return screen.width;")
                screen_height = driver.execute_script("return screen.height;")
                
                position_count = window_slot_count or amount
                position_index = window_slot if window_slot is not None else i
                grid_cols = min(3, position_count)
                grid_rows = (position_count + grid_cols - 1) // grid_cols
                
                col = position_index % grid_cols
                row = position_index // grid_cols
                
                x = col * (screen_width // grid_cols) + 10
                y = row * ((screen_height - 100) // grid_rows) + 10
                
                driver.set_window_position(x, y)
                driver.set_window_size(window_width, window_height)
                
                drivers.append(driver)
                instance_passwords.append(
                    password_list[i]
                    if password_list and i < len(password_list)
                    else ""
                )
                
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
                    
                    instance_script = javascript_list[i] if javascript_list else javascript
                    if instance_script:
                        print(f"[INFO] Executing Javascript for instance {i + 1}...")
                        try:
                            driver.execute_script("return document.readyState")
                            driver.execute_script(instance_script)
                            print(f"[SUCCESS] Javascript executed for instance {i + 1}")
                        except Exception as js_error:
                            print(f"[WARNING] Javascript execution failed for instance {i + 1}: {js_error}")
                    
                except Exception as e:
                    print(f"[ERROR] Error opening browser for instance {i + 1}: {e}")
                    traceback.print_exc()
                    if drivers and drivers[-1] is driver:
                        drivers.pop()
                        instance_passwords.pop()
                    profile_dir = getattr(driver, "_ram_profile_dir", None)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    self.cleanup_temp_profile(profile_dir)
                    failures.append(OperationResult.failure(
                        "BROWSER_NAVIGATION_FAILED",
                        "Roblox Login Could Not Open",
                        "The browser opened but the Roblox login page could not be loaded.",
                        detail=f"{type(e).__name__}: {e}",
                        retryable=True,
                    ))
            
            print(f"[INFO] All {len(drivers)} browser(s) opened. Waiting for logins...")

            def wait_for_instance(driver_index):
                driver = drivers[driver_index]
                try:
                    if self.wait_for_login(driver):
                        username, cookie, user_id, password, avatar_url = self.extract_user_info(driver)

                        if username and cookie:
                            saved_password = password or instance_passwords[driver_index]
                            with self._accounts_lock:
                                self.accounts[username] = {
                                    'username':   username,
                                    'cookie':     cookie,
                                    'user_id':    user_id or 0,
                                    'password':   saved_password or '',
                                    'added_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                                    'note':       '',
                                    'avatar_url': avatar_url or '',
                                    'cookie_valid': True,
                                }
                                self.save_accounts()

                            print(f"[SUCCESS] Successfully added account: {username}")
                            nonlocal success_count
                            success_count += 1
                        else:
                            print(f"[ERROR] Failed to extract account information for instance {driver_index + 1}")
                            with failure_lock:
                                failures.append(OperationResult.failure(
                                    "ACCOUNT_EXTRACTION_FAILED",
                                    "Account Information Missing",
                                    "The login completed, but the account information could not be read.",
                                ))
                    else:
                        print(f"[ERROR] Login timeout for instance {driver_index + 1}")
                        with failure_lock:
                            failures.append(OperationResult.failure(
                                "BROWSER_LOGIN_TIMEOUT",
                                "Browser Login Timed Out",
                                "The Roblox browser login did not finish within five minutes.",
                                retryable=True,
                            ))
                except Exception as e:
                    print(f"[ERROR] Error waiting for login on instance {driver_index + 1}: {e}")
                    with failure_lock:
                        failures.append(OperationResult.failure(
                            "BROWSER_LOGIN_FAILED",
                            "Browser Login Failed",
                            "The browser login could not be completed.",
                            detail=f"{type(e).__name__}: {e}",
                        ))
                finally:
                    profile_dir = getattr(driver, "_ram_profile_dir", None)
                    try:
                        driver.quit()
                    except:
                        pass
                    self.cleanup_temp_profile(profile_dir)
            
            threads = []
            for i in range(len(drivers)):
                thread = threading.Thread(
                    target=wait_for_instance,
                    args=(i,),
                    name=f"browser-login-{i + 1}",
                )
                thread.start()
                threads.append(thread)
            
            for thread in threads:
                thread.join()
            
            if success_count:
                return OperationResult.success(
                    f"Added {success_count} account(s).",
                    data={"success_count": success_count},
                )
            if failures:
                return failures[0]
            return OperationResult.failure(
                "BROWSER_DID_NOT_OPEN",
                "Browser Did Not Open",
                "No browser instance could be opened.",
            )
                
        except Exception as e:
            print(f"[ERROR] Error during account addition: {e}")
            for driver in drivers:
                profile_dir = getattr(driver, "_ram_profile_dir", None)
                try:
                    driver.quit()
                except:
                    pass
                self.cleanup_temp_profile(profile_dir)
            return OperationResult.failure(
                "ACCOUNT_BROWSER_FAILED",
                "Browser Account Login Failed",
                "The browser account login could not be completed.",
                detail=f"{type(e).__name__}: {e}",
            )
    
    def import_cookie_account_result(self, cookie):
        if not cookie:
            print("[ERROR] Cookie is required")
            return OperationResult.failure(
                "COOKIE_MISSING",
                "Cookie Missing",
                "Paste a Roblox security cookie before importing.",
            )
        
        cookie = cookie.strip()
        
        if not cookie.startswith('_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|'):
            print("[ERROR] Invalid cookie format")
            return OperationResult.failure(
                "COOKIE_FORMAT_INVALID",
                "Invalid Cookie Format",
                "The provided text is not a Roblox security cookie.",
            )
        
        try:
            try:
                username, user_id_val = RobloxAPI.get_user_info_from_api(cookie)
            except Exception as e:
                print(f"[WARNING] get_user_info_from_api failed: {e}. Falling back to legacy method.")
                username = RobloxAPI.get_username_from_api(cookie)
                user_id_val = 0

            if not username or username == "Unknown":
                print("[ERROR] Failed to get username from cookie")
                return OperationResult.failure(
                    "COOKIE_ACCOUNT_LOOKUP_FAILED",
                    "Account Could Not Be Identified",
                    "Roblox did not return an account for this cookie.",
                    retryable=True,
                )

            validation = RobloxAPI.validate_cookie(cookie)
            if not validation:
                print(
                    f"[ERROR] Cookie validation failed: "
                    f"{validation.code}"
                )
                return validation

            user_id   = user_id_val
            avatar_url = ""
            try:
                uid = user_id if user_id else RobloxAPI.get_user_id_from_username(username)
                if uid:
                    user_id = uid
                    api = (
                        "https://thumbnails.roblox.com/v1/users/avatar-headshot"
                        f"?userIds={uid}&size=100x100&format=Png&isCircular=true"
                    )
                    r = requests.get(api, timeout=6)
                    d = r.json()
                    if d.get("data") and d["data"][0].get("imageUrl"):
                        avatar_url = d["data"][0]["imageUrl"]
            except Exception:
                pass

            self.accounts[username] = {
                'username':   username,
                'cookie':     cookie,
                'user_id':    user_id,
                'added_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'note':       '',
                'avatar_url': avatar_url,
                'cookie_valid': True,
            }
            self.save_accounts()

            print(f"[SUCCESS] Successfully imported account: {username}")
            return OperationResult.success(
                f"Successfully imported account: {username}",
                data=username,
            )

        except Exception as e:
            print(f"[ERROR] Failed to import account: {e}")
            return OperationResult.failure(
                "COOKIE_IMPORT_FAILED",
                "Cookie Import Failed",
                "The account could not be imported. Check the Console tab or session log.",
                detail=f"{type(e).__name__}: {e}",
            )

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
    
    def launch_roblox(self, username, game_id="", private_server_id="", launcher_preference="default", job_id="", custom_launcher_path=""):
        """Launch Roblox game with specified account"""
        if username not in self.accounts:
            print(f"[ERROR] Account '{username}' not found")
            return OperationResult.failure(
                "ACCOUNT_NOT_FOUND",
                "Account Not Found",
                f"The account '{username}' is no longer available.",
            )

        cookie = self.accounts[username]['cookie']
        launched = RobloxAPI.launch_roblox(
            username,
            cookie,
            game_id,
            private_server_id,
            launcher_preference,
            job_id,
            custom_launcher_path,
        )
        if launched and self.accounts[username].get('cookie_valid') is not True:
            with self._accounts_lock:
                self.accounts[username]['cookie_valid'] = True
                self.accounts[username].pop('valid', None)
                self.save_accounts()
        return launched

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
    
    def switch_encryption_method(self, new_method, password=None, salt=None):
        """Switch to a different encryption method, re-encrypting (or decrypting) saved_accounts.json in place"""
        if new_method not in ('hardware', 'password', 'none'):
            raise ValueError("Invalid encryption method. Must be 'hardware', 'password', or 'none'")

        current_method = self.get_encryption_method() or 'none'
        if current_method == new_method:
            print("[INFO] Already using this encryption method")
            return

        current_data = self.accounts.copy()

        self.encryption_config.reset_encryption()

        if new_method == 'hardware':
            self.encryption_config.set_encryption_method('hardware')
            self.encryptor = HardwareEncryption()
            self._entered_password_hash = None
        elif new_method == 'password':
            if password is None:
                raise ValueError("Password must be provided for password encryption")
            if salt is None:
                salt = os.urandom(32).hex()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            self.encryption_config.enable_password_encryption(salt, password_hash)
            self._entered_password_hash = password_hash
            self.encryptor = PasswordEncryption(password, salt)
        else:  # 'none'
            self.encryption_config.disable_encryption()
            self.encryptor = None
            self._entered_password_hash = None

        self.accounts = current_data
        self.save_accounts()
        print(f"[SUCCESS] Encryption method switched to '{new_method}' and saved_accounts.json re-encrypted")
        self.save_accounts()
        print(f"[SUCCESS] Switched to {new_method} encryption")
