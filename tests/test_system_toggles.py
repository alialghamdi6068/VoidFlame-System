import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SYSTEMS = {
    "welcome": "welcome_enabled",
    "tickets": "tickets_enabled",
    "applications": "applications_enabled",
    "levels": "levels_enabled",
    "autoreply": "autoreply_enabled",
    "giveaways": "giveaways_enabled",
    "suggestions": "suggestions_enabled",
    "logs": "logs_enabled",
    "autorole": "autorole_enabled",
    "announcements": "announcements_enabled",
    "reminders": "reminders_enabled",
    "scheduler": "scheduler_enabled",
    "afk": "afk_enabled",
}


class SystemToggleTests(unittest.TestCase):
    def test_api_and_dashboard_define_the_same_system_toggles(self):
        api = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
        script = (ROOT / "static" / "script.js").read_text(encoding="utf-8")
        for system, setting in SYSTEMS.items():
            self.assertIn(f"'{setting}'", api, f"API missing {setting}")
            self.assertRegex(
                script,
                rf"{re.escape(system)}\s*:\s*['\"]{re.escape(setting)}['\"]",
                f"dashboard missing {system} toggle",
            )

    def test_runtime_cogs_honor_their_dashboard_toggle(self):
        for system, setting in SYSTEMS.items():
            source = (ROOT / "cogs" / f"{system}.py").read_text(encoding="utf-8")
            self.assertIn(setting, source, f"{system} runtime does not reference {setting}")

    def test_ticket_interactions_honor_runtime_toggle(self):
        source = (ROOT / "cogs" / "tickets.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("tickets_enabled', True) is False"), 8)
        self.assertIn('status="open" AND channel_id<>?', source)

    def test_dashboard_settings_are_audited(self):
        source = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
        self.assertIn("from database import get_guild_data, update_guild_data, log_activity", source)
        self.assertIn("dashboard_settings_update", source)
        self.assertIn("settings_cache.invalidate(guild_id)", source)

    def test_database_module_is_syntax_valid(self):
        ast.parse((ROOT / "database.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
