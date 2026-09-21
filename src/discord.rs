use anyhow::Result;
use serenity::{async_trait,model::{channel::Message,gateway::{Ready,GatewayIntents},application::Interaction,id::GuildId},prelude::*};
use serenity::builder::{CreateCommand,CreateCommandOption,CreateInteractionResponse,CreateInteractionResponseMessage};
use crate::{config::Config,database::Database,moderation,state::State};

pub struct Handler{pub config:Config,pub db:Database,pub state:State}

#[async_trait]
impl EventHandler for Handler{
 async fn ready(&self,ctx:Context,ready:Ready){
  tracing::info!("VoidFlame System connected as {} in {} guilds",ready.user.name,ready.guilds.len());
  let commands=vec![
   CreateCommand::new("info").description("Show bot information"),
   CreateCommand::new("invite").description("Get the bot invite link"),
   CreateCommand::new("support").description("Get the support server"),
   CreateCommand::new("server").description("Show server information"),
   CreateCommand::new("ping").description("Show latency"),
   CreateCommand::new("warn").description("Warn a member")
    .add_option(CreateCommandOption::new(serenity::all::CommandOptionType::User,"user","Member").required(true))
    .add_option(CreateCommandOption::new(serenity::all::CommandOptionType::String,"reason","Reason").required(false)),
   CreateCommand::new("maintenance").description("Toggle global maintenance"),
  ];
  if let Err(e)=serenity::all::Command::set_global_commands(&ctx.http,commands).await{tracing::error!("slash sync failed: {e}");}
 }
 async fn interaction_create(&self,ctx:Context,interaction:Interaction){
  if let Interaction::Command(command)=interaction{
   let name=command.data.name.as_str();
   if *self.state.maintenance.read().await && name!="maintenance"{
    let _=command.create_response(&ctx.http,CreateInteractionResponse::Message(CreateInteractionResponseMessage::new("🔧 البوت حاليًا في وضع الصيانة.").ephemeral(true))).await; return;
   }
   let text=match name{
    "info"=>format!("VoidFlame System\nالسيرفرات: {}",ctx.cache.guilds().len()),
    "ping"=>"Pong".into(),
    "support"=>"https://discord.gg/jH3vwYJyaB".into(),
    "invite"=>format!("https://discord.com/oauth2/authorize?client_id={}&scope=bot%20applications.commands",ctx.cache.current_user().id),
    "server"=>command.guild_id.map(|g|format!("Server ID: {}",g.get())).unwrap_or_else(||"هذا الأمر داخل السيرفر فقط.".into()),
    "maintenance"=>{if command.user.id.get()!=self.config.owner_id{"❌ هذا الأمر للمالك فقط.".into()}else{let mut m=self.state.maintenance.write().await;*m=!*m;format!("🔧 الصيانة: {}",if *m{"مفعلة"}else{"متوقفة"})}},
    "warn"=>"⚠️ استخدم !تحذير أو إعدادات التحذيرات من لوحة التحكم.".into(),
    _=>"الأمر غير معروف.".into()
   };
   let _=command.create_response(&ctx.http,CreateInteractionResponse::Message(CreateInteractionResponseMessage::new(text).ephemeral(true))).await;
  }
 }
 async fn message(&self,ctx:Context,msg:Message){
  if msg.author.bot{return} let Some(guild)=msg.guild_id else{return};
  if *self.state.maintenance.read().await && !msg.content.starts_with("!صيانة"){return}
  if msg.content.starts_with(&self.config.prefix){self.prefix(&ctx,&msg,guild).await}
  let result=moderation::analyze(&msg.content);
  if result.score>=40{let _=self.db.log(guild.get(),Some(msg.author.id.get()),"moderation",&format!("score={} category={} matched={:?}",result.score,result.category,result.matched)).await;}
 }
}
impl Handler{
 async fn prefix(&self,ctx:&Context,msg:&Message,guild:GuildId){
  let raw=msg.content.trim_start_matches(&self.config.prefix).trim();let mut p=raw.splitn(2,' ');let cmd=p.next().unwrap_or("");let args=p.next().unwrap_or("").trim();
  match cmd{
   "بينج"|"ping"=>{let _=msg.channel_id.say(&ctx.http,"Pong").await},
   "اوامر"|"help"=>{let _=msg.channel_id.say(&ctx.http,"!اوامر | !بينج | !تحذير | !صيانة | !تكت | !تذكرة | !توب").await},
   "صيانة"=>{if msg.author.id.get()!=self.config.owner_id{let _=msg.channel_id.say(&ctx.http,"❌ هذا الأمر للمالك فقط.").await;return}let mut m=self.state.maintenance.write().await;*m=!*m;let _=msg.channel_id.say(&ctx.http,format!("🔧 الصيانة: {}",if *m{"مفعلة"}else{"متوقفة"})).await},
   "تحذير"|"warn"=>{if let Ok(id)=args.split_whitespace().next().unwrap_or("").parse::<u64>(){match self.db.add_warning(guild.get(),id,msg.author.id.get(),args).await{Ok(n)=>{let _=msg.channel_id.say(&ctx.http,format!("⚠️ تم تسجيل التحذير رقم #{n}.")).await},Err(_)=>{let _=msg.channel_id.say(&ctx.http,"❌ تعذر تسجيل التحذير.").await}}}},
   _=>{}
  }
  let _=self.db.log(guild.get(),Some(msg.author.id.get()),"command",&msg.content).await;
 }
}
pub struct DiscordRuntime{pub client:Client}
pub async fn build(config:Config,db:Database,state:State)->Result<DiscordRuntime>{
 let intents=GatewayIntents::GUILDS|GatewayIntents::GUILD_MEMBERS|GatewayIntents::GUILD_MESSAGES|GatewayIntents::MESSAGE_CONTENT|GatewayIntents::GUILD_PRESENCES;
 Ok(DiscordRuntime{client:Client::builder(&config.token,intents).event_handler(Handler{config,db,state}).await?})
}