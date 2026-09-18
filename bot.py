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
app = create_app(bot)

MULTIWORD_ALIASES = {
    '!اوامر الادارة': '!اوامر_الادارة', '!فك تايم': '!فك_تايم', '!فك ميوت': '!فك_تايم',
    '!فك حظر': '!فك_حظر', '!ريست لفل': '!ريست_لفل', '!مسح تحذيرات': '!مسح_تحذيرات',
    '!مسح رسائل': '!مسح', '!قفل روم': '!قفل_روم', '!فتح روم': '!فتح_روم',
    '!انهاء قيفاواي': '!انهاء', '!اعادة قيفاواي': '!اعادة', '!قبول اقتراح': '!قبول_اقتراح',
    '!رفض اقتراح': '!رفض_اقتراح', '!حذف رد': '!حذف_رد', '!رتبة تلقائية': '!رتبة_تلقائية',
    '!قيفاواي روم': '!قيفاواي_روم', '!قبول تقديم': '!قبول_تقديم', '!رفض تقديم': '!رفض_تقديم',
    '!اعطاء رتبة': '!اعطاء_رتبة', '!سحب رتبة': '!سحب_رتبة', '!اعلى دعوات': '!اعلى_دعوات',
    '!رتب السيرفر': '!رتب_السيرفر', '!اعضاء اونلاين': '!اعضاء_اونلاين',
    '!احصائيات السيرفر': '!احصائيات_السيرفر', '!سجل العضو': '!سجل_العضو', '!عمر الحساب': '!عمر_الحساب',
    '!عمر السيرفر': '!عمر_السيرفر', '!اختصار الرابط': '!اختصار_الرابط', '!وقت عالمي': '!وقت_عالمي',
    '!مساعدة الأمر': '!مساعدة_الأمر', '!حظر': '!باند', '!ميوت': '!تايم', '!بنق': '!بينج',
}


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    original_content = message.content.strip()
    content = message.content

    for public_name, internal_name in sorted(MULTIWORD_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if content == public_name or content.startswith(public_name + ' '):
            message.content = internal_name + content[len(public_name):]
            break

    if is_maintenance() and original_content != '!صيانة':
        return

    await bot.process_commands(message)


@bot.event
async def on_ready():
    settings_cache.clear()
    print(f'[{BOT_NAME}] Logged in as {bot.user} | Guilds: {len(bot.guilds)}')
    for guild in bot.guilds:
        print(f'[{BOT_NAME}] Guild: {guild.name} ({guild.id})')
    try:
        synced = await bot.tree.sync()
        print(f'[{BOT_NAME}] Synced {len(synced)} slash commands.')
    except Exception as exc:
        print(f'[{BOT_NAME}] Slash sync failed: {type(exc).__name__}: {exc}')


@bot.tree.interaction_check
async def maintenance_check(interaction: discord.Interaction):
    if is_maintenance() and interaction.command and interaction.command.name != 'maintenance':
        await interaction.response.send_message('🔧 البوت حاليًا في وضع الصيانة. الأوامر متوقفة مؤقتًا.', ephemeral=True)
        return False
    return True


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        return await ctx.reply('❌ ما عندك الصلاحية المطلوبة.')
    if isinstance(error, commands.BotMissingPermissions):
        return await ctx.reply('❌ البوت ناقصه صلاحية لتنفيذ الأمر.')
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.reply(f'❌ ناقصك المتغير: `{error.param.name}`.')
    if isinstance(error, commands.BadArgument):
        return await ctx.reply('❌ تأكد من المنشن أو الرقم أو البيانات المدخلة.')

    original = getattr(error, 'original', error)
    print(f'[{BOT_NAME}] Command error: {type(original).__name__}: {original}')
    try:
        await ctx.reply('❌ حدث خطأ أثناء تنفيذ الأمر. تم تسجيل الخطأ في السجل.', mention_author=False)
    except discord.HTTPException:
        pass


async def load_cogs():
    cog_names = [
        'moderation', 'tickets', 'applications', 'levels', 'welcome', 'logs',
        'giveaways', 'suggestions', 'afk', 'autoreply', 'autorole', 'announcements',
        'reminders', 'scheduler', 'utility', 'owner', 'messaging', 'dashboard_commands',
        'extra_commands', 'new_commands', 'warn_slash', 'multiword',
        'ai_guard', 'event_logger', 'maintenance'
    ]
    for name in cog_names:
        try:
            if name == 'extra_commands':
                bot.tree.remove_command('avatar')
            await bot.load_extension(f'cogs.{name}')
            print(f'[{BOT_NAME}] Loaded cogs.{name}')
        except commands.ExtensionNotFound:
            print(f'[{BOT_NAME}] Missing cogs.{name}; skipped.')
        except Exception as exc:
            print(f'[{BOT_NAME}] Failed to load cogs.{name}: {type(exc).__name__}: {exc}')


def run_web():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


async def main():
    init_db()
    await load_cogs()
    threading.Thread(target=run_web, daemon=True, name='flame-dashboard').start()
    await bot.start(DISCORD_TOKEN)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
