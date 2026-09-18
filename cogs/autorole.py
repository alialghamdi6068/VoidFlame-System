import discord
from discord import app_commands
from discord.ext import commands
from database import get_guild_data, update_guild_data, log_activity


class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        settings = get_guild_data(member.guild.id)
        if settings.get('autorole_enabled', True) is False:
            return
        role_id = settings.get('auto_role_id')
        if not role_id:
            return
        role = member.guild.get_role(int(role_id))
        me = member.guild.me
        if not role or not me or not role.is_assignable():
            return
        try:
            await member.add_roles(role, reason='Flame auto role')
            log_activity(member.guild.id, 'auto_role', f'{member} -> {role.name}', member.id)
        except discord.HTTPException:
            pass

    @commands.command(name='رتبة_تلقائية')
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def set_role(self, ctx, role: discord.Role):
        if not role.is_assignable():
            return await ctx.reply('❌ البوت لا يستطيع إعطاء هذه الرتبة. تأكد أن رتبته أعلى منها.')
        update_guild_data(ctx.guild.id, auto_role_id=role.id)
        await ctx.reply(f'✅ تم تحديد الرتبة التلقائية: {role.mention}')

    @app_commands.command(name='autorole', description='Set the automatic member role')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def set_role_slash(self, interaction, role: discord.Role):
        if not role.is_assignable():
            return await interaction.response.send_message('❌ البوت لا يستطيع إعطاء هذه الرتبة.', ephemeral=True)
        update_guild_data(interaction.guild.id, auto_role_id=role.id)
        await interaction.response.send_message(f'✅ تم تحديد الرتبة التلقائية: {role.mention}')


async def setup(bot):
    await bot.add_cog(AutoRole(bot))
