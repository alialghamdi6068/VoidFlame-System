import discord
from discord.ext import commands
from database import connection, get_guild_data, update_guild_data, log_activity


class Suggestions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def create(self, guild, user, content, channel):
        if get_guild_data(guild.id).get('suggestions_enabled', True) is False:
            return None
        with connection() as conn:
            cur = conn.execute('INSERT INTO suggestions(guild_id,user_id,content) VALUES(?,?,?)', (guild.id, user.id, content[:2000]))
            suggestion_id = cur.lastrowid
        embed = discord.Embed(title=f'💡 اقتراح #{suggestion_id}', description=content[:2000], color=discord.Color.blurple())
        embed.add_field(name='صاحب الاقتراح', value=user.mention)
        embed.add_field(name='الحالة', value='🟡 قيد المراجعة')
        try:
            msg = await channel.send(embed=embed)
        except discord.HTTPException:
            with connection() as conn:
                conn.execute('DELETE FROM suggestions WHERE id=? AND guild_id=?',(suggestion_id,guild.id))
            return None
        try:
            await msg.add_reaction('👍')
            await msg.add_reaction('👎')
        except discord.HTTPException:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass
            with connection() as conn:
                conn.execute('DELETE FROM suggestions WHERE id=? AND guild_id=?',(suggestion_id,guild.id))
            return None
        await msg.add_reaction('👎')
        with connection() as conn:
            conn.execute('UPDATE suggestions SET message_id=? WHERE id=?', (msg.id, suggestion_id))
        log_activity(guild.id, 'suggestion', f'#{suggestion_id}', user.id)
        return suggestion_id

    async def set_status(self, ctx, suggestion_id, status):
        with connection() as conn:
            row = conn.execute('SELECT * FROM suggestions WHERE guild_id=? AND id=?', (ctx.guild.id, suggestion_id)).fetchone()
            if not row:
                return await ctx.reply('❌ الاقتراح غير موجود.')
            conn.execute('UPDATE suggestions SET status=? WHERE id=?', (status, suggestion_id))
        message = None
        channel_id = get_guild_data(ctx.guild.id).get('suggestions_channel_id')
        channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(row['message_id'])
            except (discord.NotFound, discord.Forbidden):
                message = None
        if message:
            embed = message.embeds[0] if message.embeds else discord.Embed(description=row['content'])
            embed.color = discord.Color.green() if status == 'accepted' else discord.Color.red()
            value = '🟢 مقبول' if status == 'accepted' else '🔴 مرفوض'
            if len(embed.fields) > 1:
                embed.set_field_at(1, name='الحالة', value=value)
            else:
                embed.add_field(name='الحالة', value=value)
            try:
                await message.edit(embed=embed)
            except discord.HTTPException:
                with connection() as conn:
                    conn.execute('UPDATE suggestions SET status=? WHERE guild_id=? AND id=?',(row['status'],ctx.guild.id,suggestion_id))
                return await ctx.reply('❌ تعذر تحديث رسالة الاقتراح. لم يتم اعتماد التغيير.')
        await ctx.reply('✅ تم تحديث حالة الاقتراح.')
        log_activity(ctx.guild.id, 'suggestion_review', f'#{suggestion_id} -> {status}', ctx.author.id)
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Suggestion Review', f'#{suggestion_id} -> {status}', actor=ctx.author, color=discord.Color.green() if status=='accepted' else discord.Color.red())

    @commands.command(name='اقتراح')
    @commands.guild_only()
    async def suggestion_prefix(self, ctx, *, content: str):
        settings = get_guild_data(ctx.guild.id)
        channel_id = settings.get('suggestions_channel_id')
        channel = ctx.guild.get_channel(int(channel_id)) if channel_id else ctx.channel
        if not isinstance(channel, discord.TextChannel):
            return await ctx.reply('❌ روم الاقتراحات غير صحيح.')
        suggestion_id = await self.create(ctx.guild, ctx.author, content, channel)
        if suggestion_id is None:
            return await ctx.reply('❌ نظام الاقتراحات متوقف حاليًا.')
        if channel.id != ctx.channel.id:
            await ctx.reply(f'✅ تم إرسال اقتراحك في {channel.mention}.')

    @commands.command(name='اقتراحات')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def configure(self, ctx, channel: discord.TextChannel):
        update_guild_data(ctx.guild.id, suggestions_channel_id=channel.id)
        await ctx.reply(f'✅ تم تحديد روم الاقتراحات: {channel.mention}')

    @commands.command(name='قبول_اقتراح')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def accept(self, ctx, suggestion_id: int):
        await self.set_status(ctx, suggestion_id, 'accepted')

    @commands.command(name='رفض_اقتراح')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reject(self, ctx, suggestion_id: int):
        await self.set_status(ctx, suggestion_id, 'rejected')


async def setup(bot):
    await bot.add_cog(Suggestions(bot))
