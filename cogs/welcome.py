import discord
from discord import app_commands
from discord.ext import commands
from database import get_guild_data, update_guild_data, log_activity

DEFAULT_TITLE = "Welcome {user} to {server}!"
DEFAULT_DESCRIPTION = "You are member {count} 🎉\n\n📌 Please read the rules\n💬 Chat & have fun\n🚀 Enjoy!"

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_cache = {}

    async def refresh_invites(self, guild):
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {
                invite.code: {"uses": invite.uses or 0, "inviter_id": invite.inviter.id if invite.inviter else None}
                for invite in invites
            }
        except (discord.Forbidden, discord.HTTPException):
            self.invite_cache.setdefault(guild.id, {})

    async def get_inviter(self, guild):
        old = self.invite_cache.get(guild.id, {})
        try: invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException): return None
        inviter = None; new_cache = {}
        for invite in invites:
            uses = invite.uses or 0; old_data = old.get(invite.code, {})
            if uses > int(old_data.get("uses", 0)) and invite.inviter: inviter = invite.inviter
            new_cache[invite.code] = {"uses": uses, "inviter_id": invite.inviter.id if invite.inviter else None}
        self.invite_cache[guild.id] = new_cache
        return inviter

    def replace_variables(self, text, member, inviter=None):
        guild = member.guild; count = str(guild.member_count or 0)
        return (str(text).replace("{member}", member.mention).replace("{user}", member.mention)
                .replace("{username}", member.display_name).replace("{server}", guild.name)
                .replace("{members}", count).replace("{count}", count)
                .replace("{inviter}", inviter.mention if inviter else "Unknown"))

    def build_embed(self, member, settings):
        title = self.replace_variables(settings.get("welcome_title", DEFAULT_TITLE), member)
        description = self.replace_variables(settings.get("welcome_message", DEFAULT_DESCRIPTION), member)
        try: color = int(str(settings.get("welcome_color", "8B5CF6")).replace("#", ""), 16)
        except ValueError: color = 0x8B5CF6
        embed = discord.Embed(title=title[:256], description=description[:4096], color=color)
        embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else discord.Embed.Empty)
        if settings.get("welcome_member_avatar", True):
            embed.set_thumbnail(url=member.display_avatar.url)
        if settings.get("welcome_server_icon", False) and member.guild.icon:
            embed.set_image(url=member.guild.icon.url)
        embed.set_footer(text=f"Member #{member.guild.member_count or 0}")
        return embed

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds: await self.refresh_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite): await self.refresh_invites(invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite): await self.refresh_invites(invite.guild)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        settings = get_guild_data(member.guild.id)
        if settings.get("welcome_enabled", True) is False: return
        channel_id = settings.get("welcome_channel_id")
        if not channel_id: return
        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel): return
        inviter = await self.get_inviter(member.guild)
        embed = self.build_embed(member, settings)
        try:
            await channel.send(embed=embed)
            log_activity(member.guild.id, "member_join", str(member), member.id)
        except discord.HTTPException: pass

    @commands.command(name="ترحيب")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome_prefix(self, ctx, channel: discord.TextChannel, *, message: str = DEFAULT_DESCRIPTION):
        update_guild_data(ctx.guild.id, welcome_enabled=True, welcome_channel_id=channel.id, welcome_message=message[:4096])
        await ctx.reply(f"✅ تم ضبط الترحيب في {channel.mention}.\n🖼️ صورة العضو مفعلة داخل الـEmbed.")

    @app_commands.command(name="welcome", description="Set the welcome channel and message")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_slash(self, interaction, channel: discord.TextChannel, message: str = DEFAULT_DESCRIPTION):
        update_guild_data(interaction.guild.id, welcome_enabled=True, welcome_channel_id=channel.id, welcome_message=message[:4096])
        await interaction.response.send_message(f"✅ Welcome configured in {channel.mention}. Member avatar is shown in the embed.", ephemeral=True)

    @app_commands.command(name="welcome-config", description="Configure the welcome embed")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(channel="Welcome channel", title="Embed title", message="Embed description", color="Hex color such as 8B5CF6", member_avatar="Show the new member avatar")
    async def welcome_config(self, interaction, channel: discord.TextChannel | None = None, title: str | None = None, message: str | None = None, color: str | None = None, member_avatar: bool | None = None):
        changes = {"welcome_enabled": True}
        if channel: changes["welcome_channel_id"] = channel.id
        if title is not None: changes["welcome_title"] = title[:256]
        if message is not None: changes["welcome_message"] = message[:4096]
        if color is not None:
            value = color.replace("#", "").strip()
            if len(value) not in (6,): return await interaction.response.send_message("❌ Color must be a 6-digit hex value.", ephemeral=True)
            try: int(value, 16)
            except ValueError: return await interaction.response.send_message("❌ Invalid hex color.", ephemeral=True)
            changes["welcome_color"] = value
        if member_avatar is not None: changes["welcome_member_avatar"] = member_avatar
        update_guild_data(interaction.guild.id, **changes)
        await interaction.response.send_message("✅ Welcome embed settings saved. The member avatar is rendered inside the embed when enabled.", ephemeral=True)

async def setup(bot): await bot.add_cog(Welcome(bot))
