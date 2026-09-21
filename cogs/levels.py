import random
import time
import discord
from discord import app_commands
from discord.ext import commands
from database import get_guild_data, connection, log_activity


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def apply_level_reward(self, guild, member, level, settings):
        rewards = settings.get('level_rewards') or {}
        role_id = rewards.get(str(level))
        if not role_id:
            return
        try:
            role = guild.get_role(int(role_id))
            if role and role not in member.roles and guild.me and guild.me.guild_permissions.manage_roles and role < guild.me.top_role:
                await member.add_roles(role, reason=f'Level {level} reward')
                log_activity(guild.id, 'level_role_reward', f'{member} -> {role.name} at level {level}', member.id)
        except (ValueError, discord.HTTPException, discord.Forbidden):
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        settings = get_guild_data(message.guild.id)
        if settings.get('levels_enabled', True) is False:
            return

        # Slower progression by default: longer cooldown, less XP per message,
        # and a larger XP curve. Existing dashboard settings are still respected.
        cooldown = max(5, int(settings.get('level_cooldown', 90) or 90))
        minimum = max(1, int(settings.get('xp_min', 5) or 5))
        maximum = max(minimum, int(settings.get('xp_max', 10) or 10))
        now = time.time()

        with connection() as conn:
            row = conn.execute(
                'SELECT xp, level, last_message FROM levels WHERE guild_id=? AND user_id=?',
                (message.guild.id, message.author.id),
            ).fetchone()
            if row and now - row['last_message'] < cooldown:
                return

            xp = (row['xp'] if row else 0) + random.randint(minimum, maximum)
            level = row['level'] if row else 0
            new_level = int((xp / 100) ** 0.5)
            conn.execute(
                'INSERT INTO levels(guild_id,user_id,xp,level,last_message) VALUES(?,?,?,?,?) '
                'ON CONFLICT(guild_id,user_id) DO UPDATE SET xp=excluded.xp,level=excluded.level,last_message=excluded.last_message',
                (message.guild.id, message.author.id, xp, new_level, now),
            )

        if new_level > level:
            await self.apply_level_reward(message.guild, message.author, new_level, settings)
            channel_id = settings.get('level_channel_id')
            channel = message.guild.get_channel(int(channel_id)) if channel_id else None
            if isinstance(channel, discord.TextChannel) and settings.get('level_announce', True):
                reward_text = ''
                role_id = (settings.get('level_rewards') or {}).get(str(new_level))
                if role_id:
                    role = message.guild.get_role(int(role_id))
                    if role:
                        reward_text = f'\n🏷️ الرتبة: {role.mention}'
                await channel.send(f'🎉 {message.author.mention} وصل للمستوى **{new_level}**!{reward_text}')
            log_activity(message.guild.id, 'level_up', f'{message.author} -> {new_level}', message.author.id)

    @commands.command(name='لفل')
    @commands.guild_only()
    async def level_prefix(self, ctx, member: discord.Member | None = None):
        if get_guild_data(ctx.guild.id).get('levels_enabled', True) is False:
            return await ctx.reply('❌ نظام المستويات متوقف حاليًا.')
        member = member or ctx.author
        with connection() as conn:
            row = conn.execute('SELECT xp, level FROM levels WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id)).fetchone()
        xp, level = (row['xp'], row['level']) if row else (0, 0)
        await ctx.reply(f'📊 مستوى {member.mention}: **{level}**\n⭐ XP: **{xp}**')

    @app_commands.command(name='level', description='Show a member level')
    @app_commands.guild_only()
    async def level_slash(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if get_guild_data(interaction.guild.id).get('levels_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام المستويات متوقف حاليًا.', ephemeral=True)
        member = member or interaction.user
        with connection() as conn:
            row = conn.execute('SELECT xp, level FROM levels WHERE guild_id=? AND user_id=?', (interaction.guild.id, member.id)).fetchone()
        xp, level = (row['xp'], row['level']) if row else (0, 0)
        await interaction.response.send_message(f'📊 مستوى {member.mention}: **{level}**\n⭐ XP: **{xp}**')

    @commands.command(name='توب')
    @commands.guild_only()
    async def top_prefix(self, ctx):
        if get_guild_data(ctx.guild.id).get('levels_enabled', True) is False:
            return await ctx.reply('❌ نظام المستويات متوقف حاليًا.')
        with connection() as conn:
            rows = conn.execute('SELECT user_id, xp, level FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT 10', (ctx.guild.id,)).fetchall()
        if not rows:
            return await ctx.reply('📊 لا توجد بيانات مستويات حتى الآن.')
        lines = [f'**{i}.** <@{r["user_id"]}> — مستوى {r["level"]} | {r["xp"]} XP' for i, r in enumerate(rows, 1)]
        await ctx.reply('🏆 **أفضل 10 أعضاء**\n' + '\n'.join(lines))

    @app_commands.command(name='leaderboard', description='Show the level leaderboard')
    @app_commands.guild_only()
    async def top_slash(self, interaction: discord.Interaction):
        if get_guild_data(interaction.guild.id).get('levels_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام المستويات متوقف حاليًا.', ephemeral=True)
        with connection() as conn:
            rows = conn.execute('SELECT user_id, xp, level FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT 10', (interaction.guild.id,)).fetchall()
        lines = [f'**{i}.** <@{r["user_id"]}> — مستوى {r["level"]} | {r["xp"]} XP' for i, r in enumerate(rows, 1)]
        await interaction.response.send_message('🏆 **أفضل 10 أعضاء**\n' + '\n'.join(lines) if lines else '📊 لا توجد بيانات.')


async def setup(bot):
    await bot.add_cog(Levels(bot))
