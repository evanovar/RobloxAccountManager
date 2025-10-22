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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from .encryption import HardwareEncryption, PasswordEncryption, EncryptionConfig
from .roblox_api import RobloxAPI
from utils.ui_helpers import Colors, colored_text


class RobloxAccountManager:
    """Main account manager class"""
    
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
            print(colored_text(f"Error setting up Chrome driver: {e}", Colors.RED))
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
                        print(colored_text(f"   Debug error: {e}", Colors.RED))
                
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
                username = RobloxAPI.get_username_from_api(roblosecurity_cookie)
            
            if not username:
                username = "Unknown"
            
            return username, roblosecurity_cookie
            
        except Exception as e:
            print(colored_text(f"Error extracting user info: {e}", Colors.RED))
            return None, None
    
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
        
        print("\n📋 Saved Accounts:")
        print("-" * 50)
        for i, (username, data) in enumerate(self.accounts.items(), 1):
            added_date = data.get('added_date', 'Unknown')
            print(f"{i}. {username} (Added: {added_date})")
    
    def get_account_by_number(self, number):
        """Get account username by its numbered position"""
        try:
            number = int(number)
            if 1 <= number <= len(self.accounts):
                return list(self.accounts.keys())[number - 1]
            return None
        except (ValueError, IndexError):
            return None
    
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
        """Validate if an account's cookie is still valid"""
        cookie = self.get_account_cookie(username)
        if not cookie:
            print(colored_text(f"[ERROR] Account '{username}' not found", Colors.RED))
            return False
        
        return RobloxAPI.validate_account(username, cookie)
    
    def launch_roblox(self, username, game_id, private_server_id=""):
        """Launch Roblox game with specified account"""
        if username not in self.accounts:
            print(colored_text(f"[ERROR] Account '{username}' not found", Colors.RED))
            return False
        
        cookie = self.accounts[username]['cookie']
        return RobloxAPI.launch_roblox(username, cookie, game_id, private_server_id)
