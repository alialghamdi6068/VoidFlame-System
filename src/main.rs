mod config; mod database; mod dashboard; mod discord; mod moderation; mod state;
use anyhow::Result;
#[tokio::main]
async fn main()->Result<()>{
 tracing_subscriber::fmt().with_env_filter(std::env::var("RUST_LOG").unwrap_or_else(|_|"voidflame_system=info,tower_http=info".into())).init();
 let config=config::Config::from_env()?;
 let db=database::Database::connect(&config.database_url).await?; db.init().await?;
 let state=state::State::new();
 let cache=std::sync::Arc::new(serenity::prelude::Cache::new());
 let dashboard=dashboard::serve(config.clone(),db.clone(),cache,state.clone());
 let mut bot=discord::build(config,db,state).await?;
 tokio::select!{r=bot.client.start_autosharded()=>r?,r=dashboard=>r?,_=tokio::signal::ctrl_c()=>{}}
 Ok(())
}
