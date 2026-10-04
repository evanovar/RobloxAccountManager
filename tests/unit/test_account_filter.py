import unittest

from features.account_filter import filter_accounts

ITEMS = [
    ("Alice_Main", {"note": "farming account", "user_id": 111}),
    ("bob_alt", {"note": "trading", "user_id": 222}),
    ("Carol99", {"note": "", "user_id": 333}),
    ("dave", "unexpected legacy value"),
]
GROUPS = {"Alice_Main": "Farm", "bob_alt": "Trade"}


def names(result):
    return [name for name, _ in result]


class FilterAccountsTests(unittest.TestCase):
    def test_empty_query_keeps_everything_in_order(self):
        for query in ("", "   ", None):
            with self.subTest(query=query):
                self.assertEqual(names(filter_accounts(ITEMS, query)), [n for n, _ in ITEMS])

    def test_matches_usernames_ignoring_case(self):
        self.assertEqual(names(filter_accounts(ITEMS, "ALICE")), ["Alice_Main"])
        self.assertEqual(names(filter_accounts(ITEMS, "_")), ["Alice_Main", "bob_alt"])

    def test_matches_notes_and_user_ids(self):
        self.assertEqual(names(filter_accounts(ITEMS, "trading")), ["bob_alt"])
        self.assertEqual(names(filter_accounts(ITEMS, "333")), ["Carol99"])

    def test_matches_group_names(self):
        self.assertEqual(names(filter_accounts(ITEMS, "farm", GROUPS)), ["Alice_Main"])
        self.assertEqual(names(filter_accounts(ITEMS, "trade", GROUPS)), ["bob_alt"])

    def test_every_word_has_to_match(self):
        self.assertEqual(names(filter_accounts(ITEMS, "alice farming")), ["Alice_Main"])
        self.assertEqual(names(filter_accounts(ITEMS, "alice trading")), [])

    def test_no_match_returns_an_empty_list(self):
        self.assertEqual(filter_accounts(ITEMS, "zzz"), [])

    def test_entries_without_dictionary_data_still_match_by_name(self):
        self.assertEqual(names(filter_accounts(ITEMS, "dav")), ["dave"])
        self.assertEqual(filter_accounts(ITEMS, "legacy"), [])

    def test_input_is_not_modified(self):
        items = list(ITEMS)
        filter_accounts(items, "alice")
        self.assertEqual(items, ITEMS)


if __name__ == "__main__":
    unittest.main()
