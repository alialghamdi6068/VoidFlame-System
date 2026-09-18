import discord
from discord import app_commands
from discord.ext import commands
from database import get_guild_data, update_guild_data, log_activity


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_cache = {}

    async def refresh_invites(self, guild):
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {
                invite.code: {
                    'uses': invite.uses or 0,
                    'inviter_id': invite.inviter.id if invite.inviter else None,
                }
                for invite in invites
            }
        except (discord.Forbidden, discord.HTTPException):
            self.invite_cache.setdefault(guild.id, {})

    async def get_inviter(self, guild):
        old = self.invite_cache.get(guild.id, {})
        try:
            invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None

        inviter = None
        new_cache = {}
        for invite in invites:
            uses = invite.uses or 0
            old_data = old.get(invite.code, {})
            if uses > int(old_data.get('uses', 0)) and invite.inviter:
                inviter = invite.inviter
            new_cache[invite.code] = {
                'uses': uses,
                'inviter_id': invite.inviter.id if invite.inviter else None,
            }
        self.invite_cache[guild.id] = new_cache
        return inviter

    def replace_variables(self, message, member, inviter=None):
        guild = member.guild
        count = str(guild.member_count or 0)
        inviter_text = inviter.mention if inviter else 'غير معروف'
        return (
            str(message)
            .replace('{member}', member.mention)
            .replace('{username}', member.display_name)
            .replace('{server}', guild.name)
            .replace('{members}', count)
            .replace('{count}', count)
            .replace('{inviter}', inviter_text)
        )

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self.refresh_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        await self.refresh_invites(invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        await self.refresh_invites(invite.guild)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        settings = get_guild_data(member.guild.id)
        if settings.get('welcome_enabled', True) is False:
            return
        inviter = await self.get_inviter(member.guild)
        channel_id = settings.get('welcome_channel_id')
        if channel_id:
            channel = member.guild.get_channel(int(channel_id))
            if isinstance(channel, discord.TextChannel):
                message = settings.get('welcome_message', 'أهلاً وسهلاً {member} في **{server}**! 👋')
                message = self.replace_variables(message, member, inviter)
                try:
                    await channel.send(message)
                except discord.HTTPException:
                    pass
        log_activity(member.guild.id, 'member_join', str(member), member.id)

    @commands.command(name='ترحيب')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome_prefix(self, ctx, channel: discord.TextChannel, *, message: str = 'أهلاً وسهلاً {member} في **{server}**! 👋'):
        update_guild_data(ctx.guild.id, welcome_channel_id=channel.id, welcome_message=message[:2000])
        await ctx.reply(f'✅ تم ضبط الترحيب في {channel.mention}.')

    @app_commands.command(name='welcome', description='Set the welcome channel and message')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_slash(self, interaction, channel: discord.TextChannel, message: str = 'أهلاً وسهلاً {member} في **{server}**! 👋'):
        update_guild_data(interaction.guild.id, welcome_channel_id=channel.id, welcome_message=message[:2000])
        await interaction.response.send_message(f'✅ تم ضبط الترحيب في {channel.mention}.')


async def setup(bot):
    await bot.add_cog(Welcome(bot))
