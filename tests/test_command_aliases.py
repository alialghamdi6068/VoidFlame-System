import os
import unittest

os.environ["DISCORD_TOKEN"] = "test-token"
os.environ["SESSION_SECRET"] = "test-secret"

from bot import MULTIWORD_ALIASES  # noqa: E402


class CommandAliasTests(unittest.TestCase):
    def test_public_arabic_aliases_have_no_underscore(self):
        required = {
            "!اوامر الادارة": "!اوامر_الادارة",
            "!اعطاء رتبة": "!اعطاء_رتبة",
            "!سحب رتبة": "!سحب_رتبة",
            "!تذكرة": "!تكت",
            "!فتح تذكرة": "!تكت",
        }
        for public_name, internal_name in required.items():
            self.assertEqual(MULTIWORD_ALIASES.get(public_name), internal_name)

    def test_longer_alias_is_selected_before_shorter_alias(self):
        aliases = sorted(MULTIWORD_ALIASES, key=len, reverse=True)
        self.assertLess(aliases.index("!فتح تذكرة"), aliases.index("!تذكرة"))


if __name__ == "__main__":
    unittest.main()
