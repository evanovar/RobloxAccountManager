import unittest

from features.account_order import move_account

ORDER = ["a", "b", "c", "d", "e"]


class MoveAccountTests(unittest.TestCase):
    def test_move_before_another_account(self):
        self.assertEqual(move_account(ORDER, "d", "b", ORDER), ["a", "d", "b", "c", "e"])
        self.assertEqual(move_account(ORDER, "a", "d", ORDER), ["b", "c", "a", "d", "e"])

    def test_move_to_the_end_of_the_full_list(self):
        self.assertEqual(move_account(ORDER, "a", None, ORDER), ["b", "c", "d", "e", "a"])

    def test_moving_next_to_itself_changes_nothing(self):
        self.assertEqual(move_account(ORDER, "c", "c", ORDER), ORDER)
        self.assertEqual(move_account(ORDER, "c", "d", ORDER), ORDER)

    def test_unknown_names_change_nothing(self):
        self.assertEqual(move_account(ORDER, "zz", "a", ORDER), ORDER)
        self.assertEqual(move_account(ORDER, "a", "zz", ORDER), ORDER)

    def test_end_of_a_filtered_view_lands_after_the_last_visible_account(self):
        self.assertEqual(move_account(ORDER, "b", None, ["b", "d"]), ["a", "c", "d", "b", "e"])

    def test_filtered_view_moves_relative_to_the_visible_target(self):
        self.assertEqual(move_account(ORDER, "d", "b", ["b", "d"]), ["a", "d", "b", "c", "e"])

    def test_input_is_not_modified(self):
        original = list(ORDER)
        move_account(ORDER, "e", "a", ORDER)
        self.assertEqual(ORDER, original)


if __name__ == "__main__":
    unittest.main()
