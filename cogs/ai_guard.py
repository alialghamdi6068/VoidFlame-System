import discord
import time
from collections import defaultdict
from datetime import timedelta
from discord.ext import commands
from database import connection
from services.warning_service import issue_warning
from services.settings_cache import settings_cache
from services.moderation_engine import ModerationEngine

class AIGuard(commands.Cog):
    def __init__(self, bot):
        self.bot=bot
        self.engine=ModerationEngine()
        self.cooldowns=defaultdict(float)

    def ignored(self,message,settings):
        if not settings.get("ai_enabled",True) or message.author.bot or message.webhook_id:
            return True
        if message.channel.id in {int(x) for x in settings.get("ai_ignore_channels",[]) if str(x).isdigit()}:
            return True
        ignored_roles={int(x) for x in settings.get("ai_ignore_roles",[]) if str(x).isdigit()}
        return bool(ignored_roles & {r.id for r in message.author.roles})

    async def log(self,guild,title,description,actor=None,color=None):
        logs=self.bot.get_cog("Logs")
        if logs:
            await logs.send_log(guild,title,description,actor=actor,color=color)

    @commands.Cog.listener()
    async def on_message(self,message):
        if not message.guild or not message.content.strip():
            return
        try:
            settings=settings_cache.get(message.guild.id)
            if self.ignored(message,settings): return
            r=self.engine.analyze(message.content)
            minimum=int(settings.get("ai_min_score",40))
            if r.score<minimum: return
            medium=int(settings.get("ai_medium_score",40))
            high=int(settings.get("ai_high_score",70))
            key=(message.guild.id,message.author.id)
            now=time.monotonic()
            cooldown=max(5,int(settings.get("ai_action_cooldown_seconds",20)))
            if now < self.cooldowns[key]: return
            self.cooldowns[key]=now+cooldown
            with connection() as conn:
                recent=conn.execute("SELECT COUNT(*) c FROM warnings WHERE guild_id=? AND user_id=? AND created_at >= datetime('now','-15 minutes')",(message.guild.id,message.author.id)).fetchone()["c"]
            action="log"
            if r.score>=high:
                member=message.author
                if message.guild.me and message.guild.me.guild_permissions.moderate_members and member.top_role < message.guild.me.top_role and member != message.guild.owner:
                    minutes=min(40320,max(1,int(settings.get("ai_timeout_minutes",10))))
                    if recent>=int(settings.get("ai_repeat_threshold",3)): minutes=min(40320,minutes*2)
                    await member.timeout(timedelta(minutes=minutes),reason=f"VoidFlame protection score={r.score}")
                    action=f"timeout {minutes}m"
                else:
                    action="detected; timeout unavailable"
            elif r.score>=medium:
                try:
                    count, dm_sent, escalation = await issue_warning(message.guild, message.author, message.guild.me or self.bot.user, r.reason, self.bot)
                    action=f"warning #{count}"
                    if escalation != "warning":
                        action += f" + {escalation}"
                    if not dm_sent:
                        action += " (DM unavailable)"
                except ValueError:
                    action="detected; warning target unavailable"
            await self.log(message.guild,"AI Moderation",f"Member: {message.author.mention}\nChannel: {message.channel.mention}\nScore: {r.score}/100\nConfidence: {r.confidence:.0%}\nCategory: {r.category}\nAction: {action}\nReason: {r.reason}\nContent: {message.content[:1000]}",message.author,discord.Color.red() if r.score>=high else discord.Color.orange())
        except Exception as exc:
            print(f"[VoidFlame AI] {type(exc).__name__}: {exc}")

async def setup(bot):
    await bot.add_cog(AIGuard(bot))
