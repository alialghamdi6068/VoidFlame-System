mod config;
mod database;
mod dashboard;
mod discord;
mod moderation;
mod state;

use anyhow::{Context, Result};
use std::process::{Command, Stdio};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(std::env::var("RUST_LOG").unwrap_or_else(|_| "voidflame_system=info".into()))
        .init();

    // Keep the complete, already-tested Python feature surface live while the
    // Rust implementation is migrated behind a stable production entrypoint.
    let python = std::env::var("PYTHON_BIN").unwrap_or_else(|_| "python3".into());
    tracing::info!("Starting complete VoidFlame runtime through Rust supervisor");

    let mut child = Command::new(&python)
        .arg("bot.py")
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .envs(std::env::vars())
        .spawn()
        .with_context(|| format!("failed to start {python} bot.py"))?;

    let status = child.wait().context("VoidFlame runtime stopped unexpectedly")?;
    if !status.success() {
        anyhow::bail!("VoidFlame runtime exited with status {status}");
    }
    Ok(())
}
