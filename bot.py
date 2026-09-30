import asyncio
import threading

import discord
from discord.ext import commands

from config import BOT_PREFIX, BOT_NAME, HOST, PORT, DISCORD_TOKEN
from database import init_db
from services.settings_cache import settings_cache
from web.app import create_app
from cogs.maintenance import is_maintenance


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)

SYSTEM_COGS = [
    "moderation", "tickets", "applications", "levels", "welcome", "logs",
    "giveaways", "suggestions", "afk", "autoreply", "autorole", "announcements",
    "reminders", "scheduler", "utility", "owner", "messaging",
    "dashboard_commands", "extra_commands", "new_commands", "ai_guard",
    "event_logger", "protector_guard",
]
bot.system_extensions = [f"cogs.{name}" for name in SYSTEM_COGS] + ["maintenance"]
bot._slash_synced = False

app = create_app(bot)

MULTIWORD_ALIASES = {
    "!اوامر الادارة": "!اوامر_الادارة",
    "!فك تايم": "!فك_تايم",
    "!فك ميوت": "!فك_تايم",
    "!فك حظر": "!فك_حظر",
    "!ريست لفل": "!ريست_لفل",
    "!مسح تحذيرات": "!مسح_تحذيرات",
    "!مسح رسائل": "!مسح",
    "!قفل روم": "!قفل_روم",
    "!فتح روم": "!فتح_روم",
    "!انهاء قيفاواي": "!انهاء",
    "!اعادة قيفاواي": "!اعادة",
    "!قبول اقتراح": "!قبول_اقتراح",
    "!رفض اقتراح": "!رفض_اقتراح",
    "!حذف رد": "!حذف_رد",
    "!رتبة تلقائية": "!رتبة_تلقائية",
    "!قيفاواي روم": "!قيفاواي_روم",
    "!قبول تقديم": "!قبول_تقديم",
    "!رفض تقديم": "!رفض_تقديم",
    "!اعطاء رتبة": "!اعطاء_رتبة",
    "!سحب رتبة": "!سحب_رتبة",
    "!تذكرة": "!تكت",
    "!فتح تذكرة": "!تكت",
    "!اعلى دعوات": "!اعلى_دعوات",
    "!رتب السيرفر": "!رتب_السيرفر",
    "!اعضاء اونلاين": "!اعضاء_اونلاين",
    "!احصائيات السيرفر": "!احصائيات_السيرفر",
    "!سجل العضو": "!سجل_العضو",
    "!عمر الحساب": "!عمر_الحساب",
    "!عمر السيرفر": "!عمر_السيرفر",
    "!اختصار الرابط": "!اختصار_الرابط",
    "!وقت عالمي": "!وقت_عالمي",
    "!مساعدة الأمر": "!مساعدة_الأمر",
    "!حظر": "!باند",
    "!ميوت": "!تايم",
    "!بنق": "!بينج",
}


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    original_content = message.content.strip()
    content = message.content

    for public_name, internal_name in sorted(
        MULTIWORD_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if content == public_name or content.startswith(public_name + " "):
            message.content = internal_name + content[len(public_name):]
            break

    if is_maintenance() and original_content != "!صيانة":
        return

    await bot.process_commands(message)


@bot.event
async def on_guild_join(guild):
    tickets = bot.get_cog("Tickets")
    if tickets:
        try:
            tickets.register_persistent_views()
        except Exception as exc:
            print(f"[VoidFlame] Failed to register ticket views for new guild {guild.id}: {exc}")


@bot.event
async def on_ready():
    settings_cache.clear()
    tickets = bot.get_cog("Tickets")
    if tickets:
        try:
            tickets.register_persistent_views()
        except Exception as exc:
            print(f"[{BOT_NAME}] Ticket view registration failed: {type(exc).__name__}: {exc}")

    print(f"[{BOT_NAME}] Logged in as {bot.user} | Guilds: {len(bot.guilds)}")
    if not bot._slash_synced:
        try:
            synced = await bot.tree.sync()
            bot._slash_synced = True
            print(f"[{BOT_NAME}] Synced {len(synced)} slash commands.")
        except Exception as exc:
            print(f"[{BOT_NAME}] Slash sync failed: {type(exc).__name__}: {exc}")


@bot.tree.interaction_check
async def maintenance_check(interaction: discord.Interaction):
    if is_maintenance() and interaction.command and interaction.command.name != "maintenance":
        await interaction.response.send_message(
            "🔧 البوت حاليًا في وضع الصيانة. الأوامر متوقفة مؤقتًا.", ephemeral=True
        )
        return False
    return True


@bot.event
async def on_command(ctx):
    if not ctx.guild or ctx.author.bot:
        return
    logs = bot.get_cog("Logs")
    if logs:
        try:
            await logs.send_log(
                ctx.guild,
                "Command Used",
                f"Command: !{ctx.command.qualified_name}\nChannel: {ctx.channel.mention}\nUser: {ctx.author.mention}",
                actor=ctx.author,
            )
        except Exception as exc:
            print(f"[{BOT_NAME}] Command log failed: {type(exc).__name__}: {exc}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    embed = discord.Embed(
        title="⚠️ تعذر تنفيذ الأمر",
        color=discord.Color.from_rgb(239, 68, 68),
    )
    embed.set_footer(text=f"{BOT_NAME} • مركز المساعدة")

    if isinstance(error, commands.MissingRequiredArgument):
        embed.description = f"البيانات المطلوبة ناقصة.\nالمتغير: **{error.param.name}**"
        if ctx.command:
            usage = f"!{ctx.command.name} {ctx.command.signature or ''}".strip()
            embed.add_field(name="الاستخدام", value=usage[:1024], inline=False)
    elif isinstance(error, commands.MissingPermissions):
        embed.description = "ما عندك الصلاحية المطلوبة لتنفيذ هذا الأمر."
    elif isinstance(error, commands.BotMissingPermissions):
        embed.description = "البوت يحتاج صلاحية إضافية لتنفيذ هذا الأمر."
    elif isinstance(error, commands.BadArgument):
        embed.description = "البيانات المرسلة غير صحيحة. تأكد من المنشن أو الرقم أو القيمة المطلوبة."
    elif isinstance(error, commands.NoPrivateMessage):
        embed.description = "هذا الأمر متاح داخل السيرفر فقط."
    elif isinstance(error, commands.CheckFailure):
        embed.description = "لم تتحقق شروط استخدام هذا الأمر أو لا تملك الصلاحية المطلوبة."
    else:
        original = getattr(error, "original", error)
        print(f"[{BOT_NAME}] Command error: {type(original).__name__}: {original}")
        embed.description = "حدث خطأ غير متوقع وتم تسجيله للمراجعة. إذا استمر الخطأ، تواصل مع الإدارة."

    try:
        await ctx.reply(embed=embed, mention_author=False)
    except discord.HTTPException:
        pass


async def load_cogs():
    try:
        await bot.load_extension("cogs.maintenance")
        print(f"[{BOT_NAME}] Loaded cogs.maintenance")
    except Exception as exc:
        print(f"[{BOT_NAME}] Failed to load cogs.maintenance: {type(exc).__name__}: {exc}")
        return False

    # Always load the systems first. If maintenance was enabled before the last
    # restart, we unload them after loading so the owner can still run !صيانة
    # and disable maintenance without manually editing the database.
    for name in SYSTEM_COGS:
        try:
            await bot.load_extension(f"cogs.{name}")
            print(f"[{BOT_NAME}] Loaded cogs.{name}")
        except commands.ExtensionNotFound:
            print(f"[{BOT_NAME}] Missing cogs.{name}; skipped.")
        except commands.CommandRegistrationError as exc:
            print(f"[{BOT_NAME}] Command collision in cogs.{name}: {exc}")
        except Exception as exc:
            print(f"[{BOT_NAME}] Failed to load cogs.{name}: {type(exc).__name__}: {exc}")

    if is_maintenance():
        maintenance = bot.get_cog("Maintenance")
        if maintenance:
            unloaded = await maintenance._disable_all_systems()
            print(f"[{BOT_NAME}] Maintenance active; unloaded {len(unloaded)} systems.")

    return True


def run_web():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


async def main():
    init_db()
    if not await load_cogs():
        return
    threading.Thread(target=run_web, daemon=True, name="flame-dashboard").start()
    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
