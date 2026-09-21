mod config;
mod database;
mod dashboard;
mod discord;
mod moderation;
mod state;

use anyhow::{Context, Result};
use std::process::Stdio;
use tokio::process::Command;
use tokio::signal;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(std::env::var("RUST_LOG").unwrap_or_else(|_| "voidflame_system=info".into()))
        .init();

    let python = std::env::var("PYTHON_BIN").unwrap_or_else(|_| "python3".into());
    tracing::info!("Starting VoidFlame runtime through Rust supervisor");

    let mut child = Command::new(&python)
        .arg("bot.py")
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .envs(std::env::vars())
        .spawn()
        .with_context(|| format!("failed to start {python} bot.py"))?;

    tokio::select! {
        status = child.wait() => {
            let status = status.context("failed while waiting for VoidFlame runtime")?;
            if !status.success() {
                anyhow::bail!("VoidFlame runtime exited with status {status}");
            }
        }
        signal_result = shutdown_signal() => {
            signal_result.context("failed to listen for shutdown signal")?;
            tracing::info!("Shutdown requested; stopping VoidFlame runtime");
            if let Err(error) = child.kill().await {
                tracing::warn!("Could not stop child process cleanly: {error}");
            }
            let _ = child.wait().await;
        }
    }

    Ok(())
}

async fn shutdown_signal() -> Result<()> {
    #[cfg(unix)]
    {
        let mut terminate = signal::unix::signal(signal::unix::SignalKind::terminate())
            .context("failed to install SIGTERM handler")?;
        tokio::select! {
            _ = signal::ctrl_c() => {}
            _ = terminate.recv() => {}
        }
    }

    #[cfg(not(unix))]
    {
        signal::ctrl_c().await.context("failed to install Ctrl+C handler")?;
    }

    Ok(())
}
