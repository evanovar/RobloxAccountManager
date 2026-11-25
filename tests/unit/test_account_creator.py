import json
import re
import unittest

from features import account_creator


class SignupScriptTests(unittest.TestCase):
    def profile(self, password="Pa\"ss\\word</script>!1"):
        return {
            "month": "Mar", "day": "07", "year": "1999",
            "usernames": ["FirstName1", "SecondName2"], "password": password,
        }

    def embedded_profile(self, script):
        match = re.search(r"var profile = (\{.*?\});\n", script)
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def test_profile_is_embedded_as_json_without_changes(self):
        profile = self.profile()
        script = account_creator._build_signup_script(profile)
        self.assertNotIn("__PROFILE__", script)
        self.assertEqual(self.embedded_profile(script), profile)

    def test_script_knows_both_signup_layouts(self):
        script = account_creator._build_signup_script(self.profile())
        for marker in ("signup-password", "signup-button", "MaleButton",
                       "signup-v2-password", "'continue'", "'add password'"):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)

    def test_generated_profiles_build_a_script(self):
        profile = account_creator._generate_signup_profile({})
        script = account_creator._build_signup_script(profile)
        self.assertEqual(self.embedded_profile(script)["usernames"], profile["usernames"])


if __name__ == "__main__":
    unittest.main()
