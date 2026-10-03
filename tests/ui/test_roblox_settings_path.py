from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from classes.operation_result import OperationResult
from utils import ui


class PathRowWindow(ui.AccountManagerUIQt):
    def __init__(self):
        QMainWindow.__init__(self)
        self._roblox_settings_loading = False
        self._roblox_settings_applying = False
        self._roblox_settings_auto_applying = False
        self._roblox_settings_path_changing = False
        self._roblox_settings_records = {}
        self._bridge = ui._Bridge()
        self._bridge.roblox_settings_path_changed.connect(self._on_roblox_settings_path_changed)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addLayout(self._build_roblox_settings_path_row())
        self._roblox_settings_reload_btn = QPushButton()
        self._roblox_settings_apply_btn = QPushButton()
        self._roblox_settings_auto_apply_chk = QCheckBox()
        self._roblox_settings_value_stack = QStackedWidget()
        self._roblox_settings_state_label = QLabel()
        self._load_roblox_settings = Mock()
        self._on_roblox_setting_selected = Mock()
        self._show_operation_error = Mock()


class RobloxSettingsPathUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.path = Path("C:/Synthetic/Roblox/GlobalBasicSettings_13.xml")
        self.path_mock = self.enterContext(patch.object(ui.roblox_settings_mod, "get_settings_path", return_value=self.path))
        self.worker = self.enterContext(patch.object(ui.roblox_settings_mod, "set_settings_path_async"))
        self.window = PathRowWindow()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_default_path_is_visible(self):
        self.assertEqual(self.window._roblox_settings_path_edit.text(), str(self.path))
        self.assertTrue(self.window._roblox_settings_path_edit.isReadOnly())
        self.assertTrue(self.window._roblox_settings_browse_btn.isEnabled())

    def test_canceling_the_picker_keeps_the_location(self):
        with patch.object(ui.QFileDialog, "getOpenFileName", return_value=("", "")):
            self.window._roblox_settings_browse_btn.click()
        self.worker.assert_not_called()
        self.assertEqual(self.window._roblox_settings_path_edit.text(), str(self.path))

    def test_browse_disables_controls_until_selection_is_saved_then_reloads(self):
        custom = Path("C:/Synthetic/Custom/settings.xml")
        with patch.object(ui.QFileDialog, "getOpenFileName", return_value=(str(custom), "XML files (*.xml)")):
            self.window._roblox_settings_browse_btn.click()
        self.assertEqual(self.worker.call_args.args[0], str(custom))
        self.assertFalse(self.window._roblox_settings_browse_btn.isEnabled())
        self.assertFalse(self.window._roblox_settings_reload_btn.isEnabled())
        self.assertFalse(self.window._roblox_settings_auto_apply_chk.isEnabled())
        self.path_mock.return_value = custom
        self.worker.call_args.args[1](OperationResult.success(data={"changed": True}))
        self.assertEqual(self.window._roblox_settings_path_edit.text(), str(custom))
        self.window._load_roblox_settings.assert_called_once_with(show_error=True)

    def test_invalid_selection_shows_an_error_and_retains_the_previous_path(self):
        self.window._set_roblox_settings_path("C:/Synthetic/invalid.xml")
        result = OperationResult.failure("INVALID", "Invalid XML", "Choose another XML file.")
        self.worker.call_args.args[1](result)
        self.assertEqual(self.window._roblox_settings_path_edit.text(), str(self.path))
        self.window._show_operation_error.assert_called_once_with(result)
        self.window._load_roblox_settings.assert_not_called()
        self.assertTrue(self.window._roblox_settings_browse_btn.isEnabled())

    def test_location_cannot_change_during_load_apply_or_auto_apply(self):
        for attribute in ("_roblox_settings_loading", "_roblox_settings_applying", "_roblox_settings_auto_applying"):
            with self.subTest(attribute=attribute):
                setattr(self.window, attribute, True)
                self.window._update_roblox_settings_path_controls()
                self.assertFalse(self.window._roblox_settings_browse_btn.isEnabled())
                self.window._set_roblox_settings_path("C:/Synthetic/new.xml")
                self.worker.assert_not_called()
                setattr(self.window, attribute, False)
