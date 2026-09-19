import asyncio
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from services.settings_cache import settings_cache


class ProtectorGuard(commands.Cog):
    """Anti-spam, anti-raid and anti-nuke protection with audit-log actors."""

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
            for store in (self.messages, self.mentions, self.actions):
                for key in list(store):
                    q = store[key]
                    while q and now - q[0] > 180:
                        q.popleft()
                    if not q:
                        store.pop(key, None)
            for key in list(self.joins):
                q = self.joins[key]
                while q and now - q[0][0] > 180:
                    q.popleft()
                if not q:
                    self.joins.pop(key, None)
            for key, until in list(self.cooldowns.items()):
                if until <= now:
                    self.cooldowns.pop(key, None)

    def _ids(self, values):
        return {int(x) for x in values if str(x).isdigit()}

    def _trusted(self, member, settings):
        if not member:
            return False
        if member.id == member.guild.owner_id:
            return True
        if member.id in self._ids(settings.get("trusted_user_ids", [])):
            return True
        return bool(self._ids(settings.get("trusted_role_ids", [])) & {r.id for r in member.roles})

    def _ignored(self, message, settings):
        if not settings.get("protection_enabled", True):
            return True
        if message.author.bot or message.webhook_id:
            return True
        if message.channel.id in self._ids(settings.get("protection_ignore_channels", [])):
            return True
        return bool(self._ids(settings.get("protection_ignore_roles", [])) & {r.id for r in message.author.roles})

    async def _log(self, guild, title, description, actor=None, color=None):
        logs = self.bot.get_cog("Logs")
        if logs:
            await logs.send_log(guild, title, description, actor=actor, color=color)

    async def _punish(self, member, settings, reason):
        guild = member.guild
        me = guild.me
        if not me or member == guild.owner or member.top_role >= me.top_role:
            return "hierarchy"
        action = str(settings.get("protection_action", "timeout"))
        try:
            if action == "kick" and me.guild_permissions.kick_members:
                await member.kick(reason=reason)
                return "kick"
            if me.guild_permissions.moderate_members:
                minutes = max(1, min(40320, int(settings.get("protection_timeout_minutes", 10))))
                await member.timeout(timedelta(minutes=minutes), reason=reason)
                return f"timeout {minutes}m"
        except (discord.Forbidden, discord.HTTPException):
            return "failed"
        return "unavailable"

    async def _actor(self, guild, action, target_id=None, retries=2):
        # Audit-log entries can arrive a moment after the Discord event.
        for attempt in range(max(1, retries + 1)):
            try:
                newest = None
                async for entry in guild.audit_logs(limit=15, action=action):
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age > 30:
                        break
                    if target_id is not None and getattr(entry.target, "id", None) != target_id:
                        continue
                    if newest is None or entry.created_at > newest.created_at:
                        newest = entry
                if newest:
                    return newest.user
            except (discord.Forbidden, discord.HTTPException):
                return None
            if attempt < retries:
                await asyncio.sleep(0.8)
        return None

    async def _recent_webhook_actor(self, guild, channel_id):
        candidates = []
        for action in (
            discord.AuditLogAction.webhook_create,
            discord.AuditLogAction.webhook_update,
            discord.AuditLogAction.webhook_delete,
        ):
            try:
                async for entry in guild.audit_logs(limit=15, action=action):
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age > 30:
                        break
                    target = getattr(entry, "target", None)
                    target_channel = getattr(target, "channel_id", None)
                    if target_channel is None or target_channel == channel_id:
                        candidates.append(entry)
                        break
            except (discord.Forbidden, discord.HTTPException):
                continue
        if not candidates:
            return None
        return max(candidates, key=lambda entry: entry.created_at).user

    async def _lockdown(self, guild):
        changed = 0
        me = guild.me
        if not me or not me.guild_permissions.manage_channels:
            return changed
        for channel in guild.text_channels:
            try:
                ow = channel.overwrites_for(guild.default_role)
                if ow.send_messages is not False:
                    ow.send_messages = False
                    await channel.set_permissions(guild.default_role, overwrite=ow, reason="VoidFlame automatic lockdown")
                    changed += 1
            except (discord.Forbidden, discord.HTTPException):
                continue
        return changed

    async def _nuke_event(self, guild, action_key, audit_action, title, target_id=None):
        settings = settings_cache.get(guild.id)
        if not settings.get("protection_enabled", True):
            return
        if not settings.get("mass_change_protection", True):
            return
        if action_key == "channel_update" and not settings.get("permission_change_protection", True):
            return
        if action_key == "role_update" and not settings.get("permission_change_protection", True):
            return
        q = self.actions[(guild.id, action_key)]
        now = time.monotonic()
        q.append(now)
        window = max(5, int(settings.get("mass_change_window_seconds", 15)))
        while q and now - q[0] > window:
            q.popleft()
        threshold = max(3, int(settings.get("mass_change_threshold", 5)))
        if len(q) < threshold:
            return
        cooldown_key = ("nuke", guild.id, action_key)
        if now < self.cooldowns.get(cooldown_key, 0):
            return
        self.cooldowns[cooldown_key] = now + 45
        actor = await self._actor(guild, audit_action, target_id)
        if actor and self._trusted(actor, settings):
            await self._log(guild, title + " Burst", f"Detected {len(q)} events in {window}s\nActor: {actor.mention}\nActor is trusted; no punishment.", actor, discord.Color.orange())
            return
        action = "logged"
        if actor and settings.get("mass_change_action", "log") == "kick" and guild.me and guild.me.guild_permissions.kick_members and actor != guild.owner:
            if actor.top_role < guild.me.top_role:
                try:
                    await actor.kick(reason="VoidFlame anti-nuke: mass server changes")
                    action = "kick"
                except (discord.Forbidden, discord.HTTPException):
                    action = "kick_failed"
        if settings.get("mass_change_lockdown", False):
            locked = await self._lockdown(guild)
            action += f" + lockdown ({locked} channels)"
        await self._log(guild, title + " Burst", f"Detected {len(q)} {action_key.replace('_',' ')} events in {window}s\nActor: {actor.mention if actor else 'Unknown'}\nAction: {action}", actor, discord.Color.red())

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or not message.content or self._ignored(message, settings_cache.get(message.guild.id)):
            return
        settings = settings_cache.get(message.guild.id)
        now = time.monotonic()
        key = (message.guild.id, message.author.id)
        q = self.messages[key]
        q.append(now)
        window = max(2, int(settings.get("spam_window_seconds", 8)))
        limit = max(3, int(settings.get("spam_message_limit", 7)))
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit and now >= self.cooldowns.get(("spam", key), 0):
            self.cooldowns[("spam", key)] = now + 15
            if message.channel.permissions_for(message.guild.me).manage_messages:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
            action = await self._punish(message.author, settings, "Anti-spam protection")
            await self._log(message.guild, "Anti-Spam", f"Member: {message.author.mention}\nChannel: {message.channel.mention}\nMessages: {len(q)} in {window}s\nAction: {action}", message.author, discord.Color.orange())

        mentions = len(message.mentions) + len(message.role_mentions)
        if mentions >= max(3, int(settings.get("mention_limit", 5))):
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
                await self._log(message.guild, "Mention Spam", f"Member: {message.author.mention}\nChannel: {message.channel.mention}\nMentions: {mentions}\nAction: {action}", message.author, discord.Color.red())

    @commands.Cog.listener()
    async def on_member_join(self, member):
        settings = settings_cache.get(member.guild.id)
        if not settings.get("anti_raid_enabled", True):
            return
        now = time.monotonic()
        q = self.joins[member.guild.id]
        q.append((now, member.id))
        window = max(5, int(settings.get("raid_window_seconds", 20)))
        while q and now - q[0][0] > window:
            q.popleft()
        threshold = max(3, int(settings.get("raid_join_threshold", 8)))
        if len(q) < threshold:
            return
        if now < self.cooldowns.get(("raid", member.guild.id), 0):
            return
        self.cooldowns[("raid", member.guild.id)] = now + 60

        recent_ids = list(dict.fromkeys(member_id for joined_at, member_id in q if now - joined_at <= window))
        action = "detected"
        punished = 0
        if settings.get("raid_action", "timeout") == "timeout" and member.guild.me and member.guild.me.guild_permissions.moderate_members:
            minutes = max(1, min(40320, int(settings.get("raid_timeout_minutes", 10))))
            for member_id in recent_ids:
                target = member.guild.get_member(member_id)
                if not target or target.bot or target == member.guild.owner or target.top_role >= member.guild.me.top_role:
                    continue
                try:
                    await target.timeout(timedelta(minutes=minutes), reason="Anti-raid protection")
                    punished += 1
                except (discord.Forbidden, discord.HTTPException):
                    continue
            action = f"timeout {minutes}m ({punished}/{len(recent_ids)} members)"
        await self._log(member.guild, "Anti-Raid", f"Join burst: {len(recent_ids)} members in {window}s\nLatest: {member.mention}\nAction: {action}", member, discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self._nuke_event(channel.guild, "channel_create", discord.AuditLogAction.channel_create, "Channel Create", channel.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self._nuke_event(channel.guild, "channel_delete", discord.AuditLogAction.channel_delete, "Channel Delete", channel.id)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.overwrites != after.overwrites or before.name != after.name or before.category_id != after.category_id:
            await self._nuke_event(after.guild, "channel_update", discord.AuditLogAction.channel_update, "Channel Permission/Update", after.id)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self._nuke_event(role.guild, "role_create", discord.AuditLogAction.role_create, "Role Create", role.id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self._nuke_event(role.guild, "role_delete", discord.AuditLogAction.role_delete, "Role Delete", role.id)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before.permissions != after.permissions or before.name != after.name or before.position != after.position:
            await self._nuke_event(after.guild, "role_update", discord.AuditLogAction.role_update, "Role Permission/Update", after.id)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        settings = settings_cache.get(channel.guild.id)
        if not settings.get("webhook_protection", True):
            return
        actor = await self._recent_webhook_actor(channel.guild, channel.id)
        if actor and not self._trusted(actor, settings):
            action = "logged"
            if settings.get("mass_change_action", "log") == "kick" and channel.guild.me and channel.guild.me.guild_permissions.kick_members and actor != channel.guild.owner and actor.top_role < channel.guild.me.top_role:
                try:
                    await actor.kick(reason="VoidFlame webhook abuse protection")
                    action = "kick"
                except (discord.Forbidden, discord.HTTPException):
                    action = "kick_failed"
            await self._log(channel.guild, "Webhook Security", f"Channel: {channel.mention}\nActor: {actor.mention}\nAction: {action}", actor, discord.Color.red())

async def setup(bot):
    await bot.add_cog(ProtectorGuard(bot))
