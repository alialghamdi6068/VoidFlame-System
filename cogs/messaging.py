import discord
from discord.ext import commands
from database import log_activity


class Messaging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='dm')
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def dm(self, ctx, member: discord.Member, *, text: str):
        if not text.strip():
            return await ctx.reply('❌ اكتب الرسالة التي تريد إرسالها.')
        try:
            await member.send(text[:2000], allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            return await ctx.reply('❌ تعذر إرسال الرسالة الخاصة لهذا العضو.')
        except discord.HTTPException:
            return await ctx.reply('❌ فشل إرسال الرسالة الخاصة.')
        log_activity(ctx.guild.id, 'dm', f'{member} | {text[:500]}', ctx.author.id)
        await ctx.reply(f'✅ تم إرسال الرسالة الخاصة إلى {member.mention}.')

    @commands.command(name='قول')
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def say(self, ctx, *, text: str):
        if not text.strip():
            return await ctx.reply('❌ اكتب الكلام الذي تريد أن يقوله البوت.')
        await ctx.message.delete()
        await ctx.send(text[:2000], allowed_mentions=discord.AllowedMentions(everyone=True, users=True, roles=True))
        log_activity(ctx.guild.id, 'say', text[:500], ctx.author.id)


async def setup(bot):
    await bot.add_cog(Messaging(bot))
