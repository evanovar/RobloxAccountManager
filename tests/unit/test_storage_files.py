import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from features import auto_rejoin, favorites, groups, settings_store


class FileTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.groups_file = os.path.join(self.folder.name, "groups.json")
        self.favorites_file = os.path.join(self.folder.name, "favorites.json")
        patches = [
            mock.patch.object(groups, "_GROUPS_FILE", self.groups_file),
            mock.patch.object(groups, "get_data_dir", return_value=self.folder.name),
            mock.patch.object(groups, "_CACHE", None),
            mock.patch.object(favorites, "_DATA_DIR", self.folder.name),
            mock.patch.object(favorites, "_FAVORITES_FILE", self.favorites_file),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()


class CorruptFileTests(FileTestCase):
    def test_unreadable_groups_file_is_kept_aside(self):
        self.write(self.groups_file, "{not json")
        self.assertEqual(groups.get_group_names(), [])
        self.assertEqual(self.read(self.groups_file + ".corrupt"), "{not json")
        groups.create_group("friends")
        self.assertEqual(groups.get_group_names(), ["friends"])
        self.assertEqual(self.read(self.groups_file + ".corrupt"), "{not json")

    def test_unreadable_favorites_file_is_kept_aside(self):
        self.write(self.favorites_file, "[1, 2")
        self.assertEqual(favorites.load_favorites(), [])
        self.assertEqual(self.read(self.favorites_file + ".corrupt"), "[1, 2")
        favorites.add_favorite("1818", "Game")
        self.assertEqual(self.read(self.favorites_file + ".corrupt"), "[1, 2")

    def test_wrong_shape_is_kept_aside(self):
        self.write(self.favorites_file, '{"place_id": "1"}')
        self.assertEqual(favorites.load_favorites(), [])
        self.assertTrue(os.path.exists(self.favorites_file + ".corrupt"))

    def test_good_files_are_left_alone(self):
        groups.create_group("friends")
        favorites.add_favorite("1818", "Game")
        groups._CACHE = None
        self.assertEqual(groups.get_group_names(), ["friends"])
        self.assertEqual(len(favorites.load_favorites()), 1)
        self.assertEqual(
            [name for name in os.listdir(self.folder.name) if name.endswith(".corrupt")], []
        )


class ConcurrentUpdateTests(FileTestCase):
    def run_threads(self, targets):
        threads = [threading.Thread(target=target) for target in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)

    def test_groups_do_not_lose_concurrent_changes(self):
        original = groups._save

        def slow_save(data):
            time.sleep(0.01)
            original(data)

        with mock.patch.object(groups, "_save", slow_save):
            self.run_threads([lambda n=n: groups.create_group(f"g{n}") for n in range(8)])
        self.assertEqual(sorted(groups.get_group_names()), sorted(f"g{n}" for n in range(8)))

    def test_favorites_do_not_lose_concurrent_changes(self):
        original = favorites.save_favorites

        def slow_save(items):
            time.sleep(0.01)
            original(items)

        with mock.patch.object(favorites, "save_favorites", slow_save):
            self.run_threads([lambda n=n: favorites.add_favorite(str(1000 + n), "G") for n in range(8)])
        self.assertEqual(len(favorites.load_favorites()), 8)


class CorruptSettingsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings_file = os.path.join(self.folder.name, "ui_settings.json")
        self.rejoin_file = os.path.join(self.folder.name, "auto_rejoin.json")
        patches = [
            mock.patch.object(settings_store, "_SETTINGS_PATH", self.settings_file),
            mock.patch.object(auto_rejoin, "_CONFIG_FILE", self.rejoin_file),
            mock.patch.object(auto_rejoin, "_CONFIG_CACHE", None),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        settings_store.invalidate()
        self.addCleanup(settings_store.invalidate)

    def write(self, path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_unreadable_ui_settings_survive_the_next_save(self):
        self.write(self.settings_file, '{"theme": "dark",')
        self.assertEqual(settings_store.load(), {})
        settings_store.save("theme", "light")
        self.assertEqual(self.read(self.settings_file + ".corrupt"), '{"theme": "dark",')
        self.assertEqual(settings_store.get("theme"), "light")

    def test_wrong_shape_ui_settings_are_kept_aside(self):
        self.write(self.settings_file, '["theme"]')
        self.assertEqual(settings_store.load(), {})
        self.assertEqual(self.read(self.settings_file + ".corrupt"), '["theme"]')

    def test_unreadable_auto_rejoin_configs_survive_the_next_save(self):
        self.write(self.rejoin_file, '{"main": {"place_id"')
        self.assertEqual(auto_rejoin.load_configs(), {})
        auto_rejoin.save_configs({"alt": {"place_id": "1818"}})
        self.assertEqual(self.read(self.rejoin_file + ".corrupt"), '{"main": {"place_id"')
        self.assertIn("alt", self.read(self.rejoin_file))

    def test_good_settings_are_left_alone(self):
        settings_store.save("theme", "dark")
        settings_store.invalidate()
        self.assertEqual(settings_store.get("theme"), "dark")
        self.assertFalse(os.path.exists(self.settings_file + ".corrupt"))


if __name__ == "__main__":
    unittest.main()
