use std::{net::SocketAddr, sync::Arc};

use axum::{
    extract::State,
    response::Json,
    routing::get,
    Router,
};
use serde::Serialize;
use serenity::cache::Cache;
use tower_http::{
    compression::CompressionLayer,
    trace::TraceLayer,
};

use crate::config::Config;

#[derive(Clone)]
struct AppState {
    cache: Arc<Cache>,
}

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
    bot_ready: bool,
    guilds: usize,
}

pub async fn serve(config: Config, cache: Arc<Cache>) -> anyhow::Result<()> {
    let state = AppState { cache };

    let app = Router::new()
        .route("/health", get(health))
        .with_state(state)
        .layer(CompressionLayer::new())
        .layer(TraceLayer::new_for_http());

    let address: SocketAddr = format!("{}:{}", config.host, config.port).parse()?;
    let listener = tokio::net::TcpListener::bind(address).await?;

    tracing::info!("Dashboard listening on http://{}", address);

    axum::serve(listener, app).await?;
    Ok(())
}

async fn health(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok",
        bot_ready: !state.cache.guilds().is_empty(),
        guilds: state.cache.guilds().len(),
    })
}
