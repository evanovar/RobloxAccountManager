import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from classes.operation_result import OperationResult
from features import auto_rejoin
from features.websocket_server import WebSocketServer

class LaunchSettingsTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            'roblox_launcher': 'custom',
            'custom_roblox_launcher_path': 'C:/Example/RobloxPlayerBeta.exe',
        }
        self.manager = SimpleNamespace(
            accounts={'demo': {'cookie': 'test'}},
            launch_roblox=Mock(return_value=OperationResult.success()),
        )
        self.status = Mock()
        self.workers = {}
        self.server = WebSocketServer(
            self.manager, self.workers, {'demo': {}}, lambda: self.settings,
            rejoin_status_callback=self.status,
        )

    def test_websocket_start_supplies_status_callback(self):
        with patch.object(auto_rejoin.AutoRejoinWorker, 'start'):
            result = self.server._execute('AutoRejoin start demo')
        self.assertTrue(result['ok'], result)
        self.workers['demo']._emit('Running')
        self.status.assert_called_once_with('demo', 'Running')

    def test_websocket_launch_uses_saved_custom_path(self):
        self.assertTrue(self.server._execute('Launch demo 123')['ok'])
        self.manager.launch_roblox.assert_called_once_with(
            'demo', '123', '', 'custom', '', self.settings['custom_roblox_launcher_path'],
        )

    def test_websocket_join_user_uses_saved_custom_path(self):
        with patch('features.websocket_server.RobloxAPI.get_user_id_from_username', return_value=1), patch(
            'features.websocket_server.RobloxAPI.get_player_presence',
            return_value={'in_game': True, 'place_id': 123, 'game_id': 'job'},
        ):
            result = self.server._execute('JoinUser demo target')
        self.assertTrue(result['ok'], result)
        self.manager.launch_roblox.assert_called_once_with(
            'demo', '123', '', 'custom', 'job', self.settings['custom_roblox_launcher_path'],
        )

    def test_rejoin_reads_current_launcher_settings(self):
        worker = auto_rejoin.AutoRejoinWorker('demo', {}, self.manager, self.status)
        self.manager.launch_roblox.return_value = False
        with patch.object(auto_rejoin, '_get_roblox_processes', return_value={}), patch.object(
            auto_rejoin.settings_store, 'load', return_value=self.settings,
        ):
            worker._launch_and_track('1', '123', 'private', 'job')
        self.manager.launch_roblox.assert_called_once_with(
            'demo', '123', 'private', launcher_preference='custom', job_id='job',
            custom_launcher_path=self.settings['custom_roblox_launcher_path'],
        )
