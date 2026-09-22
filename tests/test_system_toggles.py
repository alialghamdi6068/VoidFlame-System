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

    def test_ticket_lifecycle_actions_are_audited(self):
        source = (ROOT / "cogs" / "tickets.py").read_text(encoding="utf-8")
        self.assertIn("ticket_close", source)
        self.assertIn("ticket_reopen", source)
        self.assertIn("log_activity(interaction.guild.id", source)

    def test_ticket_reopen_is_audited_once(self):
        source = (ROOT / "cogs" / "tickets.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("log_activity(guild.id, 'ticket_reopen'"), 1)
        self.assertEqual(source.count("تم إعادة فتح التذكرة بواسطة"), 1)

    def test_ticket_close_action_allows_staff_to_reopen_or_delete(self):
        source = (ROOT / "cogs" / "tickets.py").read_text(encoding="utf-8")
        self.assertIn("if interaction.user.id != self.user_id and not interaction.user.guild_permissions.manage_channels:", source)

    def test_combined_logs_cover_core_server_events(self):
        source = (ROOT / "cogs" / "logs.py").read_text(encoding="utf-8")
        for listener in (
            "on_member_join",
            "on_member_remove",
            "on_message_delete",
            "on_message_edit",
            "on_guild_channel_create",
            "on_guild_channel_delete",
            "on_guild_role_create",
            "on_guild_role_delete",
            "on_member_ban",
            "on_member_unban",
        ):
            self.assertIn(listener, source)
        self.assertIn('settings.get("logs_enabled", True) is False', source)
        self.assertIn("log_rate_limited", source)

    def test_dashboard_settings_are_audited(self):
        source = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
        self.assertIn("from database import get_guild_data, update_guild_data, log_activity", source)
        self.assertIn("dashboard_settings_update", source)
        self.assertIn("settings_cache.invalidate(guild_id)", source)

    def test_dashboard_waits_for_gateway_ready_and_cache(self):
        source = (ROOT / "web" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("ready_wait_deadline = time.time() + 15", source)
        self.assertIn("while not bot.is_ready()", source)
        self.assertIn("for _ in range(40)", source)

    def test_dashboard_api_share_resilient_guild_lookup(self):
        source = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
        self.assertIn("ready_wait_deadline = time.time() + 15", source)
        self.assertIn("while not bot.is_ready()", source)
        self.assertIn("for _ in range(40)", source)

    def test_dashboard_server_list_waits_for_gateway_ready(self):
        source = (ROOT / "web" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("bot_ids = set()", source)
        self.assertIn("while not bot.is_ready() and time.time() < ready_wait_deadline", source)
        self.assertIn("if bot_ids or bot.is_ready():", source)
        self.assertIn("bot_installed': guild_id in bot_ids", source)

    def test_dashboard_api_authorization_uses_same_permission_gate(self):
        source = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("if not can_manage_guild(guild):"), 2)
        self.assertIn("غير مصرح لك بإدارة هذا السيرفر.", source)

    def test_dashboard_authorization_uses_current_discord_permissions(self):
        auth = (ROOT / "web" / "auth.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "web" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("current = _managed_guilds_from_token(token)", auth)
        self.assertIn("return guild.id in managed_guild_ids()", dashboard)
        self.assertNotIn("member.guild_permissions.manage_guild", dashboard)

    def test_dashboard_home_is_always_landing_page(self):
        source = (ROOT / "web" / "dashboard.py").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("return render_template('index.html'", source)
        self.assertNotIn("return redirect(url_for('servers'))", source.split("def home()", 1)[1].split("@app.get('/servers')", 1)[0])
        self.assertIn("url_for('servers') if logged_in else url_for('login')", template)
        self.assertIn("{% if logged_in %}", template)

    def test_database_module_is_syntax_valid(self):
        ast.parse((ROOT / "database.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
