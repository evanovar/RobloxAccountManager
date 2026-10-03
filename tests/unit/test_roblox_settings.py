import unittest
from unittest.mock import patch

from classes.operation_result import OperationResult
from features import roblox_settings as settings


class SettingsWithoutBasicTests(unittest.TestCase):
    def test_old_basic_flags_do_not_enable_startup_apply(self):
        profile = {'basic': {'MasterVolume': {'enabled': True, 'value': '0.1'}}}
        with patch.object(settings, '_load_local_profile_file', return_value=profile):
            self.assertFalse(settings.has_startup_customizations())

    def test_manual_apply_uses_list_value_not_old_basic_override(self):
        profile = {
            'settings': {'MasterVolume': {'value': '0.8', 'editable': True}},
            'basic': {'MasterVolume': {'enabled': True, 'value': '0.1'}},
        }
        data = {'settings': [{'key': 'MasterVolume', 'value': '1.0', 'xml_type': 'float'}]}
        with patch.object(settings, 'load_settings', return_value=OperationResult.success(data=data)), patch.object(
            settings, 'apply_settings', return_value=OperationResult.success(data=data),
        ) as apply, patch.object(settings, '_save_local_profile', return_value=OperationResult.success()):
            result = settings._apply_profile(profile, True, False, False)
        self.assertTrue(result)
        self.assertEqual(apply.call_args.args[0], {'MasterVolume': '0.8'})

    def test_auto_apply_off_does_not_write_old_basic_value(self):
        profile = {'settings': {}, 'basic': {'MasterVolume': {'enabled': True, 'value': '0.1'}}}
        data = {'settings': [{'key': 'MasterVolume', 'value': '1.0', 'xml_type': 'float'}]}
        with patch.object(settings, 'load_settings', return_value=OperationResult.success(data=data)), patch.object(
            settings, 'apply_settings',
        ) as apply, patch.object(settings, '_save_local_profile', return_value=OperationResult.success()):
            self.assertTrue(settings._apply_profile(profile, False, False, False))
        apply.assert_not_called()
