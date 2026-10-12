import json
import os
import tempfile
import unittest
from unittest import mock

from features import account_actions, auto_rejoin, favorites, groups, settings_store


class DescriptorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        path = self.folder.name
        patches = [
            mock.patch.object(settings_store, "_SETTINGS_PATH", os.path.join(path, "ui_settings.json")),
            mock.patch.object(groups, "_GROUPS_FILE", os.path.join(path, "groups.json")),
            mock.patch.object(groups, "get_data_dir", return_value=path),
            mock.patch.object(groups, "_CACHE", None),
            mock.patch.object(favorites, "_DATA_DIR", path),
            mock.patch.object(favorites, "_FAVORITES_FILE", os.path.join(path, "favorites.json")),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        settings_store.invalidate()
        self.addCleanup(settings_store.invalidate)

    def leftovers(self):
        return [name for name in os.listdir(self.folder.name) if name.endswith(".tmp")]

    def assert_failed_write_is_clean(self, action):
        with mock.patch("json.dump", side_effect=OSError("disk full")), \
                mock.patch("os.close") as close:
            with self.assertRaises(OSError):
                action()
        close.assert_not_called()
        self.assertEqual(self.leftovers(), [])

    def test_settings_failed_write_does_not_close_the_descriptor_twice(self):
        self.assert_failed_write_is_clean(lambda: settings_store.save("a", 1))

    def test_groups_failed_write_does_not_close_the_descriptor_twice(self):
        self.assert_failed_write_is_clean(lambda: groups.create_group("friends"))

    def test_favorites_failed_write_does_not_close_the_descriptor_twice(self):
        self.assert_failed_write_is_clean(lambda: favorites.add_favorite("1818", "Game"))

    def test_unserializable_value_leaves_no_temp_file(self):
        with self.assertRaises(TypeError):
            favorites.save_favorites([{"bad": object()}])
        self.assertEqual(self.leftovers(), [])

    def test_failed_write_keeps_the_previous_file(self):
        favorites.add_favorite("1818", "Game")
        with self.assertRaises(TypeError):
            favorites.save_favorites([{"bad": object()}])
        self.assertEqual(favorites.load_favorites()[0]["place_id"], "1818")

    def test_round_trips(self):
        settings_store.save("theme", "dark")
        self.assertEqual(settings_store.get("theme"), "dark")
        groups.create_group("friends")
        groups.set_account_group("alice", "friends")
        self.assertEqual(groups.get_account_group("alice"), "friends")
        favorites.add_favorite("1818", "Game", "123")
        self.assertEqual(favorites.load_favorites()[0]["private_server"], "123")


class RecentGamesAndAutoRejoinTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        path = self.folder.name
        self.recent = os.path.join(path, "recent_games.json")
        self.configs = os.path.join(path, "auto_rejoin.json")
        patches = [
            mock.patch.object(account_actions, "_DATA_DIR", path),
            mock.patch.object(account_actions, "_RECENT_GAMES_FILE", self.recent),
            mock.patch.object(settings_store, "_SETTINGS_PATH", os.path.join(path, "ui_settings.json")),
            mock.patch.object(auto_rejoin, "_CONFIG_FILE", self.configs),
            mock.patch.object(auto_rejoin, "_CONFIG_CACHE", None),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        settings_store.invalidate()
        self.addCleanup(settings_store.invalidate)

    def test_recent_games_round_trip_and_limit(self):
        for number in range(25):
            account_actions.save_recent_game(str(number), f"Game {number}")
        games = account_actions.load_recent_games()
        self.assertEqual(len(games), 10)
        self.assertEqual(games[0]["place_id"], "24")
        self.assertEqual(games[-1]["place_id"], "15")
        with open(self.recent, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), games)

    def test_recent_games_use_the_configured_limit_instead_of_twenty(self):
        settings_store.save("max_recent_games", 30)
        for number in range(35):
            account_actions.save_recent_game(str(number), f"Game {number}")
        games = account_actions.load_recent_games()
        self.assertEqual([game["place_id"] for game in games], [str(n) for n in range(34, 4, -1)])

    def test_loading_oversized_history_removes_the_oldest_entries_from_disk(self):
        history = [{"place_id": str(n), "name": f"Game {n}"} for n in range(19, -1, -1)]
        with open(self.recent, "w", encoding="utf-8") as handle:
            json.dump(history, handle)
        games = account_actions.load_recent_games()
        self.assertEqual(games, history[:10])
        with open(self.recent, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), history[:10])

    def test_lowering_the_limit_keeps_the_most_recent_entries(self):
        settings_store.save("max_recent_games", 20)
        for number in range(20):
            account_actions.save_recent_game(str(number), f"Game {number}")
        settings_store.save("max_recent_games", 5)
        self.assertEqual([game["place_id"] for game in account_actions.load_recent_games()],
                         ["19", "18", "17", "16", "15"])
        with open(self.recent, encoding="utf-8") as handle:
            self.assertEqual(len(json.load(handle)), 5)

    def test_replaying_a_game_moves_it_to_the_front_without_duplicating_it(self):
        settings_store.save("max_recent_games", 5)
        for number in range(5):
            account_actions.save_recent_game(str(number), f"Game {number}")
        account_actions.save_recent_game("1", "Played Again")
        account_actions.save_recent_game("5", "New Game")
        self.assertEqual([game["place_id"] for game in account_actions.load_recent_games()],
                         ["5", "1", "4", "3", "2"])

    def test_failed_history_trim_keeps_the_existing_file(self):
        history = [{"place_id": str(n)} for n in range(19, -1, -1)]
        with open(self.recent, "w", encoding="utf-8") as handle:
            json.dump(history, handle)
        with mock.patch("json.dump", side_effect=OSError("disk full")):
            self.assertEqual(account_actions.load_recent_games(), history[:10])
        with open(self.recent, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), history)

    def test_recent_games_limit_validation_matches_the_setting_range(self):
        for value, expected in ((None, 10), ("bad", 10), ("15", 15), (1, 5), (100, 50),
                                (float("inf"), 10)):
            with self.subTest(value=value):
                self.assertEqual(account_actions.get_recent_games_limit({"max_recent_games": value}), expected)

    def test_recent_games_failed_write_keeps_the_previous_file(self):
        account_actions.save_recent_game("1", "One")
        with mock.patch("json.dump", side_effect=OSError("disk full")), mock.patch("os.close") as close:
            with self.assertRaises(OSError):
                account_actions.save_recent_game("2", "Two")
        close.assert_not_called()
        self.assertEqual([g["place_id"] for g in account_actions.load_recent_games()], ["1"])

    def test_deleting_a_recent_game_preserves_other_servers_and_order(self):
        account_actions.save_recent_game("1", "Public")
        account_actions.save_recent_game("1", "Private A", "server-a")
        account_actions.save_recent_game("1", "Private B", "server-b")
        account_actions.save_recent_game("2", "Other Game")
        account_actions.remove_recent_game("1", "server-a")
        games = account_actions.load_recent_games()
        self.assertEqual([(g["place_id"], g["private_server"]) for g in games],
                         [("2", ""), ("1", "server-b"), ("1", "")])
        with open(self.recent, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), games)

    def test_deleting_the_last_recent_game_saves_empty_history(self):
        account_actions.save_recent_game("1", "One")
        account_actions.remove_recent_game("1")
        with open(self.recent, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), [])

    def test_failed_recent_game_deletion_keeps_the_previous_file(self):
        account_actions.save_recent_game("1", "One")
        with mock.patch("json.dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                account_actions.remove_recent_game("1")
        self.assertEqual([g["place_id"] for g in account_actions.load_recent_games()], ["1"])
        self.assertEqual([n for n in os.listdir(self.folder.name) if n.endswith(".tmp")], [])

    def test_unreadable_recent_games_file_is_kept_aside(self):
        with open(self.recent, "w", encoding="utf-8") as handle:
            handle.write("[{")
        self.assertEqual(account_actions.load_recent_games(), [])
        self.assertTrue(os.path.exists(self.recent + ".corrupt"))

    def test_auto_rejoin_configs_round_trip(self):
        auto_rejoin.save_configs({"alice": {"place_id": "1"}})
        auto_rejoin._CONFIG_CACHE = None
        self.assertEqual(auto_rejoin.load_configs(), {"alice": {"place_id": "1"}})

    def test_auto_rejoin_failed_save_is_reported_and_keeps_the_old_file(self):
        auto_rejoin.save_configs({"alice": {"place_id": "1"}})
        with mock.patch("json.dump", side_effect=OSError("disk full")):
            auto_rejoin.save_configs({"alice": {"place_id": "2"}})
        auto_rejoin._CONFIG_CACHE = None
        self.assertEqual(auto_rejoin.load_configs(), {"alice": {"place_id": "1"}})
        self.assertEqual([n for n in os.listdir(self.folder.name) if n.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
