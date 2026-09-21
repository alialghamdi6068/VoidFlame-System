mod config;
mod database;
mod dashboard;
mod discord;
mod moderation;
mod state;

use anyhow::Result;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(std::env::var("RUST_LOG").unwrap_or_else(|_| "voidflame_system=info,tower_http=info".into()))
        .init();

    let config = config::Config::from_env()?;
    let db = database::Database::connect(&config.database_url).await?;
    db.init().await?;
    let state = state::State::new();

    let bot = discord::build(config.clone(), db.clone(), state.clone()).await?;
    let cache = bot.cache.clone();
    let dashboard = dashboard::serve(config, db, cache, state);

    tokio::select! {
        result = bot.start() => result?,
        result = dashboard => result?,
        _ = tokio::signal::ctrl_c() => {}
    }

    Ok(())
}
