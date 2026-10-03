"""First-run password setup saves only the KDF salt and encryption settings."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMainWindow

from classes.account_manager import RobloxAccountManager
from utils import ui


class EncryptionSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_password_confirmation_creates_a_config_without_a_fast_verifier(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(ui, "get_data_dir", return_value=directory))
        self.enterContext(patch("classes.account_manager.get_data_dir", return_value=directory))
        self.enterContext(patch.object(ui, "_show_info"))
        window = QMainWindow()
        self.addCleanup(self.close_window, window)
        window._on_setup_complete = Mock()
        window.setCentralWidget(ui.AccountManagerUIQt._build_setup_panel(window))
        window._setup_continue_btn.click()
        self.assertEqual(window._setup_stack.currentIndex(), 1)
        password = "test-password-中文"
        window._setup_pw_entry1.setText(password)
        window._setup_pw_entry2.setText(password)
        window._setup_pw_confirm_btn.click()
        window._on_setup_complete.assert_called_once_with()
        config_path = Path(directory) / "encryption_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertNotIn("password_hash", config)
        self.assertTrue(config["salt"])
        self.assertEqual(config["encryption_method"], "password")
        manager = RobloxAccountManager(password)
        manager.accounts = {"demo": {"cookie": "synthetic-cookie"}}
        manager.save_accounts()
        self.assertEqual(RobloxAccountManager(password).accounts["demo"]["cookie"], "synthetic-cookie")

    def close_window(self, window):
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
