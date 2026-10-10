import unittest
from unittest.mock import patch

from features import window_grid as grid


class WindowGridTests(unittest.TestCase):
    def tile(self, count, work_area, window_size=(845, 627), failed=(), minimized=(),
             minimum_width=0, frame_size=(16, 39)):
        windows = list(range(1, count + 1))
        rectangles = {hwnd: (100, 200, 100 + window_size[0], 200 + window_size[1])
                      for hwnd in windows}
        resized_widths = []

        def move(hwnd, insert_after, x, y, width, height, flags):
            if hwnd in failed:
                raise OSError("Window closed")
            left, top, right, bottom = rectangles[hwnd]
            if flags & grid.win32con.SWP_NOSIZE:
                self.assertEqual(insert_after, grid.win32con.HWND_TOP)
                self.assertEqual(flags, grid.win32con.SWP_NOSIZE | grid.win32con.SWP_NOACTIVATE)
                rectangles[hwnd] = (x, y, x + right - left, y + bottom - top)
            else:
                self.assertEqual(flags, grid.win32con.SWP_NOMOVE |
                                 grid.win32con.SWP_NOZORDER | grid.win32con.SWP_NOACTIVATE)
                resized_widths.append(width)
                rectangles[hwnd] = (left, top, left + max(width, minimum_width), top + height)

        with patch.object(grid, "_get_roblox_windows", return_value=windows), \
                patch.object(grid, "_get_cursor_monitor_work_area", return_value=work_area), \
                patch.object(grid.win32gui, "IsIconic", side_effect=lambda hwnd: hwnd in minimized), \
                patch.object(grid.win32gui, "ShowWindow") as restore, \
                patch.object(grid.win32gui, "GetWindowRect", side_effect=rectangles.__getitem__), \
                patch.object(grid.win32gui, "GetClientRect", side_effect=lambda hwnd: (
                    0, 0, rectangles[hwnd][2] - rectangles[hwnd][0] - frame_size[0],
                    rectangles[hwnd][3] - rectangles[hwnd][1] - frame_size[1],
                )), \
                patch.object(grid.win32gui, "SetWindowPos", side_effect=move):
            result = grid.tile_roblox_windows()
        return result, rectangles, restore, resized_widths

    def assert_in_work_area(self, rectangles, work_area):
        left, top, right, bottom = work_area
        for rectangle in rectangles.values():
            self.assertGreaterEqual(rectangle[0], left + 4)
            self.assertGreaterEqual(rectangle[1], top + 4)
            self.assertLessEqual(rectangle[2], right - 4)
            self.assertLessEqual(rectangle[3], bottom - 4)

    def assert_widescreen(self, rectangles, frame_size=(16, 39)):
        for left, top, right, bottom in rectangles.values():
            client_width = right - left - frame_size[0]
            client_height = bottom - top - frame_size[1]
            self.assertAlmostEqual(client_height, client_width * 9 / 16, delta=0.5)

    def test_nine_windows_fill_columns_with_widescreen_game_areas(self):
        work_area = (0, 0, 3440, 1392)
        result, rectangles, restore, _ = self.tile(9, work_area)
        self.assertTrue(result)
        self.assertEqual(result.data, {"count": 9, "columns": 3, "rows": 3})
        self.assert_in_work_area(rectangles, work_area)
        self.assertEqual([rectangles[hwnd][1] for hwnd in (1, 4, 7)], [4, 360, 717])
        self.assertEqual([rectangles[hwnd][0] for hwnd in (1, 2, 3)], [4, 1150, 2297])
        self.assertEqual([rectangles[hwnd][2] for hwnd in (1, 2, 3)], [1142, 2289, 3436])
        self.assert_widescreen(rectangles)
        self.assertEqual(rectangles[9][3], work_area[3] - 4)
        self.assertGreater(rectangles[1][3], rectangles[4][1])
        restore.assert_not_called()

    def test_two_windows_fill_both_halves_side_by_side(self):
        work_area = (-3440, 32, 0, 1424)
        result, rectangles, _, _ = self.tile(2, work_area)
        self.assertTrue(result)
        self.assertEqual(result.data, {"count": 2, "columns": 2, "rows": 1})
        self.assertEqual(rectangles[1], (-3436, 36, -1724, 1420))
        self.assertEqual(rectangles[2], (-1716, 36, -4, 1420))
        self.assert_in_work_area(rectangles, work_area)

    def test_three_windows_use_two_columns_with_widescreen_game_areas(self):
        result, rectangles, _, _ = self.tile(3, (0, 0, 2560, 1392))
        self.assertTrue(result)
        self.assertEqual(result.data, {"count": 3, "columns": 2, "rows": 2})
        self.assertEqual(rectangles[1], (4, 4, 1276, 750))
        self.assertEqual(rectangles[2], (1284, 4, 2556, 750))
        self.assertEqual(rectangles[3], (4, 642, 1276, 1388))
        self.assert_widescreen(rectangles)

    def test_ten_windows_do_not_overlap_horizontally(self):
        work_area = (0, 0, 3440, 1392)
        for minimum_width, columns in ((0, 4), (900, 3)):
            with self.subTest(minimum_width=minimum_width):
                result, rectangles, _, _ = self.tile(10, work_area, minimum_width=minimum_width)
                self.assertTrue(result)
                self.assertEqual(result.data["columns"], columns)
                self.assert_in_work_area(rectangles, work_area)
                for hwnd in range(1, 10):
                    if hwnd % columns:
                        self.assertLessEqual(rectangles[hwnd][2], rectangles[hwnd + 1][0])
                self.assert_widescreen(rectangles)

    def test_taller_stacks_are_on_the_left_and_windows_fill_rows_in_order(self):
        for count, expected_counts in ((5, [2, 2, 1]), (8, [3, 3, 2]), (10, [3, 3, 2, 2])):
            with self.subTest(count=count):
                result, rectangles, _, _ = self.tile(count, (0, 0, 3440, 1392))
                self.assertTrue(result)
                column_lefts = sorted({rect[0] for rect in rectangles.values()})
                self.assertEqual([
                    sum(rect[0] == left for rect in rectangles.values())
                    for left in column_lefts
                ], expected_counts)
                for hwnd in range(1, count):
                    before, after = rectangles[hwnd], rectangles[hwnd + 1]
                    if before[1] == after[1]:
                        self.assertLess(before[0], after[0])
                    else:
                        self.assertLess(before[1], after[1])

    def test_previously_tall_windows_are_resized_to_widescreen(self):
        result, rectangles, _, _ = self.tile(10, (0, 0, 3440, 1392), window_size=(845, 1384))
        self.assertTrue(result)
        self.assert_widescreen(rectangles)

    def test_widescreen_sizing_accounts_for_different_window_borders(self):
        for frame_size in ((0, 0), (16, 39), (24, 59)):
            with self.subTest(frame_size=frame_size):
                result, rectangles, _, _ = self.tile(9, (0, 0, 3440, 1392), frame_size=frame_size)
                self.assertTrue(result)
                self.assert_widescreen(rectangles, frame_size)

    def test_incomplete_row_keeps_the_same_column_widths(self):
        result, rectangles, _, _ = self.tile(5, (0, 0, 3441, 1392))
        self.assertTrue(result)
        self.assertEqual(result.data, {"count": 5, "columns": 3, "rows": 2})
        self.assertEqual(rectangles[4][0:3:2], rectangles[1][0:3:2])
        self.assertEqual(rectangles[5][0:3:2], rectangles[2][0:3:2])
        self.assertEqual(rectangles[4][2] - rectangles[4][0], 1139)
        self.assertEqual(rectangles[5][2] - rectangles[5][0], 1139)

    def test_minimum_width_reduces_columns_instead_of_overlapping_horizontally(self):
        work_area = (0, 0, 1920, 1040)
        result, rectangles, _, widths = self.tile(9, work_area, minimum_width=800)
        self.assertTrue(result)
        self.assertEqual(result.data, {"count": 9, "columns": 2, "rows": 5})
        self.assertEqual(widths, [632] * 9 + [952] * 9)
        self.assert_in_work_area(rectangles, work_area)
        self.assertLessEqual(rectangles[1][2], rectangles[2][0])
        self.assertEqual(rectangles[9][3], work_area[3] - 4)
        self.assert_widescreen(rectangles)

    def test_two_windows_fall_back_to_one_column_when_halves_are_too_narrow(self):
        work_area = (0, 0, 1280, 984)
        result, rectangles, _, _ = self.tile(2, work_area, minimum_width=800)
        self.assertTrue(result)
        self.assertEqual(result.data, {"count": 2, "columns": 1, "rows": 2})
        self.assertEqual(rectangles[1], (4, 4, 1276, 488))
        self.assertEqual(rectangles[2], (4, 496, 1276, 980))
        self.assert_in_work_area(rectangles, work_area)

    def test_monitor_narrower_than_one_window_reports_failure(self):
        result, _, _, _ = self.tile(3, (0, 0, 700, 1040), minimum_width=800)
        self.assertFalse(result)
        self.assertEqual(result.code, "WINDOW_GRID_MONITOR_TOO_NARROW")

    def test_positions_fit_offset_and_portrait_monitors(self):
        for work_area in ((-1920, -200, 0, 840), (3440, 1440, 4720, 2112),
                          (48, 32, 1080, 1920)):
            with self.subTest(work_area=work_area):
                result, rectangles, _, _ = self.tile(9, work_area, (640, 500), minimum_width=600)
                self.assertTrue(result)
                self.assert_in_work_area(rectangles, work_area)
                self.assertEqual(rectangles[1][:2], (work_area[0] + 4, work_area[1] + 4))
                self.assert_widescreen(rectangles)

    def test_single_window_fills_the_monitor_work_area(self):
        result, rectangles, _, _ = self.tile(1, (-1280, 0, 0, 984))
        self.assertTrue(result)
        self.assertEqual(rectangles[1], (-1276, 4, -4, 980))

    def test_widescreen_height_is_limited_by_the_monitor_work_area(self):
        work_area = (0, 0, 5120, 1040)
        result, rectangles, _, _ = self.tile(3, work_area)
        self.assertTrue(result)
        self.assert_in_work_area(rectangles, work_area)
        self.assertEqual({rect[3] - rect[1] for rect in rectangles.values()}, {1032})

    def test_only_minimized_windows_are_restored(self):
        result, _, restore, _ = self.tile(8, (0, 0, 2560, 1392), minimized=(4,))
        self.assertTrue(result)
        restore.assert_called_once_with(4, grid.win32con.SW_RESTORE)

    def test_closed_window_does_not_prevent_other_windows_from_fitting(self):
        work_area = (0, 0, 2560, 1392)
        result, rectangles, _, _ = self.tile(8, work_area, failed=(4,))
        self.assertTrue(result)
        self.assertEqual(result.data["count"], 7)
        self.assert_in_work_area({hwnd: rect for hwnd, rect in rectangles.items() if hwnd != 4}, work_area)

    def test_no_windows_reports_existing_failure(self):
        result, _, restore, _ = self.tile(0, (0, 0, 2560, 1392))
        self.assertFalse(result)
        self.assertEqual(result.code, "ROBLOX_WINDOWS_NOT_FOUND")
        restore.assert_not_called()

    def test_all_moves_failing_reports_existing_failure(self):
        result, _, _, _ = self.tile(2, (0, 0, 2560, 1392), failed=(1, 2))
        self.assertFalse(result)
        self.assertEqual(result.code, "ROBLOX_WINDOWS_MOVE_FAILED")
