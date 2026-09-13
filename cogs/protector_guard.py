import re
import time
import asyncio
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from database import get_guild_data, update_guild_data, log_activity


INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+", re.I)
SPAM_LIMIT = 7
SPAM_WINDOW = 8
RAID_LIMIT = 8
RAID_WINDOW = 15
MENTION_LIMIT = 5
WEBHOOK_LIMIT = 3


class ProtectorGuard(commands.Cog):
    """Automatic security and comprehensive Discord event logging."""

    def __init__(self, bot):
        self.bot = bot
        self.spam = defaultdict(deque)
        self.joins = defaultdict(deque)
        self.nuke_actions = defaultdict(deque)
        self._channel_setup_lock = asyncio.Lock()

    def logger(self):
        return self.bot.get_cog('Logs')

    async def log(self, guild, title, description, actor=None, color=None):
        cog = self.logger()
        if cog:
            await cog.send_log(guild, title, description, actor=actor, color=color)
        else:
            log_activity(guild.id, title, description, getattr(actor, 'id', None))

    async def audit(self, guild, action, target_id=None, attempts=3):
        for attempt in range(attempts):
            try:
                async for entry in guild.audit_logs(limit=12, action=action):
                    if target_id is not None and getattr(entry.target, 'id', None) != target_id:
                        continue
                    if abs((discord.utils.utcnow() - entry.created_at).total_seconds()) <= 20:
                        return entry.user, entry.reason
            except (discord.Forbidden, discord.HTTPException):
                return None, None
            if attempt + 1 < attempts:
                await asyncio.sleep(0.5)
        return None, None

    async def ensure_security_channels(self, guild):
        async with self._channel_setup_lock:
            data = get_guild_data(guild.id)
            log_channel = guild.get_channel(int(data['log_channel_id'])) if data.get('log_channel_id') else None
            if not isinstance(log_channel, discord.TextChannel):
                existing = discord.utils.find(lambda c: isinstance(c, discord.TextChannel) and c.name == 'voidflame-logs', guild.text_channels)
                if existing:
                    log_channel = existing
                elif guild.me and guild.me.guild_permissions.manage_channels:
                    try:
                        log_channel = await guild.create_text_channel('voidflame-logs', reason='VoidFlame automatic security log setup')
                    except (discord.Forbidden, discord.HTTPException):
                        log_channel = None
                if log_channel:
                    update_guild_data(guild.id, log_channel_id=log_channel.id)
            alert_channel = guild.get_channel(int(data['staff_channel_id'])) if data.get('staff_channel_id') else None
            if not isinstance(alert_channel, discord.TextChannel) and guild.me and guild.me.guild_permissions.manage_channels:
                existing = discord.utils.find(lambda c: isinstance(c, discord.TextChannel) and c.name == 'voidflame-alerts', guild.text_channels)
                if existing:
                    alert_channel = existing
                else:
                    try:
                        alert_channel = await guild.create_text_channel('voidflame-alerts', reason='VoidFlame automatic security alert setup')
                    except (discord.Forbidden, discord.HTTPException):
                        alert_channel = None
                if alert_channel:
                    update_guild_data(guild.id, staff_channel_id=alert_channel.id)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self.ensure_security_channels(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.ensure_security_channels(guild)
        await self.log(guild, '🛡️ Protector Connected', f'VoidFlame Protector joined **{guild.name}** (`{guild.id}`).', color=discord.Color.green())

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        now = time.monotonic()
        bucket = self.joins[guild.id]
        bucket.append(now)
        while bucket and now - bucket[0] > RAID_WINDOW:
            bucket.popleft()
        await self.log(guild, '👤 Member Joined', f'Member: {member.mention}\nID: `{member.id}`\nAccount: <t:{int(member.created_at.timestamp())}:R>', actor=member, color=discord.Color.green())
        if len(bucket) >= RAID_LIMIT and guild.me and guild.me.guild_permissions.moderate_members:
            await self.log(guild, '🚨 Anti-Raid Triggered', f'**{len(bucket)}** members joined within **{RAID_WINDOW}s**.', color=discord.Color.dark_red())
            for recent in list(guild.members):
                if recent.bot:
                    continue
                try:
                    if (discord.utils.utcnow() - recent.joined_at).total_seconds() <= RAID_WINDOW:
                        await recent.timeout(timedelta(seconds=30), reason='VoidFlame Anti-Raid')
                except (discord.Forbidden, discord.HTTPException):
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        actor, reason = await self.audit(member.guild, discord.AuditLogAction.kick, member.id)
        if actor:
            await self.log(member.guild, '👢 Member Kicked', f'Member: {member.mention}\nActor: {actor.mention}\nReason: `{reason or "No reason provided"}`', actor=actor, color=discord.Color.red())
        else:
            await self.log(member.guild, '👋 Member Left', f'Member: **{member}**\nID: `{member.id}`', actor=member, color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        actor, reason = await self.audit(guild, discord.AuditLogAction.ban, user.id)
        await self.log(guild, '🔨 Member Banned', f'Member: **{user}**\nID: `{user.id}`\nActor: {actor.mention if actor else "Unknown"}\nReason: `{reason or "No reason provided"}`', actor=actor or user, color=discord.Color.red())

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        actor, reason = await self.audit(guild, discord.AuditLogAction.unban, user.id)
        await self.log(guild, '🔓 Member Unbanned', f'Member: **{user}**\nID: `{user.id}`\nActor: {actor.mention if actor else "Unknown"}\nReason: `{reason or "No reason provided"}`', actor=actor or user, color=discord.Color.green())

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        changes = []
        if before.display_name != after.display_name:
            changes.append(f'Name: `{before.display_name}` → `{after.display_name}`')
        if before.avatar != after.avatar:
            changes.append('Avatar changed')
        old_roles = {r.id for r in before.roles}
        new_roles = {r.id for r in after.roles}
        added = [after.guild.get_role(i) for i in new_roles - old_roles]
        removed = [before.guild.get_role(i) for i in old_roles - new_roles]
        if added:
            changes.append('Roles added: ' + ', '.join(r.mention for r in added if r))
        if removed:
            changes.append('Roles removed: ' + ', '.join(r.mention for r in removed if r))
        if before.communication_disabled_until != after.communication_disabled_until:
            changes.append('Timeout: ' + (f'<t:{int(after.communication_disabled_until.timestamp())}:F>' if after.communication_disabled_until else 'removed'))
        if changes:
            actor, reason = await self.audit(after.guild, discord.AuditLogAction.member_update, after.id)
            details = f'Member: {after.mention}\n' + '\n'.join(changes)
            if actor:
                details += f'\nActor: {actor.mention}\nReason: `{reason or "No reason provided"}`'
            await self.log(after.guild, '👤 Member Updated', details, actor=actor or after, color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        guild = message.guild
        data = get_guild_data(guild.id)
        if data.get('protection_enabled', True) is False:
            return
        if INVITE_RE.search(message.content):
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.log(guild, '🔗 Invite Blocked', f'Member: {message.author.mention}\nChannel: {message.channel.mention}\nContent: `{message.content[:1000]}`', actor=message.author, color=discord.Color.orange())
            return
        if len(message.mentions) >= MENTION_LIMIT:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            try:
                await message.author.timeout(timedelta(minutes=2), reason='VoidFlame Anti-Mass-Mention')
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.log(guild, '📢 Anti-Mass-Mention', f'Member: {message.author.mention}\nMentions: **{len(message.mentions)}**', actor=message.author, color=discord.Color.red())
            return
        key = (guild.id, message.author.id)
        now = time.monotonic()
        bucket = self.spam[key]
        bucket.append(now)
        while bucket and now - bucket[0] > SPAM_WINDOW:
            bucket.popleft()
        if len(bucket) >= SPAM_LIMIT:
            try:
                await message.author.timeout(timedelta(seconds=60), reason='VoidFlame Anti-Spam')
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.log(guild, '💬 Anti-Spam', f'Member: {message.author.mention}\nMessages: **{len(bucket)}** in **{SPAM_WINDOW}s**', actor=message.author, color=discord.Color.red())
            bucket.clear()

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild and not message.author.bot:
            await self.log(message.guild, '🗑️ Message Deleted', f'Author: {message.author.mention}\nChannel: {message.channel.mention}\nContent: `{(message.content or "[no text]")[:1800]}`', actor=message.author, color=discord.Color.red())

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if messages:
            await self.log(messages[0].guild, '🗑️ Bulk Delete', f'Channel: {messages[0].channel.mention}\nCount: **{len(messages)}**', color=discord.Color.red())

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild and not before.author.bot and before.content != after.content:
            await self.log(before.guild, '✏️ Message Edited', f'Author: {before.author.mention}\nChannel: {before.channel.mention}\nBefore: `{before.content[:800]}`\nAfter: `{after.content[:800]}`', actor=before.author, color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        actor, reason = await self.audit(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        await self.log(channel.guild, '📁 Channel Created', f'Channel: {channel.mention}\nActor: {actor.mention if actor else "Unknown"}\nReason: `{reason or "No reason provided"}`', actor=actor, color=discord.Color.green())
        await self.nuke_check(channel.guild, 'channel_create', channel.id, actor)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        actor, reason = await self.audit(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        await self.log(channel.guild, '🗑️ Channel Deleted', f'Channel: **{channel.name}**\nID: `{channel.id}`\nActor: {actor.mention if actor else "Unknown"}\nReason: `{reason or "No reason provided"}`', actor=actor, color=discord.Color.red())
        await self.nuke_check(channel.guild, 'channel_delete', channel.id, actor)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        changes = []
        if before.name != after.name: changes.append(f'Name: `{before.name}` → `{after.name}`')
        if before.category_id != after.category_id: changes.append('Category changed')
        if before.position != after.position: changes.append('Position changed')
        if before.overwrites != after.overwrites: changes.append('Permissions/overwrites changed')
        if changes:
            actor, reason = await self.audit(after.guild, discord.AuditLogAction.channel_update, after.id)
            await self.log(after.guild, '📁 Channel Updated', f'Channel: {after.mention}\n' + '\n'.join(changes) + (f'\nActor: {actor.mention}\nReason: `{reason or "No reason provided"}`' if actor else ''), actor=actor, color=discord.Color.orange())
            await self.nuke_check(after.guild, 'channel_update', after.id, actor)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        actor, reason = await self.audit(role.guild, discord.AuditLogAction.role_create, role.id)
        await self.log(role.guild, '🏷️ Role Created', f'Role: {role.mention}\nActor: {actor.mention if actor else "Unknown"}\nReason: `{reason or "No reason provided"}`', actor=actor, color=discord.Color.green())
        await self.nuke_check(role.guild, 'role_create', role.id, actor)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        actor, reason = await self.audit(role.guild, discord.AuditLogAction.role_delete, role.id)
        await self.log(role.guild, '🗑️ Role Deleted', f'Role: **{role.name}**\nID: `{role.id}`\nActor: {actor.mention if actor else "Unknown"}\nReason: `{reason or "No reason provided"}`', actor=actor, color=discord.Color.red())
        await self.nuke_check(role.guild, 'role_delete', role.id, actor)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        changes = []
        if before.name != after.name: changes.append(f'Name: `{before.name}` → `{after.name}`')
        if before.permissions != after.permissions: changes.append('Permissions changed')
        if before.position != after.position: changes.append('Position changed')
        if changes:
            actor, reason = await self.audit(after.guild, discord.AuditLogAction.role_update, after.id)
            await self.log(after.guild, '🏷️ Role Updated', f'Role: {after.mention}\n' + '\n'.join(changes) + (f'\nActor: {actor.mention}\nReason: `{reason or "No reason provided"}`' if actor else ''), actor=actor, color=discord.Color.orange())
            await self.nuke_check(after.guild, 'role_update', after.id, actor)

    async def nuke_check(self, guild, action, target_id, actor):
        if not actor or actor.bot or actor.id == guild.owner_id:
            return
        key = (guild.id, actor.id)
        now = time.monotonic()
        bucket = self.nuke_actions[key]
        bucket.append(now)
        while bucket and now - bucket[0] > 15:
            bucket.popleft()
        if len(bucket) >= 3 and guild.me and guild.me.guild_permissions.moderate_members:
            try:
                await actor.timeout(timedelta(minutes=10), reason='VoidFlame Anti-Nuke')
                result = 'Timeout 10m'
            except (discord.Forbidden, discord.HTTPException):
                result = 'Action failed'
            await self.log(guild, '🚨 Anti-Nuke Triggered', f'Actor: {actor.mention}\nLatest action: `{action}`\nActions in 15s: **{len(bucket)}**\nResponse: **{result}**', actor=actor, color=discord.Color.dark_red())
            bucket.clear()

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        changes = []
        if before.name != after.name: changes.append(f'Name: `{before.name}` → `{after.name}`')
        if before.icon != after.icon: changes.append('Server icon changed')
        if before.verification_level != after.verification_level: changes.append('Verification level changed')
        if before.default_notifications != after.default_notifications: changes.append('Default notifications changed')
        if changes:
            actor, reason = await self.audit(after, discord.AuditLogAction.guild_update)
            await self.log(after, '⚙️ Server Updated', '\n'.join(changes) + (f'\nActor: {actor.mention}\nReason: `{reason or "No reason provided"}`' if actor else ''), actor=actor, color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        try:
            hooks = await channel.webhooks()
        except (discord.Forbidden, discord.HTTPException):
            return
        if len(hooks) <= WEBHOOK_LIMIT:
            return
        actor, reason = await self.audit(channel.guild, discord.AuditLogAction.webhook_create)
        if actor and not actor.bot and actor.id != channel.guild.owner_id:
            try:
                await actor.timeout(timedelta(minutes=10), reason='VoidFlame Anti-Webhook')
            except (discord.Forbidden, discord.HTTPException):
                pass
        await self.log(channel.guild, '🪝 Anti-Webhook', f'Channel: {channel.mention}\nWebhooks: **{len(hooks)}**\nActor: {actor.mention if actor else "Unknown"}\nReason: `{reason or "No reason provided"}`', actor=actor, color=discord.Color.red())

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        changes = []
        if before.channel != after.channel:
            if before.channel and after.channel: changes.append(f'Moved: {before.channel.mention} → {after.channel.mention}')
            elif after.channel: changes.append(f'Joined: {after.channel.mention}')
            else: changes.append(f'Left: {before.channel.mention}')
        if before.self_mute != after.self_mute: changes.append(f'Self mute: **{after.self_mute}**')
        if before.self_deaf != after.self_deaf: changes.append(f'Self deaf: **{after.self_deaf}**')
        if before.mute != after.mute: changes.append(f'Server mute: **{after.mute}**')
        if before.deaf != after.deaf: changes.append(f'Server deaf: **{after.deaf}**')
        if before.self_stream != after.self_stream: changes.append(f'Stream: **{after.self_stream}**')
        if before.self_video != after.self_video: changes.append(f'Camera: **{after.self_video}**')
        if changes:
            await self.log(member.guild, '🔊 Voice Updated', f'Member: {member.mention}\n' + '\n'.join(changes), actor=member, color=discord.Color.blurple())


async def setup(bot):
    await bot.add_cog(ProtectorGuard(bot))
