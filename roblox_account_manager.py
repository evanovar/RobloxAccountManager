import os
import json
import time
import tempfile
import subprocess
import threading
import random
import warnings
import ctypes
import base64
import hashlib
import platform
import msvcrt
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
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import PBKDF2

warnings.filterwarnings("ignore")
os.environ['WDM_LOG_LEVEL'] = '0'

ctypes.windll.kernel32.SetConsoleTitleW("Roblox Account Manager")

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'

def colored_text(text, color):
    return f"{color}{text}{Colors.RESET}"

def get_password_with_asterisks(prompt="Enter password: "):
    print(prompt, end='', flush=True)
    password = ""
    while True:
        char = msvcrt.getch()
        if char in (b'\r', b'\n'):
            print()
            break
        elif char == b'\x08':
            if len(password) > 0:
                password = password[:-1]
                print('\b \b', end='', flush=True)
        elif char == b'\x03':
            raise KeyboardInterrupt
        else:
            password += char.decode('utf-8', errors='ignore')
            print('*', end='', flush=True)
    return password

class HardwareEncryption:
    def __init__(self):
        self.machine_id = self._get_machine_id()
        self.key = self._derive_key_from_machine_id()
    
    def _get_machine_id(self):
        identifiers = []
        
        try:
            if platform.system() == "Windows":
                result = subprocess.check_output("wmic csproduct get uuid", shell=True)
                uuid = result.decode().split('\n')[1].strip()
                identifiers.append(uuid)
                
                result = subprocess.check_output("wmic cpu get processorid", shell=True)
                cpu_id = result.decode().split('\n')[1].strip()
                identifiers.append(cpu_id)
                
                result = subprocess.check_output("wmic baseboard get serialnumber", shell=True)
                board_serial = result.decode().split('\n')[1].strip()
                identifiers.append(board_serial)
            else:
                identifiers.append(platform.node())
                identifiers.append(str(os.getuid()) if hasattr(os, 'getuid') else "0")
        except:
            identifiers.append(platform.node())
            identifiers.append(platform.machine())
        
        machine_string = "-".join(identifiers)
        return hashlib.sha256(machine_string.encode()).hexdigest()
    
    def _derive_key_from_machine_id(self):
        salt = b'roblox_account_manager_salt_v1'
        key = PBKDF2(self.machine_id, salt, dkLen=32, count=100000)
        return key
    
    def encrypt_data(self, data):
        if isinstance(data, dict):
            data = json.dumps(data, indent=2, ensure_ascii=False)
        
        data_bytes = data.encode('utf-8')
        
        cipher = AES.new(self.key, AES.MODE_GCM)
        nonce = cipher.nonce
        
        ciphertext, tag = cipher.encrypt_and_digest(data_bytes)
        
        encrypted_package = {
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8')
        }
        
        return encrypted_package
    
    def decrypt_data(self, encrypted_package):
        try:
            nonce = base64.b64decode(encrypted_package['nonce'])
            tag = base64.b64decode(encrypted_package['tag'])
            ciphertext = base64.b64decode(encrypted_package['ciphertext'])
            
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
            
            data_bytes = cipher.decrypt_and_verify(ciphertext, tag)
            
            data_string = data_bytes.decode('utf-8')
            
            try:
                return json.loads(data_string)
            except:
                return data_string
                
        except Exception as e:
            raise Exception(f"Decryption failed. This file may have been encrypted on a different machine. Error: {str(e)}")

class PasswordEncryption:
    def __init__(self, password, salt=None):
        if salt is None:
            self.salt = get_random_bytes(32)
        else:
            if isinstance(salt, str):
                self.salt = base64.b64decode(salt)
            else:
                self.salt = salt
        
        self.key = self._derive_key_from_password(password)
    
    def _derive_key_from_password(self, password):
        key = PBKDF2(password, self.salt, dkLen=32, count=100000)
        return key
    
    def get_salt_b64(self):
        return base64.b64encode(self.salt).decode('utf-8')
    
    def encrypt_data(self, data):
        if isinstance(data, dict):
            data = json.dumps(data, indent=2, ensure_ascii=False)
        
        data_bytes = data.encode('utf-8')
        
        cipher = AES.new(self.key, AES.MODE_GCM)
        nonce = cipher.nonce
        
        ciphertext, tag = cipher.encrypt_and_digest(data_bytes)
        
        encrypted_package = {
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8')
        }
        
        return encrypted_package
    
    def decrypt_data(self, encrypted_package):
        try:
            nonce = base64.b64decode(encrypted_package['nonce'])
            tag = base64.b64decode(encrypted_package['tag'])
            ciphertext = base64.b64decode(encrypted_package['ciphertext'])
            
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
            
            data_bytes = cipher.decrypt_and_verify(ciphertext, tag)
            
            data_string = data_bytes.decode('utf-8')
            
            try:
                return json.loads(data_string)
            except:
                return data_string
                
        except Exception as e:
            raise Exception(f"Decryption failed. Password may be incorrect. Error: {str(e)}")

class EncryptionConfig:
    def __init__(self, config_file="encryption_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def is_encryption_enabled(self):
        return self.config.get('encryption_enabled', False)
    
    def get_encryption_method(self):
        return self.config.get('encryption_method', None)
    
    def get_salt(self):
        return self.config.get('salt', None)
    
    def get_password_hash(self):
        return self.config.get('password_hash', None)
    
    def enable_hardware_encryption(self):
        self.config['encryption_enabled'] = True
        self.config['encryption_method'] = 'hardware'
        self.save_config()
    
    def enable_password_encryption(self, salt, password_hash):
        self.config['encryption_enabled'] = True
        self.config['encryption_method'] = 'password'
        self.config['salt'] = salt
        self.config['password_hash'] = password_hash
        self.save_config()
    
    def disable_encryption(self):
        self.config['encryption_enabled'] = False
        self.config['encryption_method'] = None
        if 'salt' in self.config:
            del self.config['salt']
        self.save_config()

class RobloxAccountManager:
    def __init__(self, password=None):
        self.accounts_file = "saved_accounts.json"
        self.encryption_config = EncryptionConfig()
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
                        return decrypted_data
                    except Exception as e:
                        raise ValueError(f"Decryption failed. Wrong password or corrupted data.")
                
                return data if isinstance(data, dict) else {}
            except ValueError:
                raise
            except Exception as e:
                print(colored_text(f"[WARNING] Error loading accounts: {e}", Colors.YELLOW))
                return {}
        return {}
    
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
            print(colored_text("[SUCCESS] Detection script injected successfully", Colors.GREEN))
        except Exception as e:
            print(colored_text(f"[WARNING] Warning: Could not inject detection script: {e}", Colors.YELLOW))
        
        start_time = time.time()
        last_debug_time = 0
        
        while time.time() - start_time < timeout:
            try:
                result = driver.execute_script("return window.ultraFastDetection;")
                
                if result and result.get('detected'):
                    method = result.get('method', 'url_only')
                    print(colored_text(f"[SUCCESS] LOGIN DETECTED! Method: {method} - Closing browser instantly...", Colors.GREEN))
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
                            print(colored_text("[SUCCESS] LOGIN DETECTED via manual URL check!", Colors.GREEN))
                            return True
                                
                    except Exception as e:
                        print(f"   Debug error: {e}")
                
                time.sleep(0.025)
                
            except WebDriverException:
                return False
        
        print(colored_text("[WARNING] Login timeout. Please try again.", Colors.YELLOW))
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
                    print(colored_text(f"[SUCCESS] Username detected from page: {username}", Colors.GREEN))
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
            print(colored_text(f"[ERROR] Account '{username}' not found", Colors.RED))
            return False
        
        cookie = self.accounts[username]['cookie']
        
        print(f"🎮 Getting authentication ticket for {username}...")
        auth_ticket = self.get_auth_ticket(cookie)
        
        if not auth_ticket:
            print(colored_text("[ERROR] Failed to get authentication ticket", Colors.RED))
            return False
        
        print(colored_text("[SUCCESS] Got authentication ticket!", Colors.GREEN))
        
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
            print(colored_text("[SUCCESS] Roblox launched successfully!", Colors.GREEN))
            return True
        except Exception as e:
            print(colored_text(f"[ERROR] Failed to launch Roblox: {e}", Colors.RED))
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
                    
                    print(colored_text(f"[SUCCESS] Successfully added account: {username}", Colors.GREEN))
                    return True
                else:
                    print(colored_text("[ERROR] Failed to extract account information", Colors.RED))
                    return False
            else:
                print(colored_text("[ERROR] Login was not completed", Colors.RED))
                return False
                
        except Exception as e:
            print(colored_text(f"[ERROR] Error during account addition: {e}", Colors.RED))
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
            print(colored_text(f"[SUCCESS] Deleted account: {username}", Colors.GREEN))
            return True
        else:
            print(colored_text(f"[ERROR] Account '{username}' not found", Colors.RED))
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
            print(colored_text(f"[ERROR] Account '{username}' not found", Colors.RED))
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

def setup_encryption():
    """First-time encryption setup"""
    encryption_config = EncryptionConfig()
    
    if not encryption_config.is_encryption_enabled():
        os.system('cls' if os.name == 'nt' else 'clear')
        print("="*60)
        print("🔐 FIRST-TIME SETUP: ENCRYPTION CONFIGURATION")
        print("="*60)
        print()
        print("To protect your account data, please choose an encryption method:")
        print()
        print("1. Default Encryption (Hardware-Based)")
        print("   • Automatic encryption using your computer's hardware")
        print("   • No password needed")
        print("   • Data ONLY works on THIS computer")
        print("   • Cannot be transferred or backed up to cloud")
        print()
        print("2. Password Encryption (Recommended, Portable)")
        print("   • Encrypt with a password you create")
        print("   • Can backup to cloud (Google Drive, Dropbox, etc.)")
        print("   • Works on any computer with the password")
        print("   • MUST remember your password - no recovery!")
        print()
        print("-" * 60)
        
        while True:
            choice = input("Select encryption method (1 or 2): ").strip()
            
            if choice == '1':
                encryption_config.enable_hardware_encryption()
                print()
                print(colored_text("[SUCCESS] Hardware-based encryption enabled!", Colors.GREEN))
                print("🔒 Your accounts will be encrypted automatically.")
                print()
                input("Press Enter to continue...")
                os.system('cls' if os.name == 'nt' else 'clear')
                return None
                
            elif choice == '2':
                os.system('cls' if os.name == 'nt' else 'clear')
                print("="*60)
                print("🔐 PASSWORD ENCRYPTION SETUP")
                print("="*60)
                print()
                print(colored_text("[WARNING] IMPORTANT WARNING", Colors.YELLOW))
                print("PLEASE SAVE YOUR PASSWORD. DO NOT FORGET IT!")
                print("There is NO password recovery method.")
                print("Lost password = permanent data loss!")
                print()
                
                while True:
                    try:
                        password1 = get_password_with_asterisks("Enter your password: ")
                    except KeyboardInterrupt:
                        print()
                        return setup_encryption()
                    
                    if len(password1) < 8:
                        print(colored_text("[WARNING] Password must be at least 8 characters long.", Colors.YELLOW))
                        print()
                        continue
                    
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print("="*60)
                    print("🔐 PASSWORD ENCRYPTION SETUP")
                    print("="*60)
                    print()
                    
                    try:
                        password2 = get_password_with_asterisks("Confirm your password: ")
                    except KeyboardInterrupt:
                        print()
                        return setup_encryption()
                    
                    if password1 == password2:
                        temp_encryptor = PasswordEncryption(password1)
                        salt_b64 = temp_encryptor.get_salt_b64()
                        password_hash = hashlib.sha256(password1.encode()).hexdigest()
                        encryption_config.enable_password_encryption(salt_b64, password_hash)
                        
                        os.system('cls' if os.name == 'nt' else 'clear')
                        print()
                        print(colored_text("[SUCCESS] Password encryption enabled successfully!", Colors.GREEN))
                        print("🔒 Your accounts will be encrypted with your password.")
                        print()
                        print(colored_text("[WARNING] Remember: Your password is NOT stored anywhere.", Colors.YELLOW))
                        print("   You will need to enter it every time you start the app.")
                        print()
                        input("Press Enter to continue...")
                        os.system('cls' if os.name == 'nt' else 'clear')
                        return password1
                    else:
                        os.system('cls' if os.name == 'nt' else 'clear')
                        print()
                        print(colored_text("[ERROR] Passwords do not match!", Colors.RED))
                        print(colored_text("[WARNING] Returning to encryption setup...", Colors.YELLOW))
                        print()
                        input("Press Enter to continue...")
                        return setup_encryption()
                        
            else:
                print(colored_text("[WARNING] Invalid choice. Please enter 1 or 2.", Colors.YELLOW))

def main():
    password = setup_encryption()
    
    encryption_config = EncryptionConfig()
    
    if encryption_config.is_encryption_enabled() and encryption_config.get_encryption_method() == 'password':
        if password is None:
            print()
            print("🔐 Password-encrypted accounts detected")
            print()
            try:
                password = get_password_with_asterisks("Enter your password to unlock: ")
            except KeyboardInterrupt:
                print()
                print(colored_text("[ERROR] Cancelled by user", Colors.RED))
                return
            print()
    
    try:
        manager = RobloxAccountManager(password=password)
    except ValueError as e:
        print()
        print(colored_text("[ERROR] Password is invalid. Please try again.", Colors.RED))
        print()
        input("Press Enter to exit...")
        return
    except Exception as e:
        print()
        print(colored_text(f"[ERROR] Failed to initialize: {e}", Colors.RED))
        print()
        input("Press Enter to exit...")
        return
    
    encryption_status = ""
    if manager.encryption_config.is_encryption_enabled():
        method = manager.encryption_config.get_encryption_method()
        if method == 'hardware':
            encryption_status = " 🔒 [Hardware Encrypted]"
        elif method == 'password':
            encryption_status = " 🔐 [Password Encrypted]"
    
    while True:
        print("\n" + "="*50)
        print(f"🚀 ROBLOX ACCOUNT MANAGER{encryption_status}")
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
