import asyncio
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from services.settings_cache import settings_cache


class ProtectorGuard(commands.Cog):
    """Local anti-spam, anti-mention and anti-raid protection."""

    def __init__(self, bot):
        self.bot = bot
        self.messages = defaultdict(deque)
        self.mentions = defaultdict(deque)
        self.joins = defaultdict(deque)
        self.actions = defaultdict(deque)
        self.cooldowns = {}
        self._cleanup_task = asyncio.create_task(self._cleanup())

    def cog_unload(self):
        self._cleanup_task.cancel()

    async def _cleanup(self):
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            for store in (self.messages, self.mentions, self.joins, self.actions):
                for key in list(store):
                    q = store[key]
                    while q and now - q[0] > 120:
                        q.popleft()
                    if not q:
                        store.pop(key, None)
            for key, until in list(self.cooldowns.items()):
                if until <= now:
                    self.cooldowns.pop(key, None)

    def _numbers(self, value):
        return {int(x) for x in value if str(x).isdigit()}

    def _ignored(self, message, settings):
        if not settings.get("protection_enabled", True):
            return True
        if message.author.bot or message.webhook_id:
            return True
        if message.author.guild_permissions.administrator:
            return True
        if message.channel.id in self._numbers(settings.get("protection_ignore_channels", [])):
            return True
        return bool(self._numbers(settings.get("protection_ignore_roles", [])) & {r.id for r in message.author.roles})

    async def _log(self, guild, title, description, actor=None, color=None):
        logs = self.bot.get_cog("Logs")
        if logs:
            await logs.send_log(guild, title, description, actor=actor, color=color)

    async def _punish(self, member, settings, reason, *, allow_kick=True):
        guild = member.guild
        me = guild.me
        if not me or member == guild.owner or member.top_role >= me.top_role:
            return "hierarchy"
        action = str(settings.get("protection_action", "timeout"))
        if action == "kick" and allow_kick and me.guild_permissions.kick_members:
            await member.kick(reason=reason)
            return "kick"
        if me.guild_permissions.moderate_members:
            minutes = max(1, min(40320, int(settings.get("protection_timeout_minutes", 10))))
            await member.timeout(timedelta(minutes=minutes), reason=reason)
            return f"timeout {minutes}m"
        return "unavailable"

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or not message.content or self._ignored(message, settings_cache.get(message.guild.id)):
            return
        settings = settings_cache.get(message.guild.id)
        now = time.monotonic()
        key = (message.guild.id, message.author.id)

        spam_window = max(2, int(settings.get("spam_window_seconds", 8)))
        spam_limit = max(3, int(settings.get("spam_message_limit", 7)))
        q = self.messages[key]
        q.append(now)
        while q and now - q[0] > spam_window:
            q.popleft()

        if len(q) >= spam_limit:
            if now >= self.cooldowns.get(("spam", key), 0):
                self.cooldowns[("spam", key)] = now + 15
                if message.channel.permissions_for(message.guild.me).manage_messages:
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass
                action = await self._punish(message.author, settings, "Anti-spam protection")
                await self._log(message.guild, "Anti-Spam", f"Member: {message.author.mention}\nChannel: {message.channel.mention}\nMessages: {len(q)} in {spam_window}s\nAction: {action}", message.author, discord.Color.orange())
            return

        mention_count = len(message.mentions) + len(message.role_mentions)
        mention_limit = max(3, int(settings.get("mention_limit", 5)))
        if mention_count >= mention_limit:
            mq = self.mentions[key]
            mq.append(now)
            while mq and now - mq[0] > 20:
                mq.popleft()
            if now >= self.cooldowns.get(("mention", key), 0):
                self.cooldowns[("mention", key)] = now + 20
                if message.channel.permissions_for(message.guild.me).manage_messages:
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass
                action = await self._punish(message.author, settings, "Anti-mention-spam protection")
                await self._log(message.guild, "Mention Spam", f"Member: {message.author.mention}\nChannel: {message.channel.mention}\nMentions: {mention_count}\nAction: {action}", message.author, discord.Color.red())

    @commands.Cog.listener()
    async def on_member_join(self, member):
        settings = settings_cache.get(member.guild.id)
        if not settings.get("anti_raid_enabled", True):
            return
        now = time.monotonic()
        q = self.joins[member.guild.id]
        q.append(now)
        window = max(5, int(settings.get("raid_window_seconds", 20)))
        while q and now - q[0] > window:
            q.popleft()
        threshold = max(3, int(settings.get("raid_join_threshold", 8)))
        if len(q) < threshold:
            return
        key = ("raid", member.guild.id)
        if now < self.cooldowns.get(key, 0):
            return
        self.cooldowns[key] = now + 60
        action = "detected"
        if settings.get("raid_action", "timeout") == "timeout":
            if member.guild.me and member.guild.me.guild_permissions.moderate_members and member.top_role < member.guild.me.top_role:
                minutes = max(1, min(40320, int(settings.get("raid_timeout_minutes", 10))))
                try:
                    await member.timeout(timedelta(minutes=minutes), reason="Anti-raid protection")
                    action = f"timeout {minutes}m"
                except discord.HTTPException:
                    action = "timeout_failed"
        await self._log(member.guild, "Anti-Raid", f"Join burst detected: {len(q)} members in {window}s\nLatest member: {member.mention}\nAction: {action}", member, discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self._audit_burst(channel.guild, "channel_create", "Channel Create", discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self._audit_burst(channel.guild, "channel_delete", "Channel Delete", discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self._audit_burst(role.guild, "role_create", "Role Create", discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self._audit_burst(role.guild, "role_delete", "Role Delete", discord.Color.red())

    async def _audit_burst(self, guild, action_name, title, color):
        settings = settings_cache.get(guild.id)
        if not settings.get("mass_change_protection", True):
            return
        now = time.monotonic()
        q = self.actions[(guild.id, action_name)]
        q.append(now)
        window = max(5, int(settings.get("mass_change_window_seconds", 15)))
        while q and now - q[0] > window:
            q.popleft()
        threshold = max(3, int(settings.get("mass_change_threshold", 5)))
        if len(q) < threshold:
            return
        key = ("mass", guild.id, action_name)
        if now < self.cooldowns.get(key, 0):
            return
        self.cooldowns[key] = now + 45
        actor = None
        try:
            audit_action = {
                "channel_create": discord.AuditLogAction.channel_create,
                "channel_delete": discord.AuditLogAction.channel_delete,
                "role_create": discord.AuditLogAction.role_create,
                "role_delete": discord.AuditLogAction.role_delete,
            }[action_name]
            async for entry in guild.audit_logs(limit=5, action=audit_action):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() < 15:
                    actor = entry.user
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass
        action = "logged"
        if actor and actor != guild.owner and settings.get("mass_change_action", "log") == "kick":
            me = guild.me
            if me and me.guild_permissions.kick_members and actor.top_role < me.top_role:
                try:
                    await actor.kick(reason="Mass server change protection")
                    action = "kick"
                except discord.HTTPException:
                    action = "kick_failed"
        await self._log(guild, title + " Burst", f"Detected {len(q)} {action_name.replace('_', ' ')} events in {window}s\nActor: {actor.mention if actor else 'Unknown'}\nAction: {action}", actor, color)


async def setup(bot):
    await bot.add_cog(ProtectorGuard(bot))
