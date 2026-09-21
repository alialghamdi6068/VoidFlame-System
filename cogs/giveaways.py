import random
import re
import time
import discord
from discord import app_commands
from discord.ext import commands, tasks
from database import connection, get_guild_data, update_guild_data, log_activity

DURATION_RE = re.compile(r'^(\d+)([smhd])$', re.IGNORECASE)


def parse_duration(value: str) -> int:
    match = DURATION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError
    seconds = int(match.group(1)) * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[match.group(2).lower()]
    if seconds < 10 or seconds > 30 * 86400:
        raise ValueError
    return seconds


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.finish_loop.start()

    def cog_unload(self):
        self.finish_loop.cancel()

    async def create_giveaway(self, guild, channel, author, duration, winners, prize):
        settings = get_guild_data(guild.id)
        if settings.get('giveaways_enabled', True) is False:
            return False
        configured = guild.get_channel(int(settings['giveaways_channel_id'])) if settings.get('giveaways_channel_id') else None
        if isinstance(configured, discord.TextChannel):
            channel = configured
        ends_at = time.time() + duration
        embed = discord.Embed(title='🎉 قيفاواي', description=f'**الجائزة:** {prize}\n**الفائزون:** {winners}\n**ينتهي:** <t:{int(ends_at)}:R>', color=discord.Color.blurple())
        embed.set_footer(text=f'بدأه {author}')
        message = None
        try:
            message = await channel.send(embed=embed)
            await message.add_reaction('🎉')
        except (discord.Forbidden, discord.HTTPException):
            if message is not None:
                try:
                    await message.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass
            return None
        with connection() as conn:
            conn.execute('INSERT INTO giveaways(guild_id,channel_id,message_id,prize,winners,ends_at) VALUES(?,?,?,?,?,?)', (guild.id, channel.id, message.id, prize, winners, ends_at))
        log_activity(guild.id, 'giveaway_create', f'{prize} | {winners}', author.id)
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(guild, 'Giveaway Create', f'Prize: {prize}\nWinners: {winners}\nChannel: {channel.mention}', actor=author, color=discord.Color.blurple())
        return message

    async def finish(self, row, reroll=False):
        guild = self.bot.get_guild(row['guild_id'])
        if not guild:
            return []
        channel = guild.get_channel(row['channel_id'])
        if not isinstance(channel, discord.TextChannel):
            return []
        try:
            message = await channel.fetch_message(row['message_id'])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
        reaction = next((r for r in message.reactions if str(r.emoji) == '🎉'), None)
        if not reaction:
            return None
        users = [u async for u in reaction.users() if not u.bot]
        if not users:
            try:
                await channel.send(f'🎉 انتهى القيفاواي **{row["prize"]}** ولكن ما فيه مشاركين.')
            except discord.HTTPException:
                return None
            return []
        winners = random.sample(users, min(row['winners'], len(users)))
        mentions = ', '.join(user.mention for user in winners)
        try:
            await channel.send(f'🎉 مبروك {mentions}! فزتوا بـ **{row["prize"]}**!')
        except discord.HTTPException:
            return None
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(guild, 'Giveaway Finished', f'Prize: {row["prize"]}\nWinners: {mentions}', color=discord.Color.green())
        return winners

    @tasks.loop(seconds=5)
    async def finish_loop(self):
        with connection() as conn:
            rows = conn.execute('SELECT * FROM giveaways WHERE ended=0 AND ends_at<=?', (time.time(),)).fetchall()
        for row in rows:
            if get_guild_data(row['guild_id']).get('giveaways_enabled', True) is False:
                continue
            finished = await self.finish(row)
            if finished is not None:
                with connection() as conn:
                    conn.execute('UPDATE giveaways SET ended=1 WHERE id=? AND ended=0', (row['id'],))

    @finish_loop.before_loop
    async def before_finish_loop(self):
        await self.bot.wait_until_ready()

    @commands.command(name='قيفاواي')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def giveaway_prefix(self, ctx, duration: str, winners: int, *, prize: str):
        if get_guild_data(ctx.guild.id).get('giveaways_enabled', True) is False:
            return await ctx.reply('❌ نظام القيفاواي متوقف حاليًا.')
        try:
            seconds = parse_duration(duration)
        except ValueError:
            return await ctx.reply('❌ المدة غير صحيحة. استخدم `10m` أو `2h` أو `1d`.')
        if not 1 <= winners <= 50:
            return await ctx.reply('❌ عدد الفائزين يجب أن يكون بين 1 و50.')
        created = await self.create_giveaway(ctx.guild, ctx.channel, ctx.author, seconds, winners, prize[:200])
        if created is False:
            return await ctx.reply('❌ نظام القيفاواي متوقف حاليًا.')
        if created is None:
            return await ctx.reply('❌ تعذر إنشاء القيفاواي. تأكد من صلاحيات البوت في الروم المحدد.')
        await ctx.reply('✅ تم إنشاء القيفاواي.', delete_after=5)

    @app_commands.command(name='giveaway', description='Create a giveaway')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_slash(self, interaction, duration: str, winners: app_commands.Range[int, 1, 50], prize: str):
        if get_guild_data(interaction.guild.id).get('giveaways_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام القيفاواي متوقف حاليًا.', ephemeral=True)
        try:
            seconds = parse_duration(duration)
        except ValueError:
            return await interaction.response.send_message('❌ المدة غير صحيحة. استخدم 10m أو 2h أو 1d.', ephemeral=True)
        created = await self.create_giveaway(interaction.guild, interaction.channel, interaction.user, seconds, winners, prize[:200])
        if created is False:
            return await interaction.response.send_message('❌ نظام القيفاواي متوقف حاليًا.', ephemeral=True)
        if created is None:
            return await interaction.response.send_message('❌ تعذر إنشاء القيفاواي. تأكد من صلاحيات البوت في الروم المحدد.', ephemeral=True)
        await interaction.response.send_message('✅ تم إنشاء القيفاواي.', ephemeral=True)

    @commands.command(name='انهاء')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def end_prefix(self, ctx, message_id: int):
        if get_guild_data(ctx.guild.id).get('giveaways_enabled', True) is False:
            return await ctx.reply('❌ نظام القيفاواي متوقف حاليًا.')
        with connection() as conn:
            row = conn.execute('SELECT * FROM giveaways WHERE guild_id=? AND message_id=? AND ended=0', (ctx.guild.id, message_id)).fetchone()
        if not row:
            return await ctx.reply('❌ ما لقيت قيفاواي شغال بهذا الرقم.')
        finished = await self.finish(row)
        if finished is None:
            return await ctx.reply('❌ تعذر إنهاء القيفاواي الآن. لم يتم إغلاقه، حاول مرة أخرى.')
        with connection() as conn:
            conn.execute('UPDATE giveaways SET ended=1 WHERE id=? AND ended=0', (row['id'],))
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Giveaway End', f'Message: {message_id}', actor=ctx.author)
        await ctx.reply('✅ تم إنهاء القيفاواي.', delete_after=5)

    @commands.command(name='اعادة')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reroll_prefix(self, ctx, message_id: int):
        with connection() as conn:
            row = conn.execute('SELECT * FROM giveaways WHERE guild_id=? AND message_id=? AND ended=1', (ctx.guild.id, message_id)).fetchone()
        if not row:
            return await ctx.reply('❌ القيفاواي غير موجود أو لم ينتهِ بعد.')
        finished = await self.finish(row, reroll=True)
        if finished is None or not finished:
            return await ctx.reply('❌ تعذر إعادة السحب الآن.')
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Giveaway Reroll', f'Message: {message_id}', actor=ctx.author)
        await ctx.reply('🔄 تم اختيار فائز جديد.', delete_after=5)

    @commands.command(name='قيفاواي_روم')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        update_guild_data(ctx.guild.id, giveaways_channel_id=channel.id)
        await ctx.reply(f'✅ تم تحديد روم القيفاواي: {channel.mention}')


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
