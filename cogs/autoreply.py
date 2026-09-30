import discord
from discord.ext import commands
from database import get_guild_data, update_guild_data, log_activity


class AutoReply(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return

        settings = get_guild_data(message.guild.id)
        if settings.get('autoreply_enabled', False) is False:
            return

        channel_id = settings.get('autoreply_channel_id')
        if channel_id and message.channel.id != int(channel_id):
            return

        replies = settings.get('autoreplies', {})
        if not isinstance(replies, dict):
            return

        # Deliberately use the raw message content: only a literal full-message
        # match triggers a reply. No substring, prefix, case-folding, or
        # whitespace normalization is performed.
        text = message.content
        for trigger, response in replies.items():
            if text == str(trigger):
                try:
                    await message.channel.send(
                        str(response)[:2000],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass
                break

    @commands.command(name='رد')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def add_reply(self, ctx, trigger: str, *, response: str):
        settings = get_guild_data(ctx.guild.id)
        if settings.get('autoreply_enabled', False) is False:
            return await ctx.reply('❌ نظام الردود التلقائية متوقف حاليًا.')

        replies = dict(settings.get('autoreplies', {}))
        trigger = trigger.strip()[:100]
        if not trigger:
            return await ctx.reply('❌ كلمة التفعيل لا يمكن أن تكون فارغة.')

        replies[trigger] = response[:2000]
        update_guild_data(ctx.guild.id, autoreplies=replies)
        log_activity(ctx.guild.id, 'autoreply_add', trigger, ctx.author.id)
        await ctx.reply('✅ تم حفظ الرد التلقائي.')

    @commands.command(name='حذف_رد')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def remove_reply(self, ctx, trigger: str):
        settings = get_guild_data(ctx.guild.id)
        if settings.get('autoreply_enabled', False) is False:
            return await ctx.reply('❌ نظام الردود التلقائية متوقف حاليًا.')

        replies = dict(settings.get('autoreplies', {}))
        if trigger not in replies:
            return await ctx.reply('❌ هذا الرد غير موجود.')

        replies.pop(trigger)
        update_guild_data(ctx.guild.id, autoreplies=replies)
        log_activity(ctx.guild.id, 'autoreply_remove', trigger, ctx.author.id)
        await ctx.reply('🗑️ تم حذف الرد التلقائي.')

async def setup(bot):
    await bot.add_cog(AutoReply(bot))
