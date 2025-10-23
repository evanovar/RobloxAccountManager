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
        self.temp_profile_dir = tempfile.mkdtemp(prefix="roblox_login_")
        return self.temp_profile_dir

    def cleanup_temp_profile(self):
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
        try:
            number = int(number)
            if 1 <= number <= len(self.accounts):
                return list(self.accounts.keys())[number - 1]
            return None
        except (ValueError, IndexError):
            return None

    def import_cookie_account(self, username, cookie):
        if username in self.accounts:
            del self.accounts[username]
            self.save_accounts()
            print(colored_text(f"[SUCCESS] Deleted account: {username}", Colors.GREEN))
            return True
        else:
            print(colored_text(f"[ERROR] Account '{username}' not found", Colors.RED))
            return False

    def get_account_cookie(self, username):
        cookie = self.get_account_cookie(username)
        if not cookie:
            print(colored_text(f"[ERROR] Account '{username}' not found", Colors.RED))
            return False

        return RobloxAPI.validate_account(username, cookie)

    def launch_home(self, username):
        if username not in self.accounts:
            print(colored_text(f"[ERROR] Account '{username}' not found", Colors.RED))
            return False

        cookie = self.accounts[username]['cookie']
        return RobloxAPI.launch_roblox(username, cookie, game_id, private_server_id)
