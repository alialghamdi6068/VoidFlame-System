import re
import time
import discord
from discord.ext import commands, tasks
from database import connection, log_activity, get_guild_data

DURATION_RE = re.compile(r'^(\d+)([smhd])$', re.I)

def seconds(value):
    m = DURATION_RE.fullmatch(value.strip())
    if not m:
        raise ValueError
    return int(m.group(1)) * {'s':1,'m':60,'h':3600,'d':86400}[m.group(2).lower()]

class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot=bot
        self.loop.start()
    def cog_unload(self):
        self.loop.cancel()
    @tasks.loop(seconds=5)
    async def loop(self):
        with connection() as conn:
            rows=conn.execute('SELECT * FROM reminders WHERE sent=0 AND due_at<=?',(time.time(),)).fetchall()
            for row in rows:
                conn.execute('UPDATE reminders SET sent=1 WHERE id=? AND sent=0',(row['id'],))
        for row in rows:
            if get_guild_data(row['guild_id']).get('reminders_enabled', True) is False:
                with connection() as conn:
                    conn.execute('UPDATE reminders SET sent=0 WHERE id=? AND sent=1', (row['id'],))
                continue
            user=self.bot.get_user(row['user_id'])
            if not user:
                try:
                    user=await self.bot.fetch_user(row['user_id'])
                except (discord.NotFound, discord.HTTPException):
                    with connection() as conn:
                        conn.execute('UPDATE reminders SET sent=0 WHERE id=?',(row['id'],))
                    continue
            delivered=False
            try:
                await user.send(f'⏰ **تذكيرك:**\n{row["text"]}')
                delivered=True
            except (discord.Forbidden, discord.HTTPException):
                settings=get_guild_data(row['guild_id'])
                configured=settings.get('reminder_channel_id')
                channel=self.bot.get_channel(int(configured)) if configured else self.bot.get_channel(row['channel_id'])
                if isinstance(channel,discord.TextChannel):
                    try:
                        await channel.send(f'⏰ {user.mention} تذكيرك: {row["text"]}',allowed_mentions=discord.AllowedMentions(users=True))
                        delivered=True
                    except (discord.Forbidden,discord.HTTPException):
                        pass
            if not delivered:
                with connection() as conn:
                    conn.execute('UPDATE reminders SET sent=0 WHERE id=?',(row['id'],))
    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
    @commands.command(name='تذكير')
    @commands.guild_only()
    async def reminder(self,ctx,duration:str,*,text:str):
        try: delay=seconds(duration)
        except ValueError: return await ctx.reply('❌ استخدم `10m` أو `2h` أو `1d`.')
        if delay<5 or delay>30*86400: return await ctx.reply('❌ المدة يجب أن تكون بين 5 ثوانٍ و30 يوم.')
        with connection() as conn:
            conn.execute('INSERT INTO reminders(guild_id,user_id,channel_id,text,due_at) VALUES(?,?,?,?,?)',(ctx.guild.id,ctx.author.id,ctx.channel.id,text[:1000],time.time()+delay))
        log_activity(ctx.guild.id,'reminder_create',text[:200],ctx.author.id)
        await ctx.reply('✅ تم إنشاء التذكير.')
    @commands.command(name='تذكيرات_روم')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def set_channel(self,ctx,channel:discord.TextChannel):
        from database import update_guild_data
        update_guild_data(ctx.guild.id,reminder_channel_id=channel.id)
        await ctx.reply(f'✅ تم تحديد روم التذكيرات: {channel.mention}')
async def setup(bot):
    await bot.add_cog(Reminders(bot))
