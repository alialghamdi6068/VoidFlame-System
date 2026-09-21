use std::{net::SocketAddr, sync::Arc};

use axum::{extract::{Path, State}, response::{Html, Json}, routing::{get, put}, Router};
use serde::{Deserialize, Serialize};
use serenity::{cache::Cache, model::id::GuildId};
use tower_http::{compression::CompressionLayer, trace::TraceLayer};

use crate::{config::Config, database::Database, state::State as BotState};

#[derive(Clone)]
struct AppState {
    cache: Arc<Cache>,
    db: Database,
    bot_state: BotState,
}

#[derive(Serialize)]
struct Status {
    status: &'static str,
    bot_ready: bool,
    guilds: usize,
    maintenance: bool,
}

#[derive(Deserialize)]
struct SettingsPayload {
    settings: serde_json::Value,
}

pub async fn serve(config: Config, db: Database, cache: Arc<Cache>, bot_state: BotState) -> anyhow::Result<()> {
    let app_state = AppState { cache, db, bot_state };
    let app = Router::new()
        .route("/", get(index))
        .route("/health", get(health))
        .route("/api/status", get(status))
        .route("/api/guild/{guild_id}/settings", get(get_settings).put(put_settings))
        .with_state(app_state)
        .layer(CompressionLayer::new())
        .layer(TraceLayer::new_for_http());

    let address: SocketAddr = format!("{}:{}", config.host, config.port).parse()?;
    let listener = tokio::net::TcpListener::bind(address).await?;
    tracing::info!("Dashboard listening on http://{}", address);
    axum::serve(listener, app).await?;
    Ok(())
}

async fn index() -> Html<&'static str> {
    Html(r#"<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VoidFlame System</title><style>body{font-family:system-ui;background:#0b0d12;color:#eee;max-width:900px;margin:50px auto;padding:20px}main{background:#151922;border:1px solid #252b38;border-radius:18px;padding:30px}code{background:#0b0d12;padding:4px 8px;border-radius:8px}</style></head><body><main><h1>VoidFlame System</h1><p>لوحة التحكم تعمل.</p><p>Health: <code>/health</code></p></main></body></html>"#)
}

async fn health(State(s): State<AppState>) -> Json<Status> {
    let maintenance = *s.bot_state.maintenance.read().await;
    Json(Status { status: "ok", bot_ready: !s.cache.guilds().is_empty(), guilds: s.cache.guilds().len(), maintenance })
}

async fn status(State(s): State<AppState>) -> Json<Status> {
    health(State(s)).await
}

async fn get_settings(Path(guild_id): Path<u64>, State(s): State<AppState>) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let guild = s.cache.guilds().iter().any(|id| id.get() == guild_id);
    if !guild {
        return Err((axum::http::StatusCode::NOT_FOUND, "البوت غير موجود في هذا السيرفر.".into()));
    }
    s.db.get_guild_data(guild_id).await.map(Json).map_err(internal)
}

async fn put_settings(Path(guild_id): Path<u64>, State(s): State<AppState>, Json(payload): Json<SettingsPayload>) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    if !s.cache.guilds().iter().any(|id| id.get() == guild_id) {
        return Err((axum::http::StatusCode::NOT_FOUND, "البوت غير موجود في هذا السيرفر.".into()));
    }
    s.db.set_guild_data(guild_id, &payload.settings).await.map_err(internal)?;
    Ok(Json(payload.settings))
}

fn internal<E: std::fmt::Display>(e: E) -> (axum::http::StatusCode, String) {
    (axum::http::StatusCode::INTERNAL_SERVER_ERROR, e.to_string())
}
