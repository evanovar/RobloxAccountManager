import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import requests

from features import avatars

DAY = 86400


class AvatarCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.enterContext(patch.object(avatars, "_CACHE_DIR", self.folder.name))
        self.enterContext(patch.object(avatars, "_MEMORY_CACHE", avatars.collections.OrderedDict()))
        self.enterContext(patch.dict(avatars._INFLIGHT, {}, clear=True))
        self.days = 7
        self.enterContext(patch.object(avatars, "get_cache_days", side_effect=lambda: self.days))

    def write(self, user_id, data=b"png", age_days=0.0):
        path = os.path.join(self.folder.name, f"{user_id}.png")
        with open(path, "wb") as handle:
            handle.write(data)
        stamp = time.time() - age_days * DAY
        os.utime(path, (stamp, stamp))
        return path

    def test_fresh_files_are_served_from_disk(self):
        self.write("1", b"fresh", age_days=1)
        self.assertEqual(avatars.load_cached_bytes("1"), b"fresh")

    def test_expired_files_count_as_missing(self):
        self.write("1", b"old", age_days=8)
        self.assertIsNone(avatars.load_cached_bytes("1"))

    def test_expired_files_can_still_be_read_when_allowed(self):
        self.write("1", b"old", age_days=8)
        self.assertEqual(avatars.load_cached_bytes("1", allow_stale=True), b"old")

    def test_zero_days_means_never_expire(self):
        self.days = 0
        self.write("1", b"ancient", age_days=3000)
        self.assertEqual(avatars.load_cached_bytes("1"), b"ancient")

    def test_missing_file_is_missing(self):
        self.assertIsNone(avatars.load_cached_bytes("404"))
        self.assertIsNone(avatars.load_cached_bytes("404", allow_stale=True))


class FetchWorkerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.enterContext(patch.object(avatars, "_CACHE_DIR", self.folder.name))
        self.enterContext(patch.object(avatars, "_MEMORY_CACHE", avatars.collections.OrderedDict()))
        self.enterContext(patch.dict(avatars._INFLIGHT, {}, clear=True))
        self.enterContext(patch.object(avatars, "get_cache_days", return_value=7))
        self.received = []
        avatars._INFLIGHT["1"] = [("alice", lambda name, data: self.received.append((name, data)))]

    def write(self, data, age_days):
        path = os.path.join(self.folder.name, "1.png")
        with open(path, "wb") as handle:
            handle.write(data)
        stamp = time.time() - age_days * DAY
        os.utime(path, (stamp, stamp))
        return path

    def session_returning(self, content=b"new", status=200, error=None):
        response = MagicMock(status_code=status, content=content)
        session = MagicMock()
        if error:
            session.get.side_effect = error
        else:
            session.get.return_value = response
        return session

    def test_expired_avatar_is_downloaded_again_and_replaced(self):
        path = self.write(b"old", age_days=9)
        with patch.object(avatars, "_get_session", return_value=self.session_returning(b"new")):
            avatars._fetch_worker("1", "https://example.invalid/a.png")
        self.assertEqual(self.received, [("alice", b"new")])
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), b"new")
        self.assertLess(time.time() - os.path.getmtime(path), 60)

    def test_fresh_avatar_is_not_downloaded(self):
        self.write(b"fresh", age_days=1)
        session = self.session_returning(b"new")
        with patch.object(avatars, "_get_session", return_value=session):
            avatars._fetch_worker("1", "https://example.invalid/a.png")
        session.get.assert_not_called()
        self.assertEqual(self.received, [("alice", b"fresh")])

    def test_failed_refresh_falls_back_to_the_expired_avatar(self):
        self.write(b"old", age_days=9)
        session = self.session_returning(error=requests.ConnectionError("offline"))
        with patch.object(avatars, "_get_session", return_value=session):
            avatars._fetch_worker("1", "https://example.invalid/a.png")
        self.assertEqual(self.received, [("alice", b"old")])

    def test_bad_response_falls_back_to_the_expired_avatar(self):
        self.write(b"old", age_days=9)
        with patch.object(avatars, "_get_session", return_value=self.session_returning(b"", status=500)):
            avatars._fetch_worker("1", "https://example.invalid/a.png")
        self.assertEqual(self.received, [("alice", b"old")])

    def test_failed_download_without_any_cache_calls_nothing(self):
        session = self.session_returning(error=requests.ConnectionError("offline"))
        with patch.object(avatars, "_get_session", return_value=session):
            avatars._fetch_worker("1", "https://example.invalid/a.png")
        self.assertEqual(self.received, [])
        self.assertNotIn("1", avatars._INFLIGHT)


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.enterContext(patch.object(avatars, "_CACHE_DIR", self.folder.name))
        self.days = 7
        self.enterContext(patch.object(avatars, "get_cache_days", side_effect=lambda: self.days))

    def write(self, name, age_days):
        path = os.path.join(self.folder.name, name)
        with open(path, "wb") as handle:
            handle.write(b"x")
        stamp = time.time() - age_days * DAY
        os.utime(path, (stamp, stamp))

    def names(self):
        return sorted(os.listdir(self.folder.name))

    def test_only_old_files_for_unknown_users_are_removed(self):
        self.write("1.png", 100)
        self.write("2.png", 100)
        self.write("3.png", 10)
        self.write("notes.txt", 100)
        self.assertEqual(avatars.prune_unused_cache({"1"}), 1)
        self.assertEqual(self.names(), ["1.png", "3.png", "notes.txt"])

    def test_nothing_is_removed_when_expiry_is_off_or_no_accounts_are_known(self):
        self.write("2.png", 100)
        self.days = 0
        self.assertEqual(avatars.prune_unused_cache({"1"}), 0)
        self.days = 7
        self.assertEqual(avatars.prune_unused_cache(set()), 0)
        self.assertEqual(self.names(), ["2.png"])

    def test_missing_folder_is_fine(self):
        with patch.object(avatars, "_CACHE_DIR", os.path.join(self.folder.name, "missing")):
            self.assertEqual(avatars.prune_unused_cache({"1"}), 0)


class SettingTests(unittest.TestCase):
    def test_default_and_parsing(self):
        for value, expected in ((None, 7), ("14", 14), (0, 0), (-3, 0), ("soon", 7)):
            with self.subTest(value=value):
                with patch.object(avatars.settings_store, "get", return_value=7 if value is None else value):
                    self.assertEqual(avatars.get_cache_days(), expected)


if __name__ == "__main__":
    unittest.main()
