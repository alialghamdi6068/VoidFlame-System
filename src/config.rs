use anyhow::{Context, Result};
use std::env;

#[derive(Clone, Debug)]
pub struct Config {
    pub discord_token: String,
    pub host: String,
    pub port: u16,
    pub owner_id: u64,
    pub bot_name: String,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        dotenvy::dotenv().ok();

        let discord_token = env::var("DISCORD_TOKEN")
            .context("DISCORD_TOKEN is missing")?
            .trim()
            .to_owned();

        if discord_token.is_empty() {
            anyhow::bail!("DISCORD_TOKEN is empty");
        }

        let port = env::var("PORT")
            .unwrap_or_else(|_| "10000".into())
            .parse::<u16>()
            .context("PORT must be a valid u16")?;

        let owner_id = env::var("OWNER_ID")
            .unwrap_or_else(|_| "1293157778030071920".into())
            .parse::<u64>()
            .context("OWNER_ID must be a valid Discord user ID")?;

        Ok(Self {
            discord_token,
            host: env::var("HOST").unwrap_or_else(|_| "0.0.0.0".into()),
            port,
            owner_id,
            bot_name: "VoidFlame System".into(),
        })
    }
}
