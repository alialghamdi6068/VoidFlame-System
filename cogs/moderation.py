import datetime

import discord
from discord import app_commands
from discord.ext import commands
from database import connection, log_activity, get_guild_data
from services.warning_service import issue_warning


def reason_text(reason: str | None) -> str:
    return (reason or 'بدون سبب').strip()[:1000]


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ban(self, guild, member, reason):
        await member.ban(reason=reason)
        log_activity(guild.id, 'ban', f'{member} | {reason}', member.id)

    async def _kick(self, guild, member, reason):
        await member.kick(reason=reason)
        log_activity(guild.id, 'kick', f'{member} | {reason}', member.id)

    async def _timeout(self, guild, member, minutes, reason):
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        log_activity(guild.id, 'timeout', f'{member} | {minutes}m | {reason}', member.id)

    async def _change_role(self, guild, member, role, add: bool, moderator):
        me = guild.me
        if me is None:
            raise RuntimeError('Bot member is unavailable')
        if role.is_default() or role.managed:
            raise ValueError('invalid_role')
        if role >= me.top_role:
            raise ValueError('role_hierarchy')
        if member == guild.owner:
            raise ValueError('target_owner')
        if member.top_role >= me.top_role and member != me:
            raise ValueError('member_hierarchy')

        if add:
            if role in member.roles:
                return False
            await member.add_roles(role, reason=f'إعطاء رتبة بواسطة {moderator}')
            action = 'give_role'
        else:
            if role not in member.roles:
                return False
            await member.remove_roles(role, reason=f'سحب رتبة بواسطة {moderator}')
            action = 'remove_role'

        log_activity(guild.id, action, f'{member} | {role.name}', member.id)
        return True

    @commands.command(name='باند')
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban_prefix(self, ctx, member: discord.Member, *, reason='بدون سبب'):
        if member == ctx.guild.owner:
            return await ctx.reply('❌ ما تقدر تحظر مالك السيرفر.')
        if member == ctx.guild.me:
            return await ctx.reply('❌ ما تقدر تحظر البوت نفسه.')
        if member.top_role >= ctx.guild.me.top_role and member != ctx.guild.owner:
            return await ctx.reply('❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.')
        await self._ban(ctx.guild, member, reason_text(reason))
        await ctx.reply(f'🔨 تم حظر {member.mention}.')

    @app_commands.command(name='ban', description='Ban a member')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = 'بدون سبب'):
        if member == interaction.guild.owner:
            return await interaction.response.send_message('❌ ما تقدر تحظر مالك السيرفر.')
        if member.top_role >= interaction.guild.me.top_role and member != interaction.guild.owner:
            return await interaction.response.send_message('❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.')
        await self._ban(interaction.guild, member, reason_text(reason))
        await interaction.response.send_message(f'🔨 تم حظر {member.mention}.')

    @commands.command(name='طرد')
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick_prefix(self, ctx, member: discord.Member, *, reason='بدون سبب'):
        if member == ctx.guild.owner:
            return await ctx.reply('❌ ما تقدر تطرد مالك السيرفر.')
        if member.top_role >= ctx.guild.me.top_role and member != ctx.guild.owner:
            return await ctx.reply('❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.')
        await self._kick(ctx.guild, member, reason_text(reason))
        await ctx.reply(f'👢 تم طرد {member.mention}.')

    @app_commands.command(name='kick', description='Kick a member')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = 'بدون سبب'):
        if member == interaction.guild.owner:
            return await interaction.response.send_message('❌ ما تقدر تطرد مالك السيرفر.')
        if member.top_role >= interaction.guild.me.top_role and member != interaction.guild.owner:
            return await interaction.response.send_message('❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.')
        await self._kick(interaction.guild, member, reason_text(reason))
        await interaction.response.send_message(f'👢 تم طرد {member.mention}.')

    @commands.command(name='تايم')
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout_prefix(self, ctx, member: discord.Member, minutes: int, *, reason='بدون سبب'):
        if not 1 <= minutes <= 40320:
            return await ctx.reply('❌ المدة يجب أن تكون بين دقيقة و28 يوم.')
        if member == ctx.guild.owner:
            return await ctx.reply('❌ ما تقدر تعطي تايم لمالك السيرفر.')
        if member.top_role >= ctx.guild.me.top_role and member != ctx.guild.owner:
            return await ctx.reply('❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.')
        await self._timeout(ctx.guild, member, minutes, reason_text(reason))
        await ctx.reply(f'⏳ تم إعطاء {member.mention} تايم لمدة **{minutes}** دقيقة.')

    @app_commands.command(name='timeout', description='Timeout a member')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout_slash(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = 'بدون سبب'):
        if not 1 <= minutes <= 40320:
            return await interaction.response.send_message('❌ المدة يجب أن تكون بين دقيقة و28 يوم.')
        if member == interaction.guild.owner:
            return await interaction.response.send_message('❌ ما تقدر تعطي تايم لمالك السيرفر.')
        if member.top_role >= interaction.guild.me.top_role and member != interaction.guild.owner:
            return await interaction.response.send_message('❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.')
        await self._timeout(interaction.guild, member, minutes, reason_text(reason))
        await interaction.response.send_message(f'⏳ تم إعطاء {member.mention} تايم لمدة **{minutes}** دقيقة.')

    @commands.command(name='فك_تايم')
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout_prefix(self, ctx, member: discord.Member):
        await member.timeout(None, reason=f'Un-timeout by {ctx.author}')
        log_activity(ctx.guild.id, 'untimeout', str(member), member.id)
        await ctx.reply(f'✅ تم فك التايم عن {member.mention}.')

    @app_commands.command(name='untimeout', description='Remove a member timeout')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout_slash(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None, reason=f'Un-timeout by {interaction.user}')
        log_activity(interaction.guild.id, 'untimeout', str(member), member.id)
        await interaction.response.send_message(f'✅ تم فك التايم عن {member.mention}.')

    @commands.command(name='اعطاء رتبة')
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def give_role_prefix(self, ctx, member: discord.Member, role: discord.Role):
        try:
            changed = await self._change_role(ctx.guild, member, role, True, ctx.author)
        except ValueError as exc:
            messages = {
                'invalid_role': '❌ ما تقدر تعطي رتبة @everyone أو رتبة مرتبطة ببوت/تكامل.',
                'role_hierarchy': '❌ رتبة البوت لازم تكون أعلى من الرتبة اللي تبي تعطيها.',
                'target_owner': '❌ ما تقدر تعدل رتب مالك السيرفر.',
                'member_hierarchy': '❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.',
            }
            return await ctx.reply(messages.get(str(exc), '❌ ما قدرت أعطي الرتبة.'))
        if not changed:
            return await ctx.reply(f'ℹ️ {member.mention} عنده رتبة {role.mention} بالفعل.')
        await ctx.reply(f'✅ تم إعطاء {role.mention} إلى {member.mention}.')

    @app_commands.command(name='give-role', description='Give a role to a member')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def give_role_slash(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            changed = await self._change_role(interaction.guild, member, role, True, interaction.user)
        except ValueError as exc:
            messages = {
                'invalid_role': '❌ ما تقدر تعطي رتبة @everyone أو رتبة مرتبطة ببوت/تكامل.',
                'role_hierarchy': '❌ رتبة البوت لازم تكون أعلى من الرتبة اللي تبي تعطيها.',
                'target_owner': '❌ ما تقدر تعدل رتب مالك السيرفر.',
                'member_hierarchy': '❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.',
            }
            return await interaction.response.send_message(messages.get(str(exc), '❌ ما قدرت أعطي الرتبة.'))
        if not changed:
            return await interaction.response.send_message(f'ℹ️ {member.mention} عنده رتبة {role.mention} بالفعل.')
        await interaction.response.send_message(f'✅ تم إعطاء {role.mention} إلى {member.mention}.')

    @commands.command(name='سحب رتبة')
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def remove_role_prefix(self, ctx, member: discord.Member, role: discord.Role):
        try:
            changed = await self._change_role(ctx.guild, member, role, False, ctx.author)
        except ValueError as exc:
            messages = {
                'invalid_role': '❌ ما تقدر تسحب @everyone أو رتبة مرتبطة ببوت/تكامل.',
                'role_hierarchy': '❌ رتبة البوت لازم تكون أعلى من الرتبة اللي تبي تسحبها.',
                'target_owner': '❌ ما تقدر تعدل رتب مالك السيرفر.',
                'member_hierarchy': '❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.',
            }
            return await ctx.reply(messages.get(str(exc), '❌ ما قدرت أسحب الرتبة.'))
        if not changed:
            return await ctx.reply(f'ℹ️ {member.mention} ما عنده رتبة {role.mention}.')
        await ctx.reply(f'✅ تم سحب {role.mention} من {member.mention}.')

    @app_commands.command(name='remove-role', description='Remove a role from a member')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_role_slash(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            changed = await self._change_role(interaction.guild, member, role, False, interaction.user)
        except ValueError as exc:
            messages = {
                'invalid_role': '❌ ما تقدر تسحب @everyone أو رتبة مرتبطة ببوت/تكامل.',
                'role_hierarchy': '❌ رتبة البوت لازم تكون أعلى من الرتبة اللي تبي تسحبها.',
                'target_owner': '❌ ما تقدر تعدل رتب مالك السيرفر.',
                'member_hierarchy': '❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.',
            }
            return await interaction.response.send_message(messages.get(str(exc), '❌ ما قدرت أسحب الرتبة.'))
        if not changed:
            return await interaction.response.send_message(f'ℹ️ {member.mention} ما عنده رتبة {role.mention}.')
        await interaction.response.send_message(f'✅ تم سحب {role.mention} من {member.mention}.')

    @commands.command(name='تحذير')
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warn_prefix(self, ctx, member: discord.Member, *, reason='بدون سبب'):
        count, dm_sent, action = await issue_warning(ctx.guild, member, ctx.author, reason_text(reason), self.bot)
        await ctx.reply(f'⚠️ تم تحذير {member.mention}. مجموع التحذيرات: **{count}**. الإجراء: **{action}**. 📩 {"تم إرسال الخاص" if dm_sent else "الخاص غير متاح"}')

    @app_commands.command(name='warn', description='Warn a member')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = 'بدون سبب'):
        count, dm_sent, action = await issue_warning(interaction.guild, member, interaction.user, reason_text(reason), self.bot)
        await interaction.response.send_message(f'⚠️ تم تحذير {member.mention}. مجموع التحذيرات: **{count}**. الإجراء: **{action}**. 📩 {"تم إرسال الخاص" if dm_sent else "الخاص غير متاح"}')

    @commands.command(name='تحذيرات')
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warnings_prefix(self, ctx, member: discord.Member):
        with connection() as conn:
            rows = conn.execute('SELECT reason, moderator_id, created_at FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10', (ctx.guild.id, member.id)).fetchall()
        if not rows:
            return await ctx.reply(f'✅ {member.mention} ما عليه تحذيرات.')
        lines = [f'**{i}.** {row["reason"]} — <@{row["moderator_id"]}> ({row["created_at"]})' for i, row in enumerate(rows, 1)]
        await ctx.reply(f'⚠️ تحذيرات {member.mention}:\n' + '\n'.join(lines))

    @commands.command(name='مسح_تحذيرات')
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def clear_warnings_prefix(self, ctx, member: discord.Member):
        with connection() as conn:
            conn.execute('DELETE FROM warnings WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id))
        log_activity(ctx.guild.id, 'clear_warnings', str(member), member.id)
        await ctx.reply(f'🧹 تم مسح تحذيرات {member.mention}.')

    @commands.command(name='حذف_تحذير')
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def remove_warning_prefix(self, ctx, warning_id: int):
        with connection() as conn:
            row = conn.execute('SELECT * FROM warnings WHERE id=? AND guild_id=?', (warning_id, ctx.guild.id)).fetchone()
            if not row:
                return await ctx.reply('❌ ما لقيت تحذير بهذا الرقم.')
            conn.execute('DELETE FROM warnings WHERE id=? AND guild_id=?', (warning_id, ctx.guild.id))
        log_activity(ctx.guild.id, 'warning_remove', f'Warning #{warning_id} | User {row["user_id"]}', ctx.author.id)
        await ctx.reply(f'✅ تم حذف التحذير **#{warning_id}** من <@{row["user_id"]}>.')

    @app_commands.command(name='remove-warning', description='Remove a warning by ID')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def remove_warning_slash(self, interaction: discord.Interaction, warning_id: int):
        with connection() as conn:
            row = conn.execute('SELECT * FROM warnings WHERE id=? AND guild_id=?', (warning_id, interaction.guild.id)).fetchone()
            if not row:
                return await interaction.response.send_message('❌ ما لقيت تحذير بهذا الرقم.', ephemeral=True)
            conn.execute('DELETE FROM warnings WHERE id=? AND guild_id=?', (warning_id, interaction.guild.id))
        log_activity(interaction.guild.id, 'warning_remove', f'Warning #{warning_id} | User {row["user_id"]}', interaction.user.id)
        await interaction.response.send_message(f'✅ تم حذف التحذير **#{warning_id}** من <@{row["user_id"]}>.')

    @commands.command(name='مسح')
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_prefix(self, ctx, amount: int):
        if not 1 <= amount <= 100:
            return await ctx.reply('❌ العدد يجب أن يكون بين 1 و100.')
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f'🧹 تم حذف **{max(0, len(deleted) - 1)}** رسالة.', delete_after=4)
        log_activity(ctx.guild.id, 'purge', str(amount), ctx.author.id)

    @app_commands.command(name='clear', description='Delete messages')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge_slash(self, interaction: discord.Interaction, amount: int):
        if not 1 <= amount <= 100:
            return await interaction.response.send_message('❌ العدد يجب أن يكون بين 1 و100.')
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        log_activity(interaction.guild.id, 'purge', str(amount), interaction.user.id)
        await interaction.followup.send(f'🧹 تم حذف **{len(deleted)}** رسالة.')

    async def _set_lock(self, channel, locked):
        overwrite = channel.overwrites_for(channel.guild.default_role)
        overwrite.send_messages = False if locked else None
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)

    @commands.command(name='قفل')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock_prefix(self, ctx):
        await self._set_lock(ctx.channel, True)
        await ctx.reply('🔒 تم قفل الروم.')

    @commands.command(name='فتح')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock_prefix(self, ctx):
        await self._set_lock(ctx.channel, False)
        await ctx.reply('🔓 تم فتح الروم.')

    @commands.command(name='قفل_روم')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def lock_room_prefix(self, ctx, channel: discord.TextChannel | None = None):
        channel = channel or ctx.channel
        await self._set_lock(channel, True)
        await ctx.reply(f'🔒 تم قفل {channel.mention}.')

    @commands.command(name='فتح_روم')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unlock_room_prefix(self, ctx, channel: discord.TextChannel | None = None):
        channel = channel or ctx.channel
        await self._set_lock(channel, False)
        await ctx.reply(f'🔓 تم فتح {channel.mention}.')

    @commands.command(name='تثبيت')
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def pin_prefix(self, ctx, message_id: int):
        try:
            message = await ctx.channel.fetch_message(message_id)
            await message.pin()
            await ctx.reply('📌 تم تثبيت الرسالة.')
        except discord.HTTPException:
            await ctx.reply('❌ ما قدرت أثبت الرسالة.')

    @commands.command(name='اعلان')
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def announce_prefix(self, ctx, channel: discord.TextChannel, *, text: str):
        embed = discord.Embed(title='📢 إعلان', description=text, color=discord.Color.blurple())
        embed.set_footer(text=f'بواسطة {ctx.author}')
        await channel.send(embed=embed)
        await ctx.reply('✅ تم إرسال الإعلان.')

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.MissingPermissions, commands.BotMissingPermissions)):
            await ctx.reply('❌ ما عندك الصلاحية المطلوبة أو البوت ناقصه صلاحية.')
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply('❌ ناقصك متغير في الأمر.')
        elif isinstance(error, commands.BadArgument):
            await ctx.reply('❌ تأكد من المنشن/الرقم/الرتبة والبيانات المدخلة.')
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.Forbidden):
            await ctx.reply('❌ Discord رفض العملية. تأكد أن رتبة البوت أعلى من الرتبة المستهدفة وأن الصلاحيات صحيحة.')
        else:
            await ctx.reply(f'❌ صار خطأ: `{type(error).__name__}`')
            raise error


async def setup(bot):
    await bot.add_cog(Moderation(bot))
