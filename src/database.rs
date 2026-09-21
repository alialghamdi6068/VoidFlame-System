use anyhow::{Context, Result};
use serde_json::{json, Value};
use sqlx::{sqlite::SqlitePoolOptions, Pool, Row, Sqlite};
use std::time::Duration;

#[derive(Clone)]
pub struct Database {
    pool: Pool<Sqlite>,
}

impl Database {
    pub async fn connect(url: &str) -> Result<Self> {
        let url = if url.starts_with("sqlite://") {
            url.to_owned()
        } else if url.starts_with("sqlite:") {
            url.to_owned()
        } else {
            format!("sqlite://{}?mode=rwc", url)
        };

        let pool = SqlitePoolOptions::new()
            .max_connections(8)
            .acquire_timeout(Duration::from_secs(15))
            .connect(&url)
            .await
            .context("failed to connect to SQLite")?;

        Ok(Self { pool })
    }

    pub async fn init(&self) -> Result<()> {
        sqlx::query("PRAGMA journal_mode=WAL").execute(&self.pool).await?;
        sqlx::query("PRAGMA busy_timeout=30000").execute(&self.pool).await?;

        let statements = [
            "CREATE TABLE IF NOT EXISTS guild_settings (guild_id INTEGER PRIMARY KEY, data TEXT NOT NULL DEFAULT '{}')",
            "CREATE TABLE IF NOT EXISTS global_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')",
            "CREATE TABLE IF NOT EXISTS warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS levels (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, xp INTEGER NOT NULL DEFAULT 0, level INTEGER NOT NULL DEFAULT 0, last_message REAL NOT NULL DEFAULT 0, PRIMARY KEY(guild_id,user_id))",
            "CREATE TABLE IF NOT EXISTS afk (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(guild_id,user_id))",
            "CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER UNIQUE NOT NULL, user_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, closed_at TEXT, ticket_number INTEGER)",
            "CREATE TABLE IF NOT EXISTS applications (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT)",
            "CREATE TABLE IF NOT EXISTS suggestions (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, message_id INTEGER, content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER, prize TEXT NOT NULL, winners INTEGER NOT NULL DEFAULT 1, ends_at REAL NOT NULL, ended INTEGER NOT NULL DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, text TEXT NOT NULL, due_at REAL NOT NULL, sent INTEGER NOT NULL DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS schedules (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, text TEXT NOT NULL, due_at REAL NOT NULL, sent INTEGER NOT NULL DEFAULT 0)",
        ];
        for sql in statements {
            sqlx::query(sql).execute(&self.pool).await?;
        }

        sqlx::query("CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_guild_number ON tickets(guild_id,ticket_number)")
            .execute(&self.pool).await?;
        sqlx::query("CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_open_user ON tickets(guild_id,user_id) WHERE status='open'")
            .execute(&self.pool).await?;
        Ok(())
    }

    pub async fn get_guild_data(&self, guild_id: u64) -> Result<Value> {
        let row = sqlx::query("SELECT data FROM guild_settings WHERE guild_id=?")
            .bind(guild_id as i64).fetch_optional(&self.pool).await?;
        Ok(row.map(|r| serde_json::from_str(r.get::<String,_>("data").as_str()).unwrap_or_else(|_| json!({}))).unwrap_or_else(|| json!({})))
    }

    pub async fn set_guild_data(&self, guild_id: u64, data: &Value) -> Result<()> {
        sqlx::query("INSERT INTO guild_settings(guild_id,data) VALUES(?,?) ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data")
            .bind(guild_id as i64).bind(serde_json::to_string(data)?).execute(&self.pool).await?;
        Ok(())
    }

    pub async fn log_activity(&self, guild_id: u64, action: &str, details: &str, user_id: Option<u64>) -> Result<()> {
        sqlx::query("INSERT INTO activity(guild_id,user_id,action,details) VALUES(?,?,?,?)")
            .bind(guild_id as i64).bind(user_id.map(|v| v as i64)).bind(action).bind(details)
            .execute(&self.pool).await?;
        Ok(())
    }

    pub async fn add_warning(&self, guild_id: u64, user_id: u64, moderator_id: u64, reason: &str) -> Result<i64> {
        let result = sqlx::query("INSERT INTO warnings(guild_id,user_id,moderator_id,reason) VALUES(?,?,?,?)")
            .bind(guild_id as i64).bind(user_id as i64).bind(moderator_id as i64).bind(reason)
            .execute(&self.pool).await?;
        Ok(result.last_insert_rowid())
    }

    pub async fn warning_count(&self, guild_id: u64, user_id: u64) -> Result<i64> {
        let row = sqlx::query("SELECT COUNT(*) AS count FROM warnings WHERE guild_id=? AND user_id=?")
            .bind(guild_id as i64).bind(user_id as i64).fetch_one(&self.pool).await?;
        Ok(row.get("count"))
    }
}
