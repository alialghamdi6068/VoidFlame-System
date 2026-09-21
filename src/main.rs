mod config;
mod dashboard;
mod discord;

use anyhow::Result;
use config::Config;
use tracing::info;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            std::env::var("RUST_LOG")
                .unwrap_or_else(|_| "voidflame_system=info,tower_http=info".into()),
        )
        .init();

    let config = Config::from_env()?;
    info!("Starting VoidFlame System in Rust");

    let discord = discord::build_client(&config).await?;
    let dashboard = dashboard::serve(config.clone(), discord.cache.clone());

    tokio::select! {
        result = discord.start() => result?,
        result = dashboard => result?,
        _ = tokio::signal::ctrl_c() => {
            info!("Shutdown signal received");
        }
    }

    Ok(())
}
