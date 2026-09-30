import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_NAME, OWNER_ID


def owner_id_check():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)


def owner_slash_check():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.id == OWNER_ID
    return app_commands.check(predicate)


class Owner(commands.Cog):
    """Commands reserved strictly for the configured bot owner ID."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='حالة')
    @owner_id_check()
    async def status(self, ctx):
        await ctx.reply(f'🔥 **{BOT_NAME}**\nالسيرفرات: **{len(self.bot.guilds)}**\nPing: **{round(self.bot.latency * 1000)}ms**', mention_author=False)

    @commands.command(name='مزامنة')
    @owner_id_check()
    async def sync_prefix(self, ctx):
        synced = await self.bot.tree.sync()
        await ctx.reply(f'✅ تمت مزامنة **{len(synced)}** أمر Slash.', mention_author=False)

    @commands.command(name='السيرفرات')
    @owner_id_check()
    async def guilds(self, ctx):
        lines = [f'• **{guild.name}** — `{guild.id}`' for guild in self.bot.guilds]
        await ctx.reply('\n'.join(lines)[:4000] or 'لا توجد سيرفرات.', mention_author=False)

    @commands.command(name='دعوة_البوت')
    @owner_id_check()
    async def bot_invite(self, ctx):
        client_id = self.bot.user.id if self.bot.user else None
        if not client_id:
            return await ctx.reply('❌ البوت غير جاهز.', mention_author=False)
        url = f'https://discord.com/oauth2/authorize?client_id={client_id}&scope=bot%20applications.commands'
        await ctx.reply(f'🔗 {url}', mention_author=False)

    @app_commands.command(name='owner_status', description='Show owner-only bot status')
    @owner_slash_check()
    async def owner_status(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f'🔥 **{BOT_NAME}**\nالسيرفرات: **{len(self.bot.guilds)}**\nPing: **{round(self.bot.latency * 1000)}ms**',
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Owner(bot))