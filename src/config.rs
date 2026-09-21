use anyhow::{Context, Result};
use std::env;

#[derive(Clone)]
pub struct Config {
    pub token: String,
    pub host: String,
    pub port: u16,
    pub database_url: String,
    pub owner_id: u64,
    pub prefix: String,
    pub dashboard_url: String,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        dotenvy::dotenv().ok();
        let token = env::var("DISCORD_TOKEN").context("DISCORD_TOKEN is missing")?;
        if token.trim().is_empty() { anyhow::bail!("DISCORD_TOKEN is empty"); }
        Ok(Self {
            token,
            host: env::var("HOST").unwrap_or_else(|_| "0.0.0.0".into()),
            port: env::var("PORT").ok().and_then(|v| v.parse().ok()).unwrap_or(10000),
            database_url: env::var("DATABASE_URL").unwrap_or_else(|_| "sqlite://data/flame.db".into()),
            owner_id: env::var("OWNER_ID").ok().and_then(|v| v.parse().ok()).unwrap_or(0),
            prefix: env::var("BOT_PREFIX").unwrap_or_else(|_| "!".into()),
            dashboard_url: env::var("DASHBOARD_URL").unwrap_or_else(|_| "https://voidflame.wisp.uno/".into()),
        })
    }
}
