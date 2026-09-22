import discord
import time
from collections import defaultdict, deque
from discord import app_commands
from discord.ext import commands
from database import get_guild_data, update_guild_data, log_activity


class Logs(commands.Cog):
    """Shared logging destination and helper. Event logging lives in protector_guard."""

    def __init__(self, bot):
        self.bot = bot
        self._rate = defaultdict(deque)

    async def send_log(self, guild, title, description, user_id=None, actor=None, color=None):
        settings = get_guild_data(guild.id)
        if settings.get("logs_enabled", True) is False:
            return
        now = time.monotonic()
        q = self._rate[guild.id]
        while q and now - q[0] > 5:
            q.popleft()
        if len(q) >= int(settings.get("log_rate_limit", 12)):
            log_activity(guild.id, "log_rate_limited", title, user_id)
            return
        q.append(now)
        channel_id = settings.get('log_channel_id')
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            embed = discord.Embed(
                title=title,
                description=str(description)[:4000],
                color=color or discord.Color.blurple(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text='VoidFlame Protector • Security Log')
            if actor:
                try:
                    embed.set_author(name=str(actor), icon_url=actor.display_avatar.url)
                except Exception:
                    embed.set_author(name=str(actor))
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass
        log_activity(guild.id, title, str(description)[:4000], user_id)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.send_log(
            member.guild,
            "Member Joined",
            f"Member: {member.mention} (`{member.id}`)\\nAccount created: <t:{int(member.created_at.timestamp())}:R>",
            actor=member,
            color=discord.Color.green(),
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.send_log(
            member.guild,
            "Member Left",
            f"Member: {member} (`{member.id}`)",
            actor=member,
            color=discord.Color.orange(),
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        await self.send_log(
            message.guild,
            "Message Deleted",
            f"Author: {message.author.mention} (`{message.author.id}`)\\nChannel: {message.channel.mention} (`{message.channel.id}`)",
            actor=message.author,
            color=discord.Color.red(),
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        await self.send_log(
            before.guild,
            "Message Edited",
            f"Author: {before.author.mention} (`{before.author.id}`)\\nChannel: {before.channel.mention} (`{before.channel.id}`)",
            actor=before.author,
            color=discord.Color.orange(),
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self.send_log(
            channel.guild,
            "Channel Created",
            f"Channel: {channel.mention} (`{channel.id}`)",
            color=discord.Color.green(),
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self.send_log(
            channel.guild,
            "Channel Deleted",
            f"Channel: #{channel.name} (`{channel.id}`)",
            color=discord.Color.red(),
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self.send_log(
            role.guild,
            "Role Created",
            f"Role: {role.mention} (`{role.id}`)",
            color=discord.Color.green(),
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self.send_log(
            role.guild,
            "Role Deleted",
            f"Role: {role.name} (`{role.id}`)",
            color=discord.Color.red(),
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.send_log(
            guild,
            "Member Banned",
            f"Member: {user} (`{user.id}`)",
            color=discord.Color.red(),
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.send_log(
            guild,
            "Member Unbanned",
            f"Member: {user} (`{user.id}`)",
            color=discord.Color.green(),
        )

    @commands.command(name='لوق')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def set_logs(self, ctx, channel: discord.TextChannel):
        update_guild_data(ctx.guild.id, log_channel_id=channel.id)
        log_activity(ctx.guild.id, 'log_channel_update', f'channel={channel.id}', ctx.author.id)
        await ctx.reply(f'✅ تم تحديد روم اللوق: {channel.mention}')

    @app_commands.command(name='logs', description='Set the security log channel')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_logs_slash(self, interaction, channel: discord.TextChannel):
        update_guild_data(interaction.guild.id, log_channel_id=channel.id)
        log_activity(interaction.guild.id, 'log_channel_update', f'channel={channel.id}', interaction.user.id)
        await interaction.response.send_message(f'✅ تم تحديد روم اللوق: {channel.mention}', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Logs(bot))
