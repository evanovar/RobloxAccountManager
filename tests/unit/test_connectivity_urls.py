import unittest
from unittest import mock

from features import auto_rejoin


class ConnectivityUrlTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(auto_rejoin, "_INTERNET_CACHE", (0.0, False)))

    def urls_for(self, configured):
        with mock.patch.object(auto_rejoin.settings_store, "get", return_value=configured):
            return auto_rejoin.get_connectivity_urls()

    def test_defaults_are_used_when_nothing_is_configured(self):
        self.assertEqual(self.urls_for(None), auto_rejoin.DEFAULT_CONNECTIVITY_URLS)

    def test_configured_urls_replace_the_defaults(self):
        urls = self.urls_for(["https://example.com/ping", " http://router.local/status "])
        self.assertEqual(urls, ("https://example.com/ping", "http://router.local/status"))

    def test_invalid_entries_are_dropped(self):
        urls = self.urls_for(["ftp://example.com", "not a url", 5, "", "https://example.com/ok"])
        self.assertEqual(urls, ("https://example.com/ok",))

    def test_defaults_are_used_when_every_entry_is_invalid(self):
        self.assertEqual(self.urls_for(["nope", 3]), auto_rejoin.DEFAULT_CONNECTIVITY_URLS)
        self.assertEqual(self.urls_for("https://example.com"), auto_rejoin.DEFAULT_CONNECTIVITY_URLS)

    def test_check_uses_the_configured_urls_in_order(self):
        calls = []

        def fake_get(url, timeout):
            calls.append(url)
            if url.endswith("/first"):
                raise OSError("down")
            return mock.Mock(status_code=204)

        with mock.patch.object(auto_rejoin, "get_connectivity_urls", return_value=("https://a.test/first", "https://b.test/second")), \
                mock.patch.object(auto_rejoin.requests, "get", side_effect=fake_get):
            self.assertTrue(auto_rejoin._has_internet())
        self.assertEqual(calls, ["https://a.test/first", "https://b.test/second"])

    def test_check_reports_offline_when_every_url_fails(self):
        with mock.patch.object(auto_rejoin, "get_connectivity_urls", return_value=("https://a.test/",)), \
                mock.patch.object(auto_rejoin.requests, "get", side_effect=OSError("down")):
            self.assertFalse(auto_rejoin._has_internet())


if __name__ == "__main__":
    unittest.main()
