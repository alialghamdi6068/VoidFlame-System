use anyhow::{Context, Result};
use sqlx::{sqlite::SqlitePoolOptions, Pool, Postgres, Sqlite};
use std::time::Duration;

#[derive(Clone)]
pub enum Database {
    Sqlite(Pool<Sqlite>),
    Postgres(Pool<Postgres>),
}

impl Database {
    pub async fn connect() -> Result<Self> {
        if let Ok(url) = std::env::var("DATABASE_URL") {
            if url.starts_with("postgres://") || url.starts_with("postgresql://") {
                let pool = sqlx::postgres::PgPoolOptions::new()
                    .max_connections(20)
                    .acquire_timeout(Duration::from_secs(10))
                    .connect(&url)
                    .await
                    .context("failed to connect to PostgreSQL")?;
                return Ok(Self::Postgres(pool));
            }
            if url.starts_with("sqlite:") {
                let pool = SqlitePoolOptions::new()
                    .max_connections(8)
                    .acquire_timeout(Duration::from_secs(10))
                    .connect(&url)
                    .await
                    .context("failed to connect to SQLite")?;
                return Ok(Self::Sqlite(pool));
            }
        }

        let path = std::env::var("DATABASE_PATH").unwrap_or_else(|_| "data/flame.db".into());
        let url = if path.starts_with("sqlite:") {
            path
        } else {
            format!("sqlite://{path}?mode=rwc")
        };
        let pool = SqlitePoolOptions::new()
            .max_connections(8)
            .acquire_timeout(Duration::from_secs(10))
            .connect(&url)
            .await
            .context("failed to connect to fallback SQLite database")?;
        Ok(Self::Sqlite(pool))
    }

    pub async fn init(&self) -> Result<()> {
        match self {
            Self::Sqlite(pool) => {
                sqlx::query("PRAGMA journal_mode=WAL").execute(pool).await?;
                sqlx::query("PRAGMA busy_timeout=30000").execute(pool).await?;
                sqlx::query("CREATE TABLE IF NOT EXISTS guild_settings (guild_id INTEGER PRIMARY KEY, data TEXT NOT NULL DEFAULT '{}')")
                    .execute(pool).await?;
                sqlx::query("CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
                    .execute(pool).await?;
            }
            Self::Postgres(pool) => {
                sqlx::query("CREATE TABLE IF NOT EXISTS guild_settings (guild_id BIGINT PRIMARY KEY, data JSONB NOT NULL DEFAULT '{}'::jsonb)")
                    .execute(pool).await?;
                sqlx::query("CREATE TABLE IF NOT EXISTS activity (id BIGSERIAL PRIMARY KEY, guild_id BIGINT, user_id BIGINT, action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
                    .execute(pool).await?;
            }
        }
        Ok(())
    }

    pub async fn log_activity(&self, guild_id: u64, action: &str, details: &str, user_id: Option<u64>) -> Result<()> {
        match self {
            Self::Sqlite(pool) => {
                sqlx::query("INSERT INTO activity (guild_id,user_id,action,details) VALUES (?,?,?,?)")
                    .bind(guild_id as i64).bind(user_id.map(|v| v as i64)).bind(action).bind(details)
                    .execute(pool).await?;
            }
            Self::Postgres(pool) => {
                sqlx::query("INSERT INTO activity (guild_id,user_id,action,details) VALUES ($1,$2,$3,$4)")
                    .bind(guild_id as i64).bind(user_id.map(|v| v as i64)).bind(action).bind(details)
                    .execute(pool).await?;
            }
        }
        Ok(())
    }
}
