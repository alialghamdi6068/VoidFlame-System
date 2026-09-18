import re
import discord
from discord import app_commands
from discord.ext import commands
from database import connection, log_activity, get_guild_data


class WarnSlash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _warn(self, guild, member, moderator, reason):
        with connection() as conn:
            conn.execute('INSERT INTO warnings(guild_id,user_id,moderator_id,reason) VALUES(?,?,?,?)', (guild.id, member.id, moderator.id, reason))
            count = conn.execute('SELECT COUNT(*) AS c FROM warnings WHERE guild_id=? AND user_id=?', (guild.id, member.id)).fetchone()['c']
        settings = get_guild_data(guild.id)
        dm_sent = False
        if settings.get('warn_dm_enabled', True):
            template = str(settings.get('warn_dm_message', 'تم تحذيرك في سيرفر {server}.\\n\\nالسبب: {reason}\\nرقم التحذير: #{count}\\nبواسطة: {moderator}'))[:2000]
            text = template.replace('{user}', str(member)).replace('{server}', guild.name).replace('{reason}', reason).replace('{count}', str(count)).replace('{moderator}', str(moderator))
            try:
                await member.send(text)
                dm_sent = True
            except (discord.Forbidden, discord.HTTPException):
                pass
        log_activity(guild.id, 'warn', f'{member} | {reason} | DM={dm_sent}', member.id)
        return count, dm_sent

    @app_commands.command(name='warn', description='Warn a member or everyone with a role')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, target: str, reason: str = 'بدون سبب'):
        target = target.strip()
        reason = (reason or 'بدون سبب').strip()[:1000]
        role_match = re.fullmatch(r'<@&(\d+)>', target)
        if role_match:
            role = interaction.guild.get_role(int(role_match.group(1)))
            if not role or role.is_default() or role.managed:
                return await interaction.response.send_message('❌ الرتبة غير صالحة.', ephemeral=True)
            members = [m for m in role.members if not m.bot]
            if not members:
                return await interaction.response.send_message('ℹ️ لا يوجد أعضاء قابلون للتحذير في هذه الرتبة.', ephemeral=True)
            await interaction.response.defer()
            dm_sent = 0
            for member in members:
                _, dm = await self._warn(interaction.guild, member, interaction.user, reason)
                dm_sent += int(dm)
            return await interaction.followup.send(f'⚠️ تم تحذير **{len(members)}** عضوًا في {role.mention}. 📩 الخاص: **{dm_sent}**')

        member_match = re.fullmatch(r'<@!?(\d+)>', target)
        member = interaction.guild.get_member(int(member_match.group(1))) if member_match else None
        if not member:
            return await interaction.response.send_message('❌ أرسل منشن عضو أو منشن رتبة.', ephemeral=True)
        if member.bot:
            return await interaction.response.send_message('❌ لا يمكن تحذير البوتات.', ephemeral=True)
        count, dm = await self._warn(interaction.guild, member, interaction.user, reason)
        await interaction.response.send_message(f'⚠️ تم تحذير {member.mention}. مجموع التحذيرات: **{count}**. 📩 {"تم إرسال الخاص" if dm else "تعذر إرسال الخاص"}.')


async def setup(bot):
    bot.tree.remove_command('warn')
    await bot.add_cog(WarnSlash(bot))
