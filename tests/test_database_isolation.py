import os
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ["DISCORD_TOKEN"] = "test-token"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["DATABASE_PATH"] = str(Path(_TMP.name) / "flame-test.db")

from database import connection, init_db  # noqa: E402


class DatabaseIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        with connection() as conn:
            conn.execute("DELETE FROM tickets")
            conn.execute("DELETE FROM guild_settings")

    def test_ticket_numbers_are_independent_per_guild(self):
        with connection() as conn:
            conn.execute(
                "INSERT INTO tickets(guild_id,channel_id,user_id,ticket_number) VALUES(?,?,?,?)",
                (100, 1001, 2001, 1),
            )
            conn.execute(
                "INSERT INTO tickets(guild_id,channel_id,user_id,ticket_number) VALUES(?,?,?,?)",
                (200, 2001, 3001, 1),
            )
            next_a = conn.execute(
                "SELECT COALESCE(MAX(ticket_number), 0) + 1 FROM tickets WHERE guild_id=?",
                (100,),
            ).fetchone()[0]
            next_b = conn.execute(
                "SELECT COALESCE(MAX(ticket_number), 0) + 1 FROM tickets WHERE guild_id=?",
                (200,),
            ).fetchone()[0]

        self.assertEqual(next_a, 2)
        self.assertEqual(next_b, 2)

    def test_guild_settings_are_isolated(self):
        with connection() as conn:
            conn.execute(
                "INSERT INTO guild_settings(guild_id,data) VALUES(?,?)",
                (100, '{"ticket_panel_channel_id":"111"}'),
            )
            conn.execute(
                "INSERT INTO guild_settings(guild_id,data) VALUES(?,?)",
                (200, '{"ticket_panel_channel_id":"222"}'),
            )
            first = conn.execute(
                "SELECT data FROM guild_settings WHERE guild_id=?",
                (100,),
            ).fetchone()[0]
            second = conn.execute(
                "SELECT data FROM guild_settings WHERE guild_id=?",
                (200,),
            ).fetchone()[0]

        self.assertIn("111", first)
        self.assertNotIn("222", first)
        self.assertIn("222", second)
        self.assertNotIn("111", second)


if __name__ == "__main__":
    unittest.main()
