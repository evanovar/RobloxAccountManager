import unittest

from features import cookie_validator


class CookieValidationSettingsTests(unittest.TestCase):
    def test_validation_is_on_by_default(self):
        self.assertTrue(cookie_validator.validation_enabled({}))

    def test_validation_can_be_turned_off(self):
        self.assertFalse(cookie_validator.validation_enabled({"validate_cookies_on_startup": False}))

    def test_delay_defaults_when_missing_or_invalid(self):
        for settings in ({}, {"cookie_validation_delay_seconds": "slow"}, {"cookie_validation_delay_seconds": None},
                         {"cookie_validation_delay_seconds": float("nan")}):
            with self.subTest(settings=settings):
                self.assertEqual(cookie_validator.get_validation_delay(settings), cookie_validator.DEFAULT_DELAY)

    def test_delay_is_clamped(self):
        low = {"cookie_validation_delay_seconds": 0}
        high = {"cookie_validation_delay_seconds": 9999}
        self.assertEqual(cookie_validator.get_validation_delay(low), cookie_validator.MIN_DELAY)
        self.assertEqual(cookie_validator.get_validation_delay(high), cookie_validator.MAX_DELAY)

    def test_configured_delay_is_used(self):
        self.assertEqual(cookie_validator.get_validation_delay({"cookie_validation_delay_seconds": "4.5"}), 4.5)


if __name__ == "__main__":
    unittest.main()
