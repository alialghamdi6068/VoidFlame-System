import discord
from discord.ext import commands
from database import get_guild_data

class EventLogger(commands.Cog):
    def __init__(self, bot): self.bot = bot

    async def emit(self, guild, title, description, actor=None, color=None):
        settings = get_guild_data(guild.id)
        if settings.get("logs_enabled", True) is False: return
        disabled = set(settings.get("disabled_log_events", []))
        key = title.lower().replace(" ","_")
        if key in disabled: return
        logs = self.bot.get_cog("Logs")
        if logs: await logs.send_log(guild, title, description, actor=actor, color=color)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.emit(member.guild, "Member Join", f"{member.mention} joined. ID: {member.id}", member, discord.Color.green())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.emit(member.guild, "Member Leave", f"{member} left. ID: {member.id}", member, discord.Color.red())

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        changes=[]
        if before.nick != after.nick: changes.append(f"Nickname: {before.nick} -> {after.nick}")
        if before.roles != after.roles:
            old={r.id:r.name for r in before.roles}; new={r.id:r.name for r in after.roles}
            a=[new[x] for x in new.keys()-old.keys()]; r=[old[x] for x in old.keys()-new.keys()]
            if a: changes.append("Added roles: "+", ".join(a[:10]))
            if r: changes.append("Removed roles: "+", ".join(r[:10]))
        if changes: await self.emit(after.guild, "Member Update", "
".join(changes), after)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel): await self.emit(channel.guild, "Channel Create", f"{channel.name} ({channel.id})")
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel): await self.emit(channel.guild, "Channel Delete", f"{channel.name} ({channel.id})", color=discord.Color.red())
    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.name != after.name: await self.emit(after.guild, "Channel Update", f"{before.name} -> {after.name}")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role): await self.emit(role.guild, "Role Create", f"{role.name} ({role.id})")
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role): await self.emit(role.guild, "Role Delete", f"{role.name} ({role.id})", color=discord.Color.red())
    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before.name != after.name or before.permissions != after.permissions: await self.emit(after.guild, "Role Update", f"{before.name} -> {after.name}")

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild and not message.author.bot: await self.emit(message.guild, "Message Delete", f"Author: {message.author.mention}\\nChannel: {message.channel.mention}\\nContent: {message.content[:1200]}", message.author, discord.Color.orange())

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.guild and before.content != after.content and not after.author.bot: await self.emit(after.guild, "Message Edit", f"Author: {after.author.mention}\\nChannel: {after.channel.mention}\\nBefore: {before.content[:700]}\\nAfter: {after.content[:700]}", after.author)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if messages and getattr(messages[0],"guild",None): await self.emit(messages[0].guild, "Bulk Message Delete", f"Deleted messages: {len(messages)}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel==after.channel and before.mute==after.mute and before.deaf==after.deaf: return
        await self.emit(member.guild, "Voice Update", f"Member: {member.mention}\\nBefore: {before.channel}\\nAfter: {after.channel}\\nMute: {after.mute}\\nDeaf: {after.deaf}", member)

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        changes=[]
        if before.name != after.name: changes.append(f"Name: {before.name} -> {after.name}")
        if before.icon != after.icon: changes.append("Server icon changed")
        if changes: await self.emit(after, "Server Update", "
".join(changes))

async def setup(bot): await bot.add_cog(EventLogger(bot))
