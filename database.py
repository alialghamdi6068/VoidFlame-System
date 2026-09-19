import json
import sqlite3
from contextlib import contextmanager

from config import DATABASE_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS global_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS levels (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 0,
    last_message REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(guild_id,user_id)
);
CREATE TABLE IF NOT EXISTS afk (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(guild_id,user_id)
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,
    ticket_number INTEGER
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    message_id INTEGER,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    prize TEXT NOT NULL,
    winners INTEGER NOT NULL DEFAULT 1,
    ends_at REAL NOT NULL,
    ended INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    due_at REAL NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    due_at REAL NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS warning_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_activity_guild_created ON activity(guild_id,created_at);
CREATE INDEX IF NOT EXISTS idx_warnings_guild_user_created ON warnings(guild_id,user_id,created_at);
"""


def init_db():
    with sqlite3.connect(DATABASE_PATH, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.executescript(SCHEMA)

        columns = {row[1] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()}
        if "ticket_number" not in columns:
            conn.execute("ALTER TABLE tickets ADD COLUMN ticket_number INTEGER")

        guild_ids = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT guild_id FROM tickets"
            ).fetchall()
        ]
        for guild_id in guild_ids:
            rows = conn.execute(
                "SELECT id FROM tickets WHERE guild_id=? AND ticket_number IS NULL ORDER BY id",
                (guild_id,),
            ).fetchall()
            next_number = (
                conn.execute(
                    "SELECT COALESCE(MAX(ticket_number), 0) FROM tickets WHERE guild_id=?",
                    (guild_id,),
                ).fetchone()[0]
                or 0
            )
            for row in rows:
                next_number += 1
                conn.execute(
                    "UPDATE tickets SET ticket_number=? WHERE id=?",
                    (next_number, row[0]),
                )

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_guild_number "
            "ON tickets(guild_id, ticket_number)"
        )


@contextmanager
def connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_guild_data(guild_id):
    with connection() as conn:
        row = conn.execute(
            "SELECT data FROM guild_settings WHERE guild_id=?",
            (guild_id,),
        ).fetchone()
        return json.loads(row["data"]) if row else {}


def set_guild_data(guild_id, data):
    guild_id = int(guild_id)
    with connection() as conn:
        conn.execute(
            "INSERT INTO guild_settings(guild_id,data) VALUES(?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data",
            (guild_id, json.dumps(data, ensure_ascii=False)),
        )
    # Keep every write path consistent, including callers that use set_guild_data
    # directly instead of update_guild_data.
    try:
        from services.settings_cache import settings_cache
        settings_cache.invalidate(guild_id)
    except Exception:
        pass


def update_guild_data(guild_id, **changes):
    data = get_guild_data(guild_id)
    data.update(changes)
    set_guild_data(guild_id, data)
    return data


def log_activity(guild_id, action, details="", user_id=None):
    with connection() as conn:
        conn.execute(
            "INSERT INTO activity(guild_id,user_id,action,details) VALUES(?,?,?,?)",
            (guild_id, user_id, action, details),
        )


def get_global_setting(key, default=None):
    with connection() as conn:
        row = conn.execute(
            "SELECT value FROM global_settings WHERE key=?",
            (str(key),),
        ).fetchone()
        return row["value"] if row else default


def set_global_setting(key, value):
    with connection() as conn:
        conn.execute(
            "INSERT INTO global_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(key), str(value)),
        )
