import re
import time
import discord
from discord.ext import commands, tasks
from database import connection, log_activity, get_guild_data

DURATION_RE=re.compile(r'^(\d+)([smhd])$',re.I)
def seconds(value):
    m=DURATION_RE.fullmatch(value.strip())
    if not m: raise ValueError
    return int(m.group(1))*{'s':1,'m':60,'h':3600,'d':86400}[m.group(2).lower()]

class Scheduler(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.loop.start()
    def cog_unload(self):
        self.loop.cancel()
    @tasks.loop(seconds=5)
    async def loop(self):
        with connection() as conn:
            rows=conn.execute('SELECT * FROM schedules WHERE sent=0 AND due_at<=?',(time.time(),)).fetchall()
            for row in rows:
                conn.execute('UPDATE schedules SET sent=1 WHERE id=? AND sent=0',(row['id'],))
        for row in rows:
            if get_guild_data(row['guild_id']).get('scheduler_enabled', True) is False:
                with connection() as conn:
                    conn.execute('UPDATE schedules SET sent=0 WHERE id=? AND sent=1', (row['id'],))
                continue
            channel=self.bot.get_channel(row['channel_id'])
            guild=self.bot.get_guild(row['guild_id'])
            if guild:
                configured=get_guild_data(guild.id).get('scheduler_channel_id')
                if configured:
                    channel=guild.get_channel(int(configured))
            delivered=False
            if isinstance(channel,discord.TextChannel):
                try:
                    await channel.send(row['text'],allowed_mentions=discord.AllowedMentions.none())
                    delivered=True
                except (discord.Forbidden,discord.HTTPException):
                    pass
            if not delivered:
                with connection() as conn:
                    conn.execute('UPDATE schedules SET sent=0 WHERE id=?',(row['id'],))
    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
    @commands.command(name='جدولة')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def schedule(self,ctx,duration:str,*,text:str):
        if get_guild_data(ctx.guild.id).get('scheduler_enabled', True) is False:
            return await ctx.reply('❌ نظام الجدولة متوقف حاليًا.')
        try: delay=seconds(duration)
        except ValueError: return await ctx.reply('❌ استخدم `10m` أو `2h` أو `1d`.')
        if delay<5 or delay>30*86400: return await ctx.reply('❌ المدة يجب أن تكون بين 5 ثوانٍ و30 يوم.')
        with connection() as conn:
            conn.execute('INSERT INTO schedules(guild_id,channel_id,text,due_at) VALUES(?,?,?,?)',(ctx.guild.id,ctx.channel.id,text[:2000],time.time()+delay))
        log_activity(ctx.guild.id,'schedule_create',text[:200],ctx.author.id)
        await ctx.reply('✅ تمت جدولة الرسالة.')
    @commands.command(name='جدولة_روم')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def set_channel(self,ctx,channel:discord.TextChannel):
        from database import update_guild_data
        update_guild_data(ctx.guild.id,scheduler_channel_id=channel.id)
        await ctx.reply(f'✅ تم تحديد روم الجدولة: {channel.mention}')
async def setup(bot):
    await bot.add_cog(Scheduler(bot))
