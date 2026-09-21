use anyhow::Result;
use serenity::{async_trait, model::{application::Interaction, channel::Message, gateway::{GatewayIntents, Ready}}, prelude::*};
use serenity::builder::{CreateCommand, CreateCommandOption, CreateInteractionResponse, CreateInteractionResponseMessage};
use crate::{config::Config, database::Database, moderation, state::State};

pub struct Handler { pub config: Config, pub db: Database, pub state: State }

pub struct DiscordRuntime {
    pub client: Client,
    pub cache: std::sync::Arc<serenity::cache::Cache>,
}

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        tracing::info!("VoidFlame System connected as {} in {} guilds", ready.user.name, ready.guilds.len());

        let commands = vec![
            CreateCommand::new("info").description("Show bot information"),
            CreateCommand::new("invite").description("Get the bot invite link"),
            CreateCommand::new("support").description("Get the support server"),
            CreateCommand::new("server").description("Show server information"),
            CreateCommand::new("ping").description("Show latency"),
            CreateCommand::new("warn").description("Warn a member")
                .add_option(CreateCommandOption::new(serenity::all::CommandOptionType::User, "user", "Member").required(true))
                .add_option(CreateCommandOption::new(serenity::all::CommandOptionType::String, "reason", "Reason").required(false)),
            CreateCommand::new("maintenance").description("Toggle global maintenance"),
        ];

        if let Err(e) = serenity::all::Command::set_global_commands(&ctx.http, commands).await {
            tracing::error!("slash sync failed: {e}");
        }
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        let Interaction::Command(command) = interaction else { return };
        let name = command.data.name.as_str();

        if *self.state.maintenance.read().await && name != "maintenance" {
            let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new().content("🔧 البوت حاليًا في وضع الصيانة.").ephemeral(true)
            )).await;
            return;
        }

        let text = match name {
            "info" => format!("VoidFlame System\nالسيرفرات: {}", ctx.cache.guilds().len()),
            "ping" => "Pong".into(),
            "support" => "https://discord.gg/jH3vwYJyaB".into(),
            "invite" => format!("https://discord.com/oauth2/authorize?client_id={}&scope=bot%20applications.commands", ctx.cache.current_user().id),
            "server" => command.guild_id.map(|g| format!("Server ID: {}", g.get())).unwrap_or_else(|| "هذا الأمر داخل السيرفر فقط.".into()),
            "maintenance" => {
                if command.user.id.get() != self.config.owner_id {
                    "❌ هذا الأمر للمالك فقط.".into()
                } else {
                    let mut m = self.state.maintenance.write().await;
                    *m = !*m;
                    format!("🔧 الصيانة: {}", if *m { "مفعلة" } else { "متوقفة" })
                }
            },
            "warn" => "⚠️ استخدم !تحذير أو إعدادات التحذيرات من لوحة التحكم.".into(),
            _ => "الأمر غير معروف.".into(),
        };

        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(
            CreateInteractionResponseMessage::new().content(text).ephemeral(true)
        )).await;
    }

    async fn message(&self, ctx: Context, msg: Message) {
        if msg.author.bot { return; }
        let Some(guild) = msg.guild_id else { return; };

        if *self.state.maintenance.read().await && !msg.content.starts_with("!صيانة") { return; }

        if msg.content.starts_with(&self.config.prefix) {
            self.prefix(&ctx, &msg, guild).await;
        }

        let result = moderation::analyze(&msg.content);
        if result.score >= 40 {
            let _ = self.db.log_activity(guild.get(), "moderation", &format!("score={} category={} matched={:?}", result.score, result.category, result.matched), Some(msg.author.id.get())).await;
        }
    }
}

impl Handler {
    async fn prefix(&self, ctx: &Context, msg: &Message, guild: serenity::model::id::GuildId) {
        let raw = msg.content.strip_prefix(&self.config.prefix).unwrap_or(&msg.content).trim();
        let mut parts = raw.splitn(2, ' ');
        let command = parts.next().unwrap_or("");
        let args = parts.next().unwrap_or("").trim();

        match command {
            "بينج" | "ping" => { let _ = msg.channel_id.say(&ctx.http, "Pong").await; }
            "اوامر" | "help" => { let _ = msg.channel_id.say(&ctx.http, "!اوامر | !بينج | !تحذير | !صيانة | !تكت | !تذكرة | !توب").await; }
            "صيانة" => {
                if msg.author.id.get() != self.config.owner_id {
                    let _ = msg.channel_id.say(&ctx.http, "❌ هذا الأمر للمالك فقط.").await;
                } else {
                    let mut m = self.state.maintenance.write().await;
                    *m = !*m;
                    let _ = msg.channel_id.say(&ctx.http, format!("🔧 الصيانة: {}", if *m { "مفعلة" } else { "متوقفة" })).await;
                }
            }
            "تحذير" | "warn" => {
                let id = args.split_whitespace().next().and_then(|v| v.parse::<u64>().ok());
                if let Some(user_id) = id {
                    match self.db.add_warning(guild.get(), user_id, msg.author.id.get(), args).await {
                        Ok(n) => { let _ = msg.channel_id.say(&ctx.http, format!("⚠️ تم تسجيل التحذير رقم #{n}.")).await; }
                        Err(_) => { let _ = msg.channel_id.say(&ctx.http, "❌ تعذر تسجيل التحذير.").await; }
                    }
                } else {
                    let _ = msg.channel_id.say(&ctx.http, "❌ استخدم: !تحذير <معرف العضو> <السبب>").await;
                }
            }
            _ => {}
        }

        let _ = self.db.log_activity(guild.get(), "command", &msg.content, Some(msg.author.id.get())).await;
    }
}

pub async fn build(config: Config, db: Database, state: State) -> Result<DiscordRuntime> {
    let intents = GatewayIntents::GUILDS | GatewayIntents::GUILD_MEMBERS | GatewayIntents::GUILD_MESSAGES | GatewayIntents::MESSAGE_CONTENT | GatewayIntents::GUILD_PRESENCES;
    let client = Client::builder(&config.token, intents)
        .event_handler(Handler { config, db, state })
        .await?;
    let cache = client.cache.clone();
    Ok(DiscordRuntime { client, cache })
}

impl DiscordRuntime {
    pub async fn start(mut self) -> Result<()> {
        self.client.start_autosharded().await?;
        Ok(())
    }
}
