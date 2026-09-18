from datetime import timedelta
import discord
from database import connection, get_guild_data, log_activity


async def issue_warning(guild, member, moderator, reason):
    reason = (reason or "بدون سبب").strip()[:1000]
    with connection() as conn:
        conn.execute(
            "INSERT INTO warnings(guild_id,user_id,moderator_id,reason) VALUES(?,?,?,?)",
            (guild.id, member.id, moderator.id, reason),
        )
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM warnings WHERE guild_id=? AND user_id=?",
            (guild.id, member.id),
        ).fetchone()["c"]

    settings = get_guild_data(guild.id)
    dm_sent = False
    if settings.get("warn_dm_enabled", True):
        template = str(settings.get(
            "warn_dm_message",
            "تم تحذيرك في سيرفر {server}.\n\nالسبب: {reason}\nرقم التحذير: #{count}\nبواسطة: {moderator}",
        ))[:2000]
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
    rules = settings.get("warning_escalation", {
        "2": {"action": "timeout", "minutes": 5},
        "3": {"action": "timeout", "minutes": 15},
        "4": {"action": "timeout", "minutes": 60},
        "5": {"action": "timeout", "minutes": 180},
    })
    rule = rules.get(str(count)) if isinstance(rules, dict) else None
    if isinstance(rule, dict):
        target_action = rule.get("action", "warning")
        me = guild.me
        if target_action == "timeout" and me and me.guild_permissions.moderate_members and member != guild.owner and member.top_role < me.top_role:
            minutes = max(1, min(40320, int(rule.get("minutes", 10))))
            try:
                await member.timeout(timedelta(minutes=minutes), reason=f"Warning escalation #{count}: {reason}")
                action = f"warning + timeout {minutes}m"
            except discord.HTTPException:
                action = "warning + timeout_failed"
        elif target_action == "kick" and me and me.guild_permissions.kick_members and member != guild.owner and member.top_role < me.top_role:
            try:
                await member.kick(reason=f"Warning escalation #{count}: {reason}")
                action = "warning + kick"
            except discord.HTTPException:
                action = "warning + kick_failed"

    log_activity(guild.id, "warn", f"{member} | {reason} | count={count} | action={action} | DM={dm_sent}", member.id)
    logs = getattr(guild, "_voidflame_logs", None)
    return count, dm_sent, action


def remove_warning(guild_id, warning_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM warnings WHERE guild_id=? AND id=?", (guild_id, warning_id)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM warnings WHERE guild_id=? AND id=?", (guild_id, warning_id))
        return row
