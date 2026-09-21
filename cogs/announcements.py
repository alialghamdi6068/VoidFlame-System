import discord
from discord import app_commands
from discord.ext import commands
from database import get_guild_data


class Announcements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def target_channel(self, guild, fallback):
        settings = get_guild_data(guild.id)
        if settings.get('announcements_enabled', True) is False:
            return None
        channel_id = settings.get('announcements_channel_id')
        channel = guild.get_channel(int(channel_id)) if channel_id else fallback
        return channel if isinstance(channel, discord.TextChannel) else fallback

    @commands.command(name='تنبيه')
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def announcement(self, ctx, *, text: str):
        if get_guild_data(ctx.guild.id).get('announcements_enabled', True) is False:
            return await ctx.reply('❌ نظام الإعلانات متوقف حاليًا.')
        channel = await self.target_channel(ctx.guild, ctx.channel)
        if channel is None:
            return await ctx.reply('❌ نظام الإعلانات متوقف حاليًا.')
        embed = discord.Embed(title='📢 إعلان', description=text[:4000], color=discord.Color.blurple())
        embed.set_footer(text=f'بواسطة {ctx.author}')
        await channel.send(embed=embed)
        if channel.id != ctx.channel.id:
            await ctx.reply(f'✅ تم إرسال الإعلان في {channel.mention}.')

    @app_commands.command(name='announcement', description='Send an announcement')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def announcement_slash(self, interaction: discord.Interaction, text: str):
        if get_guild_data(interaction.guild.id).get('announcements_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام الإعلانات متوقف حاليًا.', ephemeral=True)
        channel = await self.target_channel(interaction.guild, interaction.channel)
        if channel is None:
            return await interaction.response.send_message('❌ نظام الإعلانات متوقف حاليًا.', ephemeral=True)
        embed = discord.Embed(title='📢 إعلان', description=text[:4000], color=discord.Color.blurple())
        embed.set_footer(text=f'بواسطة {interaction.user}')
        await channel.send(embed=embed)
        await interaction.response.send_message(f'✅ تم إرسال الإعلان في {channel.mention}.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Announcements(bot))
