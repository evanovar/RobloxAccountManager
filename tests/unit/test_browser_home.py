import threading
import unittest
from unittest.mock import Mock, patch

from classes.account_manager import RobloxAccountManager
from classes.operation_result import OperationResult
from features import account_actions


class BrowserHomeTests(unittest.TestCase):
    def setUp(self):
        self.manager = RobloxAccountManager.__new__(RobloxAccountManager)
        self.manager._accounts_lock = threading.RLock()
        self.manager.accounts = {"alice": {"cookie": "synthetic-test-cookie"}}
        self.driver = Mock()
        self.driver._ram_profile_dir = "temporary-profile"
        self.driver.get.side_effect = self.navigate
        self.manager.setup_browser_driver = Mock(return_value=OperationResult.success(data=self.driver))
        self.manager.cleanup_temp_profile = Mock()
        self.browser = {"key": "edge"}
        self.stop = threading.Event()

    def navigate(self, url):
        self.driver.current_url = url

    def test_opens_home_with_secure_cookie_in_the_selected_browser(self):
        cookie_origins = []
        self.driver.add_cookie.side_effect = lambda cookie: cookie_origins.append(self.driver.current_url)

        result = self.manager.open_browser_home("alice", self.browser, self.stop)

        self.assertTrue(result, result.message)
        self.assertIs(result.data, self.driver)
        self.manager.setup_browser_driver.assert_called_once_with(browser=self.browser, interactive=True)
        self.assertEqual(cookie_origins, ["https://www.roblox.com/robots.txt"])
        self.driver.add_cookie.assert_called_once_with({
            "name": ".ROBLOSECURITY",
            "value": "synthetic-test-cookie",
            "domain": ".roblox.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
        })
        self.assertEqual(self.driver.current_url, "https://www.roblox.com/home")
        self.driver.quit.assert_not_called()

    def test_redirect_cannot_receive_the_saved_cookie(self):
        self.driver.get.side_effect = lambda url: self.navigate("https://www.roblox.com.example.test/")

        result = self.manager.open_browser_home("alice", self.browser, self.stop)

        self.assertEqual(result.code, "BROWSER_ROBLOX_ORIGIN_UNAVAILABLE")
        self.driver.add_cookie.assert_not_called()
        self.driver.quit.assert_called_once()
        self.manager.cleanup_temp_profile.assert_called_once_with("temporary-profile")

    def test_login_redirect_closes_the_failed_session(self):
        self.driver.get.side_effect = lambda url: self.navigate(
            "https://www.roblox.com/login" if url.endswith("/home") else url
        )

        result = self.manager.open_browser_home("alice", self.browser, self.stop)

        self.assertEqual(result.code, "BROWSER_HOME_NOT_REACHED")
        self.driver.quit.assert_called_once()

    def test_driver_error_does_not_expose_cookie_and_cleans_up_profile(self):
        self.driver.add_cookie.side_effect = RuntimeError("cookie=synthetic-test-cookie")

        result = self.manager.open_browser_home("alice", self.browser, self.stop)

        self.assertEqual(result.code, "BROWSER_HOME_FAILED")
        self.assertNotIn("synthetic-test-cookie", str(result))
        self.driver.quit.assert_called_once()
        self.manager.cleanup_temp_profile.assert_called_once_with("temporary-profile")

    def test_worker_reports_success_and_closes_after_browser_closes(self):
        self.driver.window_handles = []
        cleaned = threading.Event()
        self.manager.cleanup_temp_profile.side_effect = lambda profile: cleaned.set()
        done = Mock()
        browser_result = OperationResult.success(data={"browser": self.browser})
        with patch.object(account_actions, "get_browser_result", return_value=browser_result):
            account_actions.launch_browser_home(self.manager, "alice", self.stop, done)
            self.assertTrue(cleaned.wait(3))
        done.assert_called_once_with(True, OperationResult.success())
        self.driver.quit.assert_called_once()
