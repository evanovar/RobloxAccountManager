import threading
import unittest
from unittest.mock import Mock, patch

import requests

from features import game_selector as selector


def game(universe=10, place=20, name="Game"):
    return {"universeId": universe, "rootPlaceId": place, "name": name}


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.get = self.enterContext(patch.object(selector, "_get_json"))

    def test_search_uses_root_place_ids_and_skips_other_results_invalid_ids_and_duplicates(self):
        self.get.side_effect = [
            {"searchResults": [
                {"contentGroupType": "User", "contents": [game()]},
                {"contentGroupType": "Game", "contents": [
                    game(name="Test <Game>"), game(), game(place=True),
                    game(universe=12, place="bad"), game(universe=13, name=""),
                    game(universe=14, place=12345678901234, name="Unicode 中文"),
                ]},
            ], "nextPageToken": "next"},
            {"data": [
                {"targetId": 14, "state": "Pending", "imageUrl": "pending"},
                {"targetId": 10, "state": "Completed", "imageUrl": "https://tr.rbxcdn.com/image.png"},
            ]},
        ]
        result = selector.search_games("  test  ", "session", "page")
        self.assertTrue(result)
        self.assertEqual([(g.universe_id, g.place_id, g.title) for g in result.data["games"]],
                         [("10", "20", "Test <Game>"), ("14", "12345678901234", "Unicode 中文")])
        self.assertEqual(result.data["next_page_token"], "next")
        self.assertEqual(result.data["games"][0].thumbnail_url, "https://tr.rbxcdn.com/image.png")
        self.get.assert_any_call(selector.SEARCH_URL, {
            "searchQuery": "test", "sessionId": "session", "pageType": "all", "pageToken": "page",
        })

    def test_empty_search_loads_top_playing_games(self):
        self.get.side_effect = [
            {"sorts": [
                {"contentType": "Filters"},
                {"contentType": "Games", "sortId": "other", "games": [game(11, 21)]},
                {"contentType": "Games", "sortId": "top-playing-now", "games": [game()]},
            ]}, {"data": []},
        ]
        result = selector.search_games("", "session")
        self.assertEqual(result.data["games"][0].place_id, "20")
        self.assertEqual(result.data["next_page_token"], "")
        self.get.assert_any_call(selector.DISCOVERY_URL, {"sessionId": "session"})

    def test_thumbnail_service_failure_keeps_games_selectable(self):
        self.get.side_effect = [
            {"searchResults": [{"contentGroupType": "Game", "contents": [game()]}]},
            requests.Timeout(),
        ]
        result = selector.search_games("test", "session")
        self.assertTrue(result)
        self.assertEqual(result.data["games"][0].thumbnail_url, "")

    def test_discovery_keeps_remaining_pages_and_only_fetches_first_page_icons(self):
        records = [game(i, i + 100) for i in range(1, 86)]
        self.get.side_effect = [
            {"sorts": [{"contentType": "Games", "sortId": "top-playing-now", "games": records}]},
            {"data": []},
        ]
        result = selector.search_games("", "session")
        self.assertEqual(len(result.data["games"]), 40)
        self.assertEqual([len(page) for page in result.data["remaining_pages"]], [40, 5])
        self.assertEqual(result.data["remaining_pages"][0][0].place_id, "141")
        self.assertEqual(len(self.get.call_args.args[1]["universeIds"].split(",")), 40)

    def test_empty_results_are_successful_and_do_not_fetch_thumbnails(self):
        self.get.return_value = {"searchResults": []}
        result = selector.search_games("absent", "session")
        self.assertTrue(result)
        self.assertEqual(result.data["games"], [])
        self.get.assert_called_once()

    def test_network_and_malformed_responses_return_recoverable_errors(self):
        for error in (requests.Timeout(), ValueError("invalid json"), KeyError("searchResults")):
            with self.subTest(error=error):
                self.get.side_effect = error
                result = selector.search_games("test", "session")
                self.assertFalse(result)
                self.assertTrue(result.retryable)

    def test_rate_limit_response_explains_how_to_retry(self):
        response = requests.Response()
        response.status_code = 429
        self.get.side_effect = requests.HTTPError(response=response)
        result = selector.search_games("test", "session")
        self.assertFalse(result)
        self.assertIn("Wait a moment", result.message)


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.cancel = threading.Event()
        self.get = self.enterContext(patch.object(selector.requests, "get"))
        self.response = self.get.return_value.__enter__.return_value

    def test_cancelled_and_non_roblox_urls_are_not_downloaded(self):
        for url in ("https://example.com/file", "http://rbxcdn.com/file", "https://rbxcdn.com.evil.com/file", "https://[invalid", ""):
            self.assertIsNone(selector.download_thumbnail(url, self.cancel))
        self.cancel.set()
        self.assertIsNone(selector.download_thumbnail("https://tr.rbxcdn.com/file", self.cancel))
        self.get.assert_not_called()

    def test_image_download_is_bounded_and_uses_a_timeout(self):
        self.response.iter_content.return_value = [b"image", b"data"]
        self.assertEqual(selector.download_thumbnail("https://tr.rbxcdn.com/file", self.cancel), b"imagedata")
        self.get.assert_called_once_with("https://tr.rbxcdn.com/file", timeout=(5, 10),
                                         stream=True, allow_redirects=False)
        self.response.iter_content.return_value = [b"x" * (selector.MAX_IMAGE_BYTES + 1)]
        self.assertIsNone(selector.download_thumbnail("https://tr.rbxcdn.com/file", self.cancel))


class WorkerTests(unittest.TestCase):
    def test_cached_discovery_page_resolves_icons_off_the_ui_thread(self):
        complete = threading.Event()
        seen = []

        def resolve(games):
            seen.append(threading.current_thread())
            return [selector.Game("10", "20", "Game", "url")]

        with patch.object(selector, "_with_icons", side_effect=resolve), \
                patch.object(selector, "download_thumbnail", return_value=b"image"):
            selector.start_thumbnails([selector.Game("10", "20", "Game")],
                                      lambda *args: (seen.append(threading.current_thread()), complete.set()))
            self.assertTrue(complete.wait(3))
        self.assertTrue(all(thread is not threading.current_thread() for thread in seen))

    def test_search_and_thumbnail_callbacks_run_off_the_ui_thread(self):
        result = selector.OperationResult.success(data={"games": [selector.Game("10", "20", "Game", "url")]})
        complete = threading.Event()
        seen = []
        with patch.object(selector, "search_games", return_value=result), \
                patch.object(selector, "download_thumbnail", return_value=b"image"):
            selector.start_load("test", "session", "",
                                lambda result: seen.append(threading.current_thread()),
                                lambda *args: (seen.append(threading.current_thread()), complete.set()))
            self.assertTrue(complete.wait(3))
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(thread is not threading.current_thread() for thread in seen))

    def test_cancelling_a_pending_search_prevents_delivery(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()

        def search(*args):
            entered.set()
            release.wait(3)
            finished.set()
            return selector.OperationResult.success(data={"games": []})

        done = Mock()
        with patch.object(selector, "search_games", side_effect=search):
            cancel = selector.start_load("test", "session", "", done, Mock())
            self.assertTrue(entered.wait(3))
            cancel.set()
            release.set()
            self.assertTrue(finished.wait(3))
        done.assert_not_called()


if __name__ == "__main__":
    unittest.main()
