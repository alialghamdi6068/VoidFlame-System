from datetime import timedelta

import discord

from database import connection, get_guild_data, log_activity


DEFAULT_ESCALATION = {
    "2": {"action": "timeout", "minutes": 5},
    "3": {"action": "timeout", "minutes": 15},
    "4": {"action": "timeout", "minutes": 60},
    "5": {"action": "timeout", "minutes": 180},
}


def _minutes(value, default=10):
    try:
        return max(1, min(40320, int(value)))
    except (TypeError, ValueError):
        return default


async def issue_warning(guild, member, moderator, reason, bot=None):
    if member == guild.owner:
        raise ValueError("target_owner")
    if member == guild.me:
        raise ValueError("target_bot")

    me = guild.me
    if me is not None and member.top_role >= me.top_role:
        raise ValueError("member_hierarchy")

    # A human moderator should not be able to warn someone at or above
    # their own role. The bot/automated moderator is governed by bot hierarchy.
    if moderator != guild.me and hasattr(moderator, "top_role"):
        if member.top_role >= moderator.top_role:
            raise ValueError("moderator_hierarchy")

    if member == moderator:
        raise ValueError("target_self")

    reason = (reason or "بدون سبب").strip()[:1000]

    settings = get_guild_data(guild.id)
    if settings.get("warnings_enabled", True) is False:
        raise ValueError("system_disabled")

    with connection() as conn:
        conn.execute(
            "INSERT INTO warnings(guild_id,user_id,moderator_id,reason) "
            "VALUES(?,?,?,?)",
            (guild.id, member.id, moderator.id, reason),
        )
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM warnings "
            "WHERE guild_id=? AND user_id=?",
            (guild.id, member.id),
        ).fetchone()["c"]

    dm_sent = False
    if settings.get("warn_dm_enabled", True):
        template = str(
            settings.get(
                "warn_dm_message",
                "تم تحذيرك في سيرفر {server}.\n\n"
                "السبب: {reason}\n"
                "رقم التحذير: #{count}\n"
                "بواسطة: {moderator}",
            )
        )[:2000]
        text = (
            template.replace("{user}", str(member))
            .replace("{server}", guild.name)
            .replace("{reason}", reason)
            .replace("{count}", str(count))
            .replace("{moderator}", str(moderator))
        )
        try:
            await member.send(text)
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            pass

    action = "warning"
    configured_rules = settings.get("warning_escalation", DEFAULT_ESCALATION)
    rules = configured_rules if isinstance(configured_rules, dict) else DEFAULT_ESCALATION
    rule = rules.get(str(count))

    if isinstance(rule, dict):
        target_action = str(rule.get("action", "warning")).lower()
        if target_action == "timeout":
            if (
                me
                and me.guild_permissions.moderate_members
                and member != guild.owner
                and member.top_role < me.top_role
            ):
                minutes = _minutes(rule.get("minutes", 10))
                try:
                    await member.timeout(
                        timedelta(minutes=minutes),
                        reason=f"Warning escalation #{count}: {reason}",
                    )
                    action = f"warning + timeout {minutes}m"
                except (discord.Forbidden, discord.HTTPException):
                    action = "warning + timeout_failed"
            else:
                action = "warning + timeout_unavailable"
        elif target_action == "kick":
            if (
                me
                and me.guild_permissions.kick_members
                and member != guild.owner
                and member.top_role < me.top_role
            ):
                try:
                    await member.kick(
                        reason=f"Warning escalation #{count}: {reason}"
                    )
                    action = "warning + kick"
                except (discord.Forbidden, discord.HTTPException):
                    action = "warning + kick_failed"
            else:
                action = "warning + kick_unavailable"

    log_activity(
        guild.id,
        "warn",
        f"{member} | {reason} | count={count} | action={action} | DM={dm_sent}",
        member.id,
    )

    if bot is not None:
        logs = bot.get_cog("Logs")
        if logs:
            try:
                await logs.send_log(
                    guild,
                    "Warning",
                    f"Member: {member.mention}\n"
                    f"Moderator: {moderator.mention}\n"
                    f"Count: {count}\n"
                    f"Action: {action}\n"
                    f"DM: {'sent' if dm_sent else 'unavailable'}\n"
                    f"Reason: {reason}",
                    actor=moderator,
                    color=discord.Color.orange(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    return count, dm_sent, action


def remove_warning(guild_id, warning_id):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM warnings WHERE guild_id=? AND id=?",
            (guild_id, warning_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "DELETE FROM warnings WHERE guild_id=? AND id=?",
            (guild_id, warning_id),
        )
        return row
