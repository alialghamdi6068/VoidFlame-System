import random
import re

import discord
from discord import app_commands
from discord.ext import commands

from database import connection, log_activity
from services.warning_service import issue_warning

CREATOR_ID = 1293157778030071920


def parse_mention_id(value: str):
    match = re.fullmatch(r'<@!?(\d+)>', value.strip())
    return int(match.group(1)) if match else None


class NewCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.remove_command('تحذير')

    async def _send_warning_dm(self, member, guild, moderator, reason, number):
        embed = discord.Embed(title='⚠️ تم تحذيرك', color=discord.Color.orange())
        embed.description = f'تم تسجيل تحذير على حسابك في سيرفر **{guild.name}**.'
        embed.add_field(name='السبب', value=reason[:1024], inline=False)
        embed.add_field(name='بواسطة', value=moderator.mention, inline=True)
        embed.add_field(name='رقم التحذير', value=f'#{number}', inline=True)
        embed.set_footer(text=f'{guild.name} • نظام الإدارة')
        try:
            await member.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def _warn_member(self, guild, member, moderator, reason):
        count, dm_sent, action = await issue_warning(guild, member, moderator, reason, self.bot)
        return count, dm_sent


    @commands.command(name='تحذير')
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, target: str, *, reason='بدون سبب'):
        reason = reason.strip()[:1000] or 'بدون سبب'
        role_match = re.fullmatch(r'<@&(\d+)>', target.strip())
        if role_match:
            role = ctx.guild.get_role(int(role_match.group(1)))
            if not role or role.is_default() or role.managed:
                return await ctx.reply('❌ الرتبة غير صالحة.')
            members = [m for m in role.members if not m.bot]
            if not members:
                return await ctx.reply(f'ℹ️ لا يوجد أعضاء قابلون للتحذير في {role.mention}.')
            sent = 0
            failed = 0
            skipped = 0
            for member in members:
                try:
                    _, dm = await self._warn_member(ctx.guild, member, ctx.author, reason)
                    sent += int(dm)
                    failed += int(not dm)
                except ValueError:
                    skipped += 1
            return await ctx.reply(
                f'⚠️ تم تحذير **{sent + failed}** عضوًا في {role.mention}.\n'
                f'📩 الخاص: **{sent}** | تعذر الإرسال: **{failed}** | تم تخطي: **{skipped}**'
            )

        member_id = parse_mention_id(target)
        member = ctx.guild.get_member(member_id) if member_id else None
        if member is None:
            try:
                member = await commands.MemberConverter().convert(ctx, target)
            except commands.BadArgument:
                return await ctx.reply('❌ استخدم منشن عضو أو منشن رتبة.')
        if member.bot:
            return await ctx.reply('❌ لا يمكن تحذير البوتات.')
        try:
            count, dm_sent = await self._warn_member(ctx.guild, member, ctx.author, reason)
        except ValueError as exc:
            messages = {
                'target_owner': '❌ ما تقدر تحذر مالك السيرفر.',
                'target_bot': '❌ ما تقدر تحذر البوت نفسه.',
                'member_hierarchy': '❌ رتبة العضو أعلى من رتبة البوت أو مساوية لها.',
                'target_self': '❌ ما تقدر تحذر نفسك.',
            }
            return await ctx.reply(messages.get(str(exc), '❌ تعذر إصدار التحذير.'))
        dm_text = 'تم إرسال الخاص.' if dm_sent else 'تعذر إرسال الخاص لهذا العضو.'
        await ctx.reply(f'⚠️ تم تحذير {member.mention}. مجموع التحذيرات: **{count}**.\n📩 {dm_text}')

    @app_commands.command(name='slowmode', description='Set channel slowmode in seconds')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode_slash(self, interaction: discord.Interaction, seconds: int):
        if not 0 <= seconds <= 21600:
            return await interaction.response.send_message('❌ المدة من 0 إلى 21600 ثانية.', ephemeral=True)
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message('❌ هذا الأمر للقنوات النصية.', ephemeral=True)
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f'🐢 تم ضبط البطء على **{seconds}** ثانية.')

    @commands.command(name='بطء')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode_prefix(self, ctx, seconds: int):
        if not 0 <= seconds <= 21600:
            return await ctx.reply('❌ المدة من 0 إلى 21600 ثانية.')
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.reply('❌ هذا الأمر للقنوات النصية.')
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.reply(f'🐢 تم ضبط بطء الروم على **{seconds}** ثانية.')

    @commands.command(name='نقل')
    @commands.guild_only()
    @commands.has_permissions(move_members=True)
    @commands.bot_has_permissions(move_members=True)
    async def move_member(self, ctx, member: discord.Member):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.reply('❌ لازم تكون داخل روم صوتي أولًا.')
        if not member.voice or not member.voice.channel:
            return await ctx.reply('❌ العضو ليس داخل روم صوتي.')
        await member.move_to(ctx.author.voice.channel, reason=f'نقل بواسطة {ctx.author}')
        await ctx.reply(f'🔊 تم نقل {member.mention} إلى {ctx.author.voice.channel.mention}.')

    @commands.command(name='فك حظر')
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str):
        try:
            uid = int(user_id.strip('<@!>'))
        except ValueError:
            return await ctx.reply('❌ أرسل ID صحيح.')
        try:
            await ctx.guild.unban(discord.Object(id=uid), reason=f'فك حظر بواسطة {ctx.author}')
            log_activity(ctx.guild.id, 'unban', str(uid), ctx.author.id)
            await ctx.reply(f'✅ تم فك الحظر عن `{uid}`.')
        except discord.NotFound:
            await ctx.reply('❌ هذا المستخدم غير محظور.')

    @commands.command(name='معلومات')
    @commands.guild_only()
    async def user_info(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        embed = discord.Embed(title=f'👤 معلومات {member}', color=discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name='ID', value=f'`{member.id}`')
        embed.add_field(name='اسم المستخدم', value=f'`{member}`')
        embed.add_field(name='إنشاء الحساب', value=discord.utils.format_dt(member.created_at, 'F'), inline=False)
        embed.add_field(name='دخول السيرفر', value=discord.utils.format_dt(member.joined_at, 'F') if member.joined_at else 'غير معروف', inline=False)
        embed.add_field(name='الرتبة الأعلى', value=member.top_role.mention)
        await ctx.reply(embed=embed)

    @commands.command(name='أفاتار')
    @commands.guild_only()
    async def avatar(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        embed = discord.Embed(title=f'🖼️ أفاتار {member}', color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name='بانر')
    @commands.guild_only()
    async def banner(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        try:
            user = await self.bot.fetch_user(member.id)
        except discord.HTTPException:
            user = member
        if not user.banner:
            return await ctx.reply('❌ هذا العضو لا يملك بانرًا.')
        embed = discord.Embed(title=f'🎨 بانر {member}', color=discord.Color.blurple())
        embed.set_image(url=user.banner.url)
        await ctx.reply(embed=embed)

    @commands.command(name='رتب')
    @commands.guild_only()
    async def roles(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        roles = [r.mention for r in reversed(member.roles[1:])]
        await ctx.reply(f'🏷️ رتب {member.mention}:\n' + (' '.join(roles)[:1900] if roles else 'بدون رتب.'))

    @commands.command(name='سيرفر')
    @commands.guild_only()
    async def server(self, ctx):
        g = ctx.guild
        await ctx.reply(f'🏠 **{g.name}**\n👥 الأعضاء: **{g.member_count or 0}**\n💬 القنوات: **{len(g.channels)}**\n🏷️ الرتب: **{len(g.roles)-1}**\n📅 الإنشاء: {discord.utils.format_dt(g.created_at, "D")}')

    @commands.command(name='احصائيات')
    async def stats(self, ctx):
        guilds = len(self.bot.guilds)
        users = len({m.id for g in self.bot.guilds for m in g.members})
        channels = sum(len(g.channels) for g in self.bot.guilds)
        await ctx.reply(f'📊 **إحصائيات البوت**\n🏠 السيرفرات: **{guilds}**\n👥 المستخدمون: **{users}**\n📚 القنوات: **{channels}**\n🏓 Ping: **{round(self.bot.latency*1000)}ms**')

    @commands.command(name='صانع')
    async def creator(self, ctx):
        await ctx.reply(f'👨‍💻 صانع البوت: <@{CREATOR_ID}>')

    @commands.command(name='اعطاء_رتبة')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def give_role(self, ctx, member: discord.Member, role: discord.Role):
        if role.is_default() or role.managed:
            return await ctx.reply('❌ لا يمكن إعطاء هذه الرتبة.')
        if role >= ctx.guild.me.top_role:
            return await ctx.reply('❌ رتبة البوت أقل من الرتبة المطلوبة. ارفع رتبة البوت فوقها.')
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply('❌ لا يمكنك إعطاء رتبة أعلى من أو مساوية لرتبتك.')
        if role in member.roles:
            return await ctx.reply(f'ℹ️ {member.mention} لديه هذه الرتبة بالفعل.')
        try:
            await member.add_roles(role, reason=f'إعطاء رتبة بواسطة {ctx.author}')
        except discord.Forbidden:
            return await ctx.reply('❌ لا أملك صلاحية إعطاء هذه الرتبة.')
        log_activity(ctx.guild.id, 'give_role', f'{member} -> {role}', ctx.author.id)
        await ctx.reply(f'✅ تم إعطاء {member.mention} الرتبة {role.mention}.')

    @commands.command(name='سحب_رتبة')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def remove_role(self, ctx, member: discord.Member, role: discord.Role):
        if role.is_default() or role.managed:
            return await ctx.reply('❌ لا يمكن سحب هذه الرتبة.')
        if role >= ctx.guild.me.top_role:
            return await ctx.reply('❌ رتبة البوت أقل من الرتبة المطلوبة.')
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply('❌ لا يمكنك سحب رتبة أعلى من أو مساوية لرتبتك.')
        if role not in member.roles:
            return await ctx.reply(f'ℹ️ {member.mention} لا يملك هذه الرتبة.')
        try:
            await member.remove_roles(role, reason=f'سحب رتبة بواسطة {ctx.author}')
        except discord.Forbidden:
            return await ctx.reply('❌ لا أملك صلاحية سحب هذه الرتبة.')
        log_activity(ctx.guild.id, 'remove_role', f'{member} <- {role}', ctx.author.id)
        await ctx.reply(f'✅ تم سحب الرتبة {role.mention} من {member.mention}.')

    @commands.command(name='ريست لفل')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reset_level(self, ctx, target: str):
        if target.strip().lower() == 'الكل':
            with connection() as conn:
                conn.execute('DELETE FROM levels WHERE guild_id=?', (ctx.guild.id,))
            log_activity(ctx.guild.id, 'reset_all_levels', 'all members', ctx.author.id)
            return await ctx.reply('🔄 تم تصفير مستويات وXP جميع أعضاء السيرفر.')
        member_id = parse_mention_id(target)
        member = ctx.guild.get_member(member_id) if member_id else None
        if member is None:
            try:
                member = await commands.MemberConverter().convert(ctx, target)
            except commands.BadArgument:
                return await ctx.reply('❌ استخدم منشن عضو أو اكتب `الكل`.')
        with connection() as conn:
            conn.execute('DELETE FROM levels WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id))
        log_activity(ctx.guild.id, 'reset_level', str(member), member.id)
        await ctx.reply(f'🔄 تم تصفير لفل وXP {member.mention}.')

    @app_commands.command(name='resetlevel', description='Reset a member level')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reset_level_slash(self, interaction: discord.Interaction, member: discord.Member):
        with connection() as conn:
            conn.execute('DELETE FROM levels WHERE guild_id=? AND user_id=?', (interaction.guild.id, member.id))
        log_activity(interaction.guild.id, 'reset_level', str(member), interaction.user.id)
        await interaction.response.send_message(f'🔄 تم تصفير لفل وXP {member.mention}.')

    @app_commands.command(name='creator', description='Show the bot creator')
    async def creator_slash(self, interaction):
        await interaction.response.send_message(f'👨‍💻 صانع البوت: <@{CREATOR_ID}>')


async def setup(bot):
    await bot.add_cog(NewCommands(bot))
