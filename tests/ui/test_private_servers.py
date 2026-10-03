import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from classes.operation_result import OperationResult
from utils.ui import AccountManagerUIQt, _ActionComboBox, _PrivateServerManagerDialog


class PrivateServerDialogTests(unittest.TestCase):
    def test_private_server_dropdown_toggles_closed(self):
        app = QApplication.instance() or QApplication([])
        combo = _ActionComboBox('Private Server Manager')
        combo.show()
        combo.showPopup()
        app.processEvents()
        self.assertTrue(combo._action_menu.isVisible())
        combo.showPopup()
        app.processEvents()
        self.assertFalse(combo._action_menu.isVisible())
        combo.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_account_change_rejects_stale_results_and_close_cancels(self):
        app = QApplication.instance() or QApplication([])
        parent = QMainWindow()
        parent._show_operation_error = Mock()
        manager = SimpleNamespace(accounts={'First': {}, 'Second': {}})
        pending = []

        def start(manager, username, place, callback, progress=None):
            cancel = threading.Event()
            pending.append((cancel, callback))
            return cancel

        with patch('utils.ui.private_servers_mod.start_load', side_effect=start):
            dialog = _PrivateServerManagerDialog(manager, 'First', parent)
            dialog.show()
            QTest.qWait(20)
            dialog.account.setCurrentText('Second')
            self.assertTrue(pending[0][0].is_set())
            row = {'id': '1', 'place_id': '123', 'game': 'Game', 'name': 'Server', 'status': 'Active',
                   'link': 'https://www.roblox.com/games/123?privateServerLinkCode=test'}
            pending[0][1](OperationResult.success(data=[row]))
            self.assertEqual(dialog.list.topLevelItemCount(), 0)
            pending[1][1](OperationResult.success(data=[row]))
            self.assertEqual(dialog.list.topLevelItemCount(), 1)
            applied = []
            dialog.apply_server.connect(lambda place_id, link: applied.append((place_id, link)))
            dialog.apply.click()
            self.assertEqual(applied, [('123', row['link'])])
            self.assertTrue(dialog.copy.isEnabled())
            self.assertFalse(dialog.isVisible())
            self.assertTrue(pending[1][0].is_set())
        parent.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_apply_updates_both_main_fields(self):
        target = SimpleNamespace(_place_id_edit=Mock(), _private_server_edit=Mock())
        AccountManagerUIQt._apply_private_server_fields(target, '123', 'private-link')
        target._place_id_edit.setCurrentText.assert_called_once_with('123')
        target._private_server_edit.setCurrentText.assert_called_once_with('private-link')

    def test_missing_link_can_be_generated_from_copy_button(self):
        app = QApplication.instance() or QApplication([])
        parent = QMainWindow()
        parent._show_operation_error = Mock()
        manager = SimpleNamespace(accounts={'First': {}})
        pending_load = []
        pending_link = []

        def start_load(manager, username, place, callback, progress=None):
            cancel = threading.Event()
            pending_load.append((cancel, callback))
            return cancel

        def start_link(manager, username, server_id, place_id, callback):
            cancel = threading.Event()
            pending_link.append((cancel, callback, server_id, place_id))
            return cancel

        with patch('utils.ui.private_servers_mod.start_load', side_effect=start_load), patch(
                'utils.ui.private_servers_mod.start_generate_link', side_effect=start_link), patch(
                'utils.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            dialog = _PrivateServerManagerDialog(manager, 'First', parent)
            dialog.show()
            QTest.qWait(20)
            row = {'id': '123', 'place_id': '456', 'game': 'Game', 'name': 'Server',
                   'status': 'Active', 'link': ''}
            pending_load[0][1](OperationResult.success(data=[row]))
            self.assertTrue(dialog.copy.isEnabled())
            self.assertTrue(dialog.apply.isEnabled())
            dialog.copy.click()
            self.assertEqual(pending_link[0][2:], ('123', '456'))
            link = 'https://www.roblox.com/share?code=test&type=Server'
            pending_link[0][1](OperationResult.success(data=link))
            self.assertEqual(QApplication.clipboard().text(), link)
            self.assertTrue(dialog.isVisible())
            dialog.close()
        parent.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
