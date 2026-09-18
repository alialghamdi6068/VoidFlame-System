import discord
from discord.ext import commands
from database import get_guild_data


class EventLogger(commands.Cog):
    """Unified audit/event logger. All output goes through the single Logs cog."""
    def __init__(self, bot):
        self.bot = bot

    async def actor(self, guild, action, target_id=None):
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > 20:
                    break
                if target_id is None or getattr(entry.target, "id", None) == target_id:
                    return entry.user
        except (discord.Forbidden, discord.HTTPException):
            pass
        return None

    async def emit(self, guild, title, description, actor=None, color=None):
        settings = get_guild_data(guild.id)
        if settings.get("logs_enabled", True) is False:
            return
        disabled = {str(x).lower() for x in settings.get("disabled_log_events", [])}
        if title.lower().replace(" ", "_") in disabled:
            return
        logs = self.bot.get_cog("Logs")
        if logs:
            await logs.send_log(guild, title, description, actor=actor, color=color)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.emit(member.guild, "Member Join", f"{member.mention} joined. ID: {member.id}", member, discord.Color.green())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        actor = await self.actor(member.guild, discord.AuditLogAction.kick, member.id)
        if not actor:
            actor = await self.actor(member.guild, discord.AuditLogAction.ban, member.id)
        await self.emit(member.guild, "Member Leave", f"{member} left. ID: {member.id}\nActor: {actor.mention if actor else 'Unknown'}", actor or member, discord.Color.red())

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        changes = []
        if before.nick != after.nick:
            changes.append(f"Nickname: {before.nick or 'None'} -> {after.nick or 'None'}")
        if before.roles != after.roles:
            old = {r.id: r.name for r in before.roles}
            new = {r.id: r.name for r in after.roles}
            added = [new[x] for x in new.keys() - old.keys()]
            removed = [old[x] for x in old.keys() - new.keys()]
            if added:
                changes.append("Added roles: " + ", ".join(added[:10]))
            if removed:
                changes.append("Removed roles: " + ", ".join(removed[:10]))
        if not changes:
            return
        actor = await self.actor(after.guild, discord.AuditLogAction.member_role_update, after.id) if before.roles != after.roles else await self.actor(after.guild, discord.AuditLogAction.member_update, after.id)
        await self.emit(after.guild, "Member Update", "\n".join(changes) + f"\nActor: {actor.mention if actor else 'Unknown'}", actor or after)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        actor = await self.actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        kind = "Category" if isinstance(channel, discord.CategoryChannel) else "Channel"
        await self.emit(channel.guild, f"{kind} Create", f"{channel.name} ({channel.id})\nActor: {actor.mention if actor else 'Unknown'}", actor)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        actor = await self.actor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        kind = "Category" if isinstance(channel, discord.CategoryChannel) else "Channel"
        await self.emit(channel.guild, f"{kind} Delete", f"{channel.name} ({channel.id})\nActor: {actor.mention if actor else 'Unknown'}", actor, discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} -> {after.name}")
        if before.category_id != after.category_id:
            changes.append(f"Category: {before.category_id} -> {after.category_id}")
        if before.overwrites != after.overwrites:
            changes.append("Permission overwrites changed")
        if not changes:
            return
        actor = await self.actor(after.guild, discord.AuditLogAction.channel_update, after.id)
        kind = "Category" if isinstance(after, discord.CategoryChannel) else "Channel"
        await self.emit(after.guild, f"{kind} Update", "\n".join(changes) + f"\nActor: {actor.mention if actor else 'Unknown'}", actor)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        actor = await self.actor(role.guild, discord.AuditLogAction.role_create, role.id)
        await self.emit(role.guild, "Role Create", f"{role.name} ({role.id})\nActor: {actor.mention if actor else 'Unknown'}", actor)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        actor = await self.actor(role.guild, discord.AuditLogAction.role_delete, role.id)
        await self.emit(role.guild, "Role Delete", f"{role.name} ({role.id})\nActor: {actor.mention if actor else 'Unknown'}", actor, discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} -> {after.name}")
        if before.permissions != after.permissions:
            changes.append("Permissions changed")
        if before.position != after.position:
            changes.append(f"Position: {before.position} -> {after.position}")
        if not changes:
            return
        actor = await self.actor(after.guild, discord.AuditLogAction.role_update, after.id)
        await self.emit(after.guild, "Role Update", "\n".join(changes) + f"\nActor: {actor.mention if actor else 'Unknown'}", actor)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild and not message.author.bot:
            await self.emit(message.guild, "Message Delete", f"Author: {message.author.mention}\nChannel: {message.channel.mention}\nContent: {message.content[:1500]}", message.author, discord.Color.orange())

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.guild and before.content != after.content and not after.author.bot:
            await self.emit(after.guild, "Message Edit", f"Author: {after.author.mention}\nChannel: {after.channel.mention}\nBefore: {before.content[:700]}\nAfter: {after.content[:700]}", after.author)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if messages and getattr(messages[0], "guild", None):
            await self.emit(messages[0].guild, "Bulk Message Delete", f"Deleted messages: {len(messages)}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel and before.mute == after.mute and before.deaf == after.deaf:
            return
        await self.emit(member.guild, "Voice Update", f"Member: {member.mention}\nBefore: {before.channel}\nAfter: {after.channel}\nMute: {after.mute}\nDeaf: {after.deaf}", member)

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        settings = get_guild_data(after.id)
        if settings.get("guild_update_protection", True) is False:
            return
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} -> {after.name}")
        if before.icon != after.icon:
            changes.append("Server icon changed")
        if before.banner != after.banner:
            changes.append("Server banner changed")
        if before.verification_level != after.verification_level:
            changes.append(f"Verification level: {before.verification_level} -> {after.verification_level}")
        if before.default_notifications != after.default_notifications:
            changes.append("Default notifications changed")
        if not changes:
            return
        actor = await self.actor(after, discord.AuditLogAction.guild_update, after.id)
        await self.emit(after, "Server Update", "\n".join(changes) + f"\nActor: {actor.mention if actor else 'Unknown'}", actor, discord.Color.orange())

async def setup(bot):
    await bot.add_cog(EventLogger(bot))
