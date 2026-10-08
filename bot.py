import asyncio
import discord
from discord.ext import commands

from config import BOT_PREFIX, BOT_NAME, HOST, PORT, DISCORD_TOKEN, OWNER_ID, INSTANCE_GUILD_ID, INSTANCE_ID
from database import init_db, start_database_backups
from cogs.maintenance import is_maintenance

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
# Presence, voice and typing intents stay disabled to keep all four instances lightweight.

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)
bot.instance_id = INSTANCE_ID or "default"
bot.instance_name = BOT_NAME
bot.instance_guild_id = INSTANCE_GUILD_ID
bot.owner_id = OWNER_ID
bot._slash_synced = False

async def load_core():
    for extension in ("cogs.maintenance", "services.system_manager"):
        try:
            await bot.load_extension(extension)
            print(f"[{BOT_NAME}] Loaded {extension}")
        except Exception as exc:
            print(f"[{BOT_NAME}] Failed to load {extension}: {type(exc).__name__}: {exc}")
            return False
    return True

@bot.event
async def on_message(message):
    if message.author.bot: return
    original = message.content.strip()
    if is_maintenance() and original != "!صيانة": return
    await bot.process_commands(message)

@bot.event
async def on_guild_join(guild):
    tickets = bot.get_cog("Tickets")
    if tickets:
        try: tickets.register_persistent_views()
        except Exception as exc: print(f"[{BOT_NAME}] Ticket view registration failed: {type(exc).__name__}: {exc}")

@bot.event
async def on_ready():
    manager = bot.get_cog("SystemManager")
    if manager:
        await manager.bootstrap()
    print(f"[{BOT_NAME}] Logged in as {bot.user} | Guilds: {len(bot.guilds)} | Instance: {bot.instance_id}")
    if not bot._slash_synced:
        try:
            synced = await bot.tree.sync()
            bot._slash_synced = True
            print(f"[{BOT_NAME}] Synced {len(synced)} slash commands.")
        except Exception as exc:
            print(f"[{BOT_NAME}] Slash sync failed: {type(exc).__name__}: {exc}")

@bot.tree.interaction_check
async def maintenance_check(interaction):
    if is_maintenance() and interaction.command and interaction.command.name != "maintenance":
        await interaction.response.send_message("🔧 البوت حاليًا في وضع الصيانة. الأوامر متوقفة مؤقتًا.", ephemeral=True)
        return False
    return True

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    embed = discord.Embed(title="⚠️ تعذر تنفيذ الأمر", color=discord.Color.from_rgb(239,68,68))
    embed.set_footer(text=f"{BOT_NAME} • مركز المساعدة")
    if isinstance(error, commands.MissingRequiredArgument):
        embed.description = f"البيانات المطلوبة ناقصة.\nالمتغير: **{error.param.name}**"
        if ctx.command:
            embed.add_field(name="الاستخدام", value=f"{BOT_PREFIX}{ctx.command.name} {ctx.command.signature or ''}".strip()[:1024], inline=False)
    elif isinstance(error, commands.MissingPermissions): embed.description = "ما عندك الصلاحية المطلوبة لتنفيذ هذا الأمر."
    elif isinstance(error, commands.BotMissingPermissions): embed.description = "البوت يحتاج صلاحية إضافية لتنفيذ هذا الأمر."
    elif isinstance(error, commands.BadArgument): embed.description = "البيانات المرسلة غير صحيحة. تأكد من المنشن أو الرقم أو القيمة المطلوبة."
    elif isinstance(error, commands.NoPrivateMessage): embed.description = "هذا الأمر متاح داخل السيرفر فقط."
    elif isinstance(error, commands.CheckFailure): embed.description = "لم تتحقق شروط استخدام هذا الأمر أو لا تملك الصلاحية المطلوبة."
    else:
        original = getattr(error, "original", error)
        print(f"[{BOT_NAME}] Command error: {type(original).__name__}: {original}")
        embed.description = "حدث خطأ غير متوقع وتم تسجيله للمراجعة. إذا استمر الخطأ، تواصل مع الإدارة."
    try: await ctx.reply(embed=embed, mention_author=False)
    except discord.HTTPException: pass

async def main():
    init_db()
    start_database_backups()
    if not await load_core(): return
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
