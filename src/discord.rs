use anyhow::Result;
use serenity::{
    async_trait,
    model::{
        gateway::Ready,
        id::UserId,
    },
    prelude::*,
};
use tracing::{error, info};

use crate::config::Config;

pub struct Handler {
    pub owner_id: UserId,
}

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, _ctx: Context, ready: Ready) {
        info!(
            "Logged in as {} | Guilds: {}",
            ready.user.tag(),
            ready.guilds.len()
        );
    }
}

pub struct DiscordRuntime {
    client: Client,
    pub cache: std::sync::Arc<Cache>,
}

impl DiscordRuntime {
    pub async fn start(mut self) -> Result<()> {
        self.client
            .start()
            .await
            .map_err(|error| anyhow::anyhow!("Discord client stopped: {error}"))
    }
}

pub async fn build_client(config: &Config) -> Result<DiscordRuntime> {
    let intents = GatewayIntents::GUILDS
        | GatewayIntents::GUILD_MEMBERS
        | GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::MESSAGE_CONTENT
        | GatewayIntents::GUILD_PRESENCES;

    let handler = Handler {
        owner_id: UserId::new(config.owner_id),
    };

    let client = Client::builder(&config.discord_token, intents)
        .event_handler(handler)
        .await?;

    let cache = client.cache.clone();

    Ok(DiscordRuntime { client, cache })
}
