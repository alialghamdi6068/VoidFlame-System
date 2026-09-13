import os

import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_NAME


class DashboardCommands(commands.Cog):
    """Public/admin dashboard commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='داشبورد')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def dashboard_prefix(self, ctx):
        await ctx.reply('🌐 **لوحة التحكم:**\nhttps://voidflame.wisp.uno/', mention_author=False)

    @app_commands.command(name='info', description='Show information about the bot')
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(title=f'🤖 {BOT_NAME}', description='بوت إدارة Discord مع أنظمة متكاملة ولوحة تحكم.', color=discord.Color.blurple())
        embed.add_field(name='السيرفرات', value=str(len(self.bot.guilds)))
        embed.add_field(name='Ping', value=f'{round(self.bot.latency * 1000)}ms')
        embed.add_field(name='الأوامر', value=f'{len(self.bot.tree.get_commands())} Slash')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='invite', description='Get the bot invite link')
    async def invite(self, interaction: discord.Interaction):
        client_id = str(self.bot.user.id if self.bot.user else '').strip()
        if not client_id:
            return await interaction.response.send_message('❌ تعذر إنشاء رابط الدعوة حاليًا.', ephemeral=True)
        url = f'https://discord.com/oauth2/authorize?client_id={client_id}&scope=bot%20applications.commands'
        await interaction.response.send_message(f'🔗 **رابط إضافة البوت:**\n{url}', ephemeral=True)

    @app_commands.command(name='support', description='Open the support server')
    async def support(self, interaction: discord.Interaction):
        support_url = os.getenv('SUPPORT_URL', '').strip()
        if not support_url:
            return await interaction.response.send_message('❌ رابط الدعم غير متاح حاليًا.', ephemeral=True)
        await interaction.response.send_message(f'🛟 **الدعم:** {support_url}', ephemeral=True)

    @app_commands.command(name='setup', description='Open the bot setup/dashboard')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_command(self, interaction: discord.Interaction):
        dashboard_url = os.getenv('DASHBOARD_URL', '').strip() or 'https://voidflame.wisp.uno/'
        await interaction.response.send_message(f'⚙️ افتح لوحة التحكم لإعداد السيرفر:\n{dashboard_url}', ephemeral=True)

    @app_commands.command(name='sync', description='Synchronize slash commands')
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        await interaction.followup.send(f'✅ تمت مزامنة **{len(synced)}** أمر Slash.', ephemeral=True)

    @app_commands.command(name='reload', description='Reload all bot cogs')
    @app_commands.checks.has_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        names = ['moderation', 'tickets', 'applications', 'levels', 'welcome', 'logs', 'giveaways', 'suggestions', 'afk', 'autoreply', 'autorole', 'announcements', 'reminders', 'scheduler', 'utility', 'owner', 'messaging', 'dashboard_commands']
        failed = []
        for name in names:
            extension = f'cogs.{name}'
            try:
                if extension in self.bot.extensions:
                    await self.bot.reload_extension(extension)
                else:
                    await self.bot.load_extension(extension)
            except Exception as exc:
                failed.append(f'{name}: {type(exc).__name__}')
        if failed:
            return await interaction.followup.send('⚠️ تمت إعادة التحميل مع أخطاء:\n' + '\n'.join(failed), ephemeral=True)
        await interaction.followup.send(f'✅ تمت إعادة تحميل **{len(names)}** ملف.', ephemeral=True)

    @app_commands.command(name='reboot', description='Restart the bot process')
    @app_commands.checks.has_permissions(administrator=True)
    async def reboot(self, interaction: discord.Interaction):
        await interaction.response.send_message('♻️ سيتم إعادة تشغيل البوت الآن.', ephemeral=True)
        await self.bot.close()

    @app_commands.command(name='avatar', description='Show a member avatar')
    async def avatar(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        embed = discord.Embed(title=f'🖼️ صورة {member.display_name}', color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='server', description='Show server information')
    @app_commands.guild_only()
    async def server(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=f'🏠 {guild.name}', color=discord.Color.blurple())
        embed.add_field(name='الأعضاء', value=str(guild.member_count or 0))
        embed.add_field(name='الرومات', value=str(len(guild.channels)))
        embed.add_field(name='الأدوار', value=str(len(guild.roles)))
        embed.add_field(name='المالك', value=f'<@{guild.owner_id}>' if guild.owner_id else 'غير معروف')
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='role', description='Show role information')
    @app_commands.guild_only()
    async def role(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(title=f'🏷️ {role.name}', color=role.color)
        embed.add_field(name='ID', value=str(role.id), inline=False)
        embed.add_field(name='الأعضاء', value=str(len(role.members)))
        embed.add_field(name='الموضع', value=str(role.position))
        embed.add_field(name='منشن', value=role.mention)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(DashboardCommands(bot))
