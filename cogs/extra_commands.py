import asyncio
import random
import re
from datetime import datetime, timezone

import discord
import requests
from discord import app_commands
from discord.ext import commands

from database import connection, log_activity


class ExtraCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='تحقق')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def verify(self, ctx, member: discord.Member):
        roles = ', '.join(r.mention for r in member.roles[1:]) or 'بدون رتب'
        embed = discord.Embed(title='🔎 تحقق من العضو', color=discord.Color.blurple())
        embed.add_field(name='العضو', value=f'{member.mention}\n`{member.id}`')
        embed.add_field(name='الحساب', value=discord.utils.format_dt(member.created_at, 'F'), inline=False)
        embed.add_field(name='دخل السيرفر', value=discord.utils.format_dt(member.joined_at, 'F') if member.joined_at else 'غير معروف', inline=False)
        embed.add_field(name='الرتب', value=roles[:1024], inline=False)
        await ctx.reply(embed=embed)

    @commands.command(name='رابط')
    @commands.guild_only()
    async def invite_link(self, ctx):
        invites = await ctx.guild.invites()
        usable = [i for i in invites if i.max_age == 0 and i.max_uses == 0]
        if usable:
            return await ctx.reply(f'🔗 {usable[0].url}')
        try:
            invite = await ctx.channel.create_invite(max_age=0, max_uses=0, reason=f'رابط بواسطة {ctx.author}')
            await ctx.reply(f'🔗 {invite.url}')
        except discord.Forbidden:
            await ctx.reply('❌ البوت يحتاج صلاحية إنشاء دعوات.')

    @commands.command(name='دعوات')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def invites(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        try:
            invites = await ctx.guild.invites()
            count = sum(i.uses or 0 for i in invites if i.inviter and i.inviter.id == member.id)
            await ctx.reply(f'📨 {member.mention} لديه **{count}** استخدام دعوات مسجل.')
        except discord.Forbidden:
            await ctx.reply('❌ البوت يحتاج صلاحية إدارة السيرفر لقراءة الدعوات.')

    @commands.command(name='اعلى دعوات')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def top_invites(self, ctx):
        try:
            invites = await ctx.guild.invites()
            counts = {}
            for invite in invites:
                if invite.inviter:
                    counts[invite.inviter.id] = counts.get(invite.inviter.id, 0) + (invite.uses or 0)
            top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
            if not top:
                return await ctx.reply('📨 لا توجد بيانات دعوات.')
            lines = [f'**{i}.** <@{uid}> — **{count}**' for i, (uid, count) in enumerate(top, 1)]
            await ctx.reply('🏆 **أعلى 10 في الدعوات**\n' + '\n'.join(lines))
        except discord.Forbidden:
            await ctx.reply('❌ لا أستطيع قراءة دعوات السيرفر.')

    @commands.command(name='ايموجيات')
    @commands.guild_only()
    async def emojis(self, ctx):
        if not ctx.guild.emojis:
            return await ctx.reply('😀 لا توجد إيموجيات مخصصة.')
        text = ' '.join(str(e) for e in ctx.guild.emojis)
        await ctx.reply(f'😀 **إيموجيات السيرفر ({len(ctx.guild.emojis)})**\n{text[:1900]}')

    @commands.command(name='ستيكرات')
    @commands.guild_only()
    async def stickers(self, ctx):
        stickers = ctx.guild.stickers
        if not stickers:
            return await ctx.reply('🏷️ لا توجد ستيكرات.')
        lines = [f'• **{s.name}**' for s in stickers]
        await ctx.reply(f'🏷️ **ستيكرات السيرفر ({len(stickers)})**\n' + '\n'.join(lines)[:1900])

    @commands.command(name='قنوات')
    @commands.guild_only()
    async def channels(self, ctx):
        text = len(ctx.guild.text_channels)
        voice = len(ctx.guild.voice_channels)
        cats = len(ctx.guild.categories)
        await ctx.reply(f'📚 **قنوات السيرفر**\n💬 نصية: **{text}**\n🔊 صوتية: **{voice}**\n📁 أقسام: **{cats}**')

    @commands.command(name='رتب السيرفر')
    @commands.guild_only()
    async def server_roles(self, ctx):
        roles = [r.mention for r in reversed(ctx.guild.roles) if not r.is_default()]
        await ctx.reply(f'🏷️ **رتب السيرفر ({len(roles)})**\n' + (' '.join(roles)[:1900] if roles else 'لا توجد رتب.'))

    @commands.command(name='اعضاء اونلاين')
    @commands.guild_only()
    async def online_members(self, ctx):
        online = sum(1 for m in ctx.guild.members if m.status != discord.Status.offline)
        await ctx.reply(f'🟢 الأعضاء المتصلون: **{online}** من **{ctx.guild.member_count or 0}**')

    @commands.command(name='بوتات')
    @commands.guild_only()
    async def bots(self, ctx):
        bots = [m for m in ctx.guild.members if m.bot]
        if not bots:
            return await ctx.reply('🤖 لا توجد بوتات.')
        await ctx.reply('🤖 **بوتات السيرفر**\n' + '\n'.join(f'• {b.mention}' for b in bots)[:1900])

    @commands.command(name='نشاط')
    @commands.guild_only()
    async def activity(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        with connection() as conn:
            rows = conn.execute('SELECT action, details, created_at FROM activity WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10', (ctx.guild.id, member.id)).fetchall()
        if not rows:
            return await ctx.reply(f'📊 لا يوجد نشاط مسجل لـ {member.mention}.')
        lines = [f'• `{r["created_at"]}` — **{r["action"]}** — {r["details"][:120]}' for r in rows]
        await ctx.reply(f'📊 **آخر نشاط لـ {member.mention}**\n' + '\n'.join(lines)[:1900])

    @commands.command(name='اكثر نشاط')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def most_active(self, ctx):
        with connection() as conn:
            rows = conn.execute('SELECT user_id, COUNT(*) AS c FROM activity WHERE guild_id=? AND user_id IS NOT NULL GROUP BY user_id ORDER BY c DESC LIMIT 10', (ctx.guild.id,)).fetchall()
        if not rows:
            return await ctx.reply('📊 لا توجد بيانات نشاط.')
        await ctx.reply('🏆 **أكثر الأعضاء نشاطًا في سجلات البوت**\n' + '\n'.join(f'**{i}.** <@{r["user_id"]}> — **{r["c"]}** عملية' for i, r in enumerate(rows, 1)))

    @commands.command(name='احصائيات السيرفر')
    @commands.guild_only()
    async def server_stats(self, ctx):
        embed = discord.Embed(title=f'📊 إحصائيات {ctx.guild.name}', color=discord.Color.blurple())
        embed.add_field(name='👥 الأعضاء', value=str(ctx.guild.member_count or 0))
        embed.add_field(name='🤖 البوتات', value=str(sum(m.bot for m in ctx.guild.members)))
        embed.add_field(name='💬 القنوات النصية', value=str(len(ctx.guild.text_channels)))
        embed.add_field(name='🔊 القنوات الصوتية', value=str(len(ctx.guild.voice_channels)))
        embed.add_field(name='🏷️ الرتب', value=str(len(ctx.guild.roles) - 1))
        embed.add_field(name='😀 الإيموجيات', value=str(len(ctx.guild.emojis)))
        embed.add_field(name='📅 الإنشاء', value=discord.utils.format_dt(ctx.guild.created_at, 'D'))
        await ctx.reply(embed=embed)

    @commands.command(name='تسجيل')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def logging_status(self, ctx):
        with connection() as conn:
            count = conn.execute('SELECT COUNT(*) AS c FROM activity WHERE guild_id=?', (ctx.guild.id,)).fetchone()['c']
        await ctx.reply(f'📝 نظام التسجيل يعمل.\nعدد السجلات المحفوظة: **{count}**')

    @commands.command(name='سجل العضو')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def member_log(self, ctx, member: discord.Member):
        with connection() as conn:
            rows = conn.execute('SELECT action, details, created_at FROM activity WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 20', (ctx.guild.id, member.id)).fetchall()
        if not rows:
            return await ctx.reply('📝 لا يوجد سجل لهذا العضو.')
        lines = [f'`{r["created_at"]}` **{r["action"]}** — {r["details"][:100]}' for r in rows]
        await ctx.reply(f'📝 **سجل {member}**\n' + '\n'.join(lines)[:1900])

    @commands.command(name='حظ')
    async def luck(self, ctx):
        await ctx.reply(f'🍀 نسبة حظك اليوم: **{random.randint(1, 100)}%**')

    @commands.command(name='رقم')
    async def random_number(self, ctx, minimum: int = 1, maximum: int = 100):
        if minimum > maximum or maximum - minimum > 1000000:
            return await ctx.reply('❌ نطاق الأرقام غير صالح.')
        await ctx.reply(f'🎲 الرقم العشوائي: **{random.randint(minimum, maximum)}**')

    @commands.command(name='وقت')
    async def current_time(self, ctx):
        now = datetime.now().astimezone()
        await ctx.reply(f'🕐 الوقت الآن: **{now:%H:%M:%S}**')

    @commands.command(name='تاريخ')
    async def current_date(self, ctx):
        now = datetime.now().astimezone()
        await ctx.reply(f'📅 التاريخ: **{now:%Y-%m-%d}**')

    @commands.command(name='عمر الحساب')
    async def account_age(self, ctx, member: discord.Member | None = None):
        member = member or ctx.author
        age = datetime.now(timezone.utc) - member.created_at
        await ctx.reply(f'👤 حساب {member.mention} عمره تقريبًا **{age.days} يوم**.')

    @commands.command(name='عمر السيرفر')
    @commands.guild_only()
    async def server_age(self, ctx):
        age = datetime.now(timezone.utc) - ctx.guild.created_at
        await ctx.reply(f'🏠 السيرفر عمره تقريبًا **{age.days} يوم**.')

    @commands.command(name='سرعة')
    async def speed(self, ctx):
        message = await ctx.reply('⚡ جاري القياس...')
        latency = round(self.bot.latency * 1000)
        await message.edit(content=f'⚡ سرعة البوت: **{latency}ms**')

    @commands.command(name='اختيار')
    async def choose(self, ctx, *, options: str):
        values = [x.strip() for x in options.split('|') if x.strip()]
        if len(values) < 2:
            return await ctx.reply('❌ اكتب خيارين أو أكثر بهذا الشكل: `!اختيار خيار1 | خيار2`')
        await ctx.reply(f'🎯 اختياري: **{random.choice(values)}**')

    @commands.command(name='عملة')
    async def coin(self, ctx):
        await ctx.reply(f'🪙 **{random.choice(["صورة", "كتابة"])}**')

    @commands.command(name='نرد')
    async def dice(self, ctx):
        await ctx.reply(f'🎲 رميت النرد وطلع: **{random.randint(1, 6)}**')

    @commands.command(name='حساب')
    async def calculator(self, ctx, *, expression: str):
        expression = expression.strip()
        if len(expression) > 100 or not re.fullmatch(r'[0-9+\-*/().% ]+', expression):
            return await ctx.reply('❌ اكتب عملية حسابية بسيطة فقط.')
        try:
            result = eval(expression, {'__builtins__': {}}, {})
            await ctx.reply(f'🧮 الناتج: **{result}**')
        except Exception:
            await ctx.reply('❌ العملية غير صالحة.')

    @commands.command(name='لون')
    async def color_info(self, ctx, color: str):
        value = color.strip().lstrip('#')
        if not re.fullmatch(r'[0-9a-fA-F]{6}', value):
            return await ctx.reply('❌ استخدم لون HEX مثل `#5865F2`.')
        rgb = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        await ctx.reply(f'🎨 **#{value.upper()}**\nRGB: `{rgb[0]}, {rgb[1]}, {rgb[2]}`')

    @commands.command(name='اختصار الرابط')
    async def shorten_url(self, ctx, url: str):
        if not url.startswith(('http://', 'https://')):
            return await ctx.reply('❌ أرسل رابطًا يبدأ بـ `https://` أو `http://`.')
        try:
            response = await asyncio.to_thread(requests.get, 'https://is.gd/create.php', params={'format': 'simple', 'url': url}, timeout=8)
            short = response.text.strip()
            if response.ok and short.startswith('http'):
                await ctx.reply(f'🔗 الرابط المختصر: {short}')
            else:
                await ctx.reply('❌ تعذر اختصار الرابط الآن.')
        except requests.RequestException:
            await ctx.reply('❌ خدمة اختصار الروابط غير متاحة الآن.')

    @commands.command(name='ترجمة')
    async def translate(self, ctx, target: str, *, text: str):
        langs = {'عربي': 'ar', 'انجليزي': 'en', 'إنجليزي': 'en', 'فرنسي': 'fr', 'اسباني': 'es', 'ألماني': 'de'}
        lang = langs.get(target.lower(), target.lower())
        if not re.fullmatch(r'[a-z]{2,5}', lang):
            return await ctx.reply('❌ استخدم لغة مثل `ar` أو `en`.')
        try:
            response = await asyncio.to_thread(requests.get, 'https://api.mymemory.translated.net/get', params={'q': text[:450], 'langpair': f'auto|{lang}'}, timeout=10)
            data = response.json()
            translated = data.get('responseData', {}).get('translatedText')
            if not translated:
                raise ValueError
            await ctx.reply(f'🌐 **الترجمة:**\n{translated[:1900]}')
        except (requests.RequestException, ValueError, KeyError):
            await ctx.reply('❌ تعذرت الترجمة الآن.')

    @commands.command(name='QR')
    async def qr(self, ctx, *, text: str):
        if len(text) > 1000:
            return await ctx.reply('❌ النص طويل جدًا.')
        url = 'https://api.qrserver.com/v1/create-qr-code/'
        try:
            response = await asyncio.to_thread(requests.get, url, params={'size': '300x300', 'data': text}, timeout=10)
            if not response.ok:
                raise requests.RequestException
            from io import BytesIO
            file = discord.File(BytesIO(response.content), filename='qr.png')
            await ctx.reply('🔳 QR Code:', file=file)
        except requests.RequestException:
            await ctx.reply('❌ تعذر إنشاء QR الآن.')

    @commands.command(name='وقت عالمي')
    async def world_time(self, ctx, city: str):
        zones = {
            'الرياض': 'Asia/Riyadh', 'جدة': 'Asia/Riyadh', 'دبي': 'Asia/Dubai',
            'لندن': 'Europe/London', 'نيويورك': 'America/New_York', 'طوكيو': 'Asia/Tokyo'
        }
        zone = zones.get(city, city)
        try:
            response = await asyncio.to_thread(requests.get, f'https://worldtimeapi.org/api/timezone/{zone}', timeout=8)
            data = response.json()
            dt = data.get('datetime', '')[:19].replace('T', ' ')
            await ctx.reply(f'🌍 الوقت في **{city}**: **{dt}**')
        except Exception:
            await ctx.reply('❌ المدينة غير مدعومة. جرّب: الرياض، دبي، لندن، نيويورك، طوكيو.')

    @commands.command(name='مساعدة الأمر')
    async def command_help(self, ctx, *, name: str):
        command = self.bot.get_command(name.replace('!', '').strip())
        if not command:
            return await ctx.reply('❌ ما لقيت هذا الأمر.')
        aliases = ', '.join(f'`!{a}`' for a in command.aliases) or 'لا يوجد'
        await ctx.reply(f'📖 **!{command.name}**\nالاختصارات: {aliases}\nالاستخدام: `{command.signature or "بدون متغيرات"}`')

    @app_commands.command(name='userinfo', description='Show member information')
    @app_commands.guild_only()
    async def userinfo_slash(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        embed = discord.Embed(title=f'👤 معلومات {member}', color=discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name='ID', value=str(member.id))
        embed.add_field(name='الحساب', value=discord.utils.format_dt(member.created_at, 'D'))
        embed.add_field(name='دخل السيرفر', value=discord.utils.format_dt(member.joined_at, 'D') if member.joined_at else 'غير معروف')
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='avatar', description='Show a member avatar')
    @app_commands.guild_only()
    async def avatar_slash(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        embed = discord.Embed(title=f'🖼️ صورة {member}', color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='serverinfo', description='Show server information')
    @app_commands.guild_only()
    async def serverinfo_slash(self, interaction):
        guild = interaction.guild
        await interaction.response.send_message(f'🏠 **{guild.name}**\n👥 {guild.member_count or 0} عضو\n💬 {len(guild.text_channels)} قناة نصية\n🔊 {len(guild.voice_channels)} قناة صوتية\n🏷️ {len(guild.roles)-1} رتبة')

    @app_commands.command(name='choose', description='Choose randomly from options separated by |')
    async def choose_slash(self, interaction: discord.Interaction, options: str):
        values = [x.strip() for x in options.split('|') if x.strip()]
        if len(values) < 2:
            return await interaction.response.send_message('❌ أرسل خيارين أو أكثر مفصولين بـ |', ephemeral=True)
        await interaction.response.send_message(f'🎯 الاختيار: **{random.choice(values)}**')

    @app_commands.command(name='coinflip', description='Flip a coin')
    async def coin_slash(self, interaction):
        await interaction.response.send_message(f'🪙 **{random.choice(["Heads", "Tails"])}**')

    @app_commands.command(name='roll', description='Roll a six-sided die')
    async def roll_slash(self, interaction):
        await interaction.response.send_message(f'🎲 **{random.randint(1, 6)}**')

    @app_commands.command(name='serverstats', description='Show server statistics')
    @app_commands.guild_only()
    async def serverstats_slash(self, interaction):
        guild = interaction.guild
        await interaction.response.send_message(f'📊 **{guild.name}**\n👥 {guild.member_count or 0}\n🤖 {sum(m.bot for m in guild.members)} بوت\n💬 {len(guild.text_channels)} نصية\n🔊 {len(guild.voice_channels)} صوتية\n🏷️ {len(guild.roles)-1} رتبة')

    @app_commands.command(name='luck', description='Show a random luck percentage')
    async def luck_slash(self, interaction):
        await interaction.response.send_message(f'🍀 حظك: **{random.randint(1, 100)}%**')

    @app_commands.command(name='number', description='Generate a random number')
    async def number_slash(self, interaction, minimum: int = 1, maximum: int = 100):
        if minimum > maximum or maximum - minimum > 1000000:
            return await interaction.response.send_message('❌ نطاق غير صالح.', ephemeral=True)
        await interaction.response.send_message(f'🎲 الرقم: **{random.randint(minimum, maximum)}**')

    @app_commands.command(name='age', description='Show account age in days')
    @app_commands.guild_only()
    async def age_slash(self, interaction, member: discord.Member | None = None):
        member = member or interaction.user
        days = (datetime.now(timezone.utc) - member.created_at).days
        await interaction.response.send_message(f'👤 عمر الحساب: **{days} يوم**')


async def setup(bot):
    await bot.add_cog(ExtraCommands(bot))
