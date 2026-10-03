import os
import tempfile
import unittest
from unittest.mock import patch
from features import groups

class GroupSaveTests(unittest.TestCase):
    def test_failed_write_preserves_groups_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            groups, 'get_data_dir', return_value=directory,
        ), patch.object(groups, '_GROUPS_FILE', os.path.join(directory, 'groups.json')), patch.object(
            groups, '_CACHE', None,
        ):
            self.assertTrue(groups.create_group('Original'))
            with patch.object(groups.os, 'replace', side_effect=PermissionError('Access denied')):
                with self.assertRaises(PermissionError):
                    groups.create_group('New')
            self.assertEqual(groups.get_group_names(), ['Original'])
            groups._CACHE = None
            self.assertEqual(groups.get_group_names(), ['Original'])
            self.assertEqual(os.listdir(directory), ['groups.json'])
            self.assertTrue(groups.create_group('New'))
            self.assertEqual(groups.get_group_names(), ['Original', 'New'])
