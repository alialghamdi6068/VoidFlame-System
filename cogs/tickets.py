import re
import discord
from discord.ext import commands
from database import get_guild_data, connection, log_activity


TICKET_FOOTER = 'VoidFlame • System'


class TicketPanelView(discord.ui.View):
    def __init__(self, cog, guild_id, buttons=None):
        super().__init__(timeout=None)
        configs = buttons or [{'label': '🎫 فتح تذكرة', 'style': 'success'}]
        for index, config in enumerate(configs[:5]):
            self.add_item(TicketPanelButton(cog, config, guild_id, index))


class TicketPanelButton(discord.ui.Button):
    def __init__(self, cog, config, guild_id, index):
        styles = {'primary': discord.ButtonStyle.primary, 'secondary': discord.ButtonStyle.secondary, 'success': discord.ButtonStyle.success, 'danger': discord.ButtonStyle.danger}
        label = str(config.get('label') or '🎫 فتح تذكرة')[:80]
        super().__init__(label=label, style=styles.get(config.get('style'), discord.ButtonStyle.success), custom_id=f'flame_tp:{guild_id}:{index}')
        self.cog = cog
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        await self.cog.create_ticket(interaction, self.config)


class MemberTicketModal(discord.ui.Modal):
    def __init__(self, cog, action):
        super().__init__(title='إضافة عضو للتذكرة' if action == 'add' else 'إزالة عضو من التذكرة')
        self.cog = cog
        self.action = action
        self.member_input = discord.ui.TextInput(label='منشن العضو أو ID', placeholder='مثال: 123456789012345678 أو @العضو', required=True, max_length=100)
        self.add_item(self.member_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message('❌ هذا الزر يعمل داخل التذكرة فقط.', ephemeral=True)
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ هذا الزر للإدارة فقط.', ephemeral=True)
        raw = str(self.member_input.value).strip()
        match = re.search(r'(\d{15,25})', raw)
        member_id = int(match.group(1)) if match else None
        member = interaction.guild.get_member(member_id) if member_id else None
        if not member:
            try:
                member = await interaction.guild.fetch_member(int(raw))
            except (ValueError, discord.NotFound, discord.HTTPException):
                member = None
        if not member:
            return await interaction.response.send_message('❌ لم أجد هذا العضو. أرسل الـ ID أو المنشن الصحيح.', ephemeral=True)
        if self.action == 'add':
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
            await interaction.response.send_message(f'✅ تمت إضافة {member.mention} إلى التذكرة.')
            log_activity(interaction.guild.id, 'ticket_add_member', str(member.id), interaction.user.id)
        else:
            await interaction.channel.set_permissions(member, overwrite=None)
            await interaction.response.send_message(f'✅ تمت إزالة {member.mention} من التذكرة.')
            log_activity(interaction.guild.id, 'ticket_remove_member', str(member.id), interaction.user.id)


class TicketView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label='استلام', style=discord.ButtonStyle.primary, emoji='📥', custom_id='flame_ticket_claim')
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ هذا الزر للإدارة فقط.', ephemeral=True)
        await interaction.response.send_message(f'📥 تم استلام التذكرة بواسطة {interaction.user.mention}.')
        log_activity(interaction.guild.id, 'ticket_claim', str(interaction.channel), interaction.user.id)

    @discord.ui.button(label='إضافة عضو', style=discord.ButtonStyle.success, emoji='➕', custom_id='flame_ticket_add_member')
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ هذا الزر للإدارة فقط.', ephemeral=True)
        await interaction.response.send_modal(MemberTicketModal(self.cog, 'add'))

    @discord.ui.button(label='إزالة عضو', style=discord.ButtonStyle.secondary, emoji='➖', custom_id='flame_ticket_remove_member')
    async def remove_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ هذا الزر للإدارة فقط.', ephemeral=True)
        await interaction.response.send_modal(MemberTicketModal(self.cog, 'remove'))

    @discord.ui.button(label='إغلاق', style=discord.ButtonStyle.danger, emoji='🔒', custom_id='flame_ticket_close')
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket(interaction)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def replace_variables(self, text, guild, user, ticket_id, category=None, support_role=None):
        return (
            str(text)
            .replace('{member}', user.mention)
            .replace('{username}', user.display_name)
            .replace('{server}', guild.name)
            .replace('{ticket}', f'#{ticket_id:04d}')
            .replace('{category}', category.name if isinstance(category, discord.CategoryChannel) else 'بدون قسم')
            .replace('{support}', support_role.mention if support_role else 'فريق الدعم')
        )

    def ticket_overwrites(self, guild, user, support_role_id=None):
        settings = get_guild_data(guild.id)
        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False), user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)}
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True, read_message_history=True)
        role_id = support_role_id or settings.get('ticket_support_role_id')
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        return overwrites

    async def write_ticket_log(self, guild, text):
        logs = self.bot.get_cog("Logs")
        if logs:
            await logs.send_log(guild, "Ticket Action", text, color=discord.Color.blurple())

    async def create_ticket(self, interaction, button_config=None):
        guild, user = interaction.guild, interaction.user
        if not guild:
            return await interaction.response.send_message('❌ هذا الزر يعمل داخل السيرفر فقط.', ephemeral=True)
        settings = get_guild_data(guild.id)
        if settings.get('tickets_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام التذاكر متوقف حاليًا.', ephemeral=True)
        button_config = button_config or {}
        category_id = button_config.get('category_id') or settings.get('ticket_category_id')
        support_role_id = button_config.get('support_role_id') or settings.get('ticket_support_role_id')
        category = guild.get_channel(int(category_id)) if category_id else None
        category = category if isinstance(category, discord.CategoryChannel) else None
        support_role = guild.get_role(int(support_role_id)) if support_role_id else None
        existing = discord.utils.find(lambda c: c.topic == f'flame-ticket-user:{user.id}', guild.text_channels)
        if existing:
            return await interaction.response.send_message(f'❌ عندك تذكرة مفتوحة بالفعل: {existing.mention}', ephemeral=True)
        try:
            channel = await guild.create_text_channel(f'ticket-pending-{user.id}', category=category, overwrites=self.ticket_overwrites(guild, user, support_role_id), topic=f'flame-ticket-user:{user.id}', reason='Flame ticket')
        except discord.Forbidden:
            return await interaction.response.send_message('❌ البوت لا يملك Manage Channels لإنشاء التذكرة.', ephemeral=True)
        except discord.HTTPException:
            return await interaction.response.send_message('❌ تعذر إنشاء التذكرة.', ephemeral=True)
        try:
            with connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                next_number = conn.execute(
                    'SELECT COALESCE(MAX(ticket_number), 0) + 1 FROM tickets WHERE guild_id=?',
                    (guild.id,)
                ).fetchone()[0]
                cursor = conn.execute(
                    'INSERT INTO tickets(guild_id,channel_id,user_id,ticket_number) VALUES(?,?,?,?)',
                    (guild.id, channel.id, user.id, next_number)
                )
                ticket_id = next_number
            await channel.edit(name=f'ticket-{ticket_id:04d}', reason='Set guild ticket number')
        except Exception:
            try:
                await channel.delete(reason='Ticket database creation failed')
            except discord.HTTPException:
                pass
            return await interaction.response.send_message('❌ تعذر حفظ التذكرة في قاعدة البيانات.', ephemeral=True)
        log_activity(guild.id, 'ticket_open', str(channel), user.id)
        await self.write_ticket_log(guild, f'🎫 تم فتح `{channel.name}` بواسطة {user.mention}.')
        title = str(button_config.get('title') or settings.get('ticket_embed_title') or f'🎫 تذكرة دعم #{ticket_id:04d}')[:256]
        description = str(button_config.get('description') or settings.get('ticket_embed_description') or 'أهلاً بك!\n\nاكتب تفاصيل طلبك هنا وسيقوم فريق الدعم بمساعدتك.')[:4000]
        title = self.replace_variables(title, guild, user, ticket_id, category, support_role)[:256]
        description = self.replace_variables(description, guild, user, ticket_id, category, support_role)[:4000]
        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        embed.set_footer(text=TICKET_FOOTER)
        await channel.send(content=user.mention, embed=embed, view=TicketView(self))
        await interaction.response.send_message(f'✅ تم فتح تذكرتك: {channel.mention}', ephemeral=True)

    async def close_ticket(self, source):
        if isinstance(source, discord.Interaction):
            guild, channel, user = source.guild, source.channel, source.user
            async def reply(text):
                return await source.response.send_message(text, ephemeral=True)
            async def confirm(text):
                return await source.response.send_message(text)
        else:
            guild, channel, user = source.guild, source.channel, source.author
            async def reply(text):
                return await source.reply(text)
            async def confirm(text):
                return await source.reply(text)
        if not guild or not channel:
            return
        with connection() as conn:
            row = conn.execute('SELECT * FROM tickets WHERE channel_id=? AND status="open"', (channel.id,)).fetchone()
            if not row:
                return await reply('❌ هذه التذكرة مغلقة أو غير موجودة.')
            if user.id != row['user_id'] and not user.guild_permissions.manage_channels:
                return await reply('❌ ما عندك صلاحية إغلاق هذه التذكرة.')
            conn.execute("UPDATE tickets SET status='closed', closed_at=CURRENT_TIMESTAMP WHERE channel_id=?", (channel.id,))
        await self.write_ticket_log(guild, f'🔒 تم إغلاق `{channel.name}` بواسطة {user.mention}.')
        log_activity(guild.id, 'ticket_close', str(channel), user.id)
        await confirm('🔒 سيتم إغلاق التذكرة.')
        await channel.delete(reason=f'Ticket closed by {user}')

    async def send_panel(self, ctx):
        settings = get_guild_data(ctx.guild.id)
        if settings.get('tickets_enabled', True) is False:
            return await ctx.reply('❌ نظام التذاكر متوقف حاليًا.')
        panel_id = settings.get('ticket_panel_channel_id')
        channel = ctx.guild.get_channel(int(panel_id)) if panel_id else None
        if not isinstance(channel, discord.TextChannel):
            return await ctx.reply('❌ حدد **روم لوحة التذاكر** من الموقع أولاً، ثم استخدم `!تكت`.')
        embed = discord.Embed(title=str(settings.get('ticket_panel_title') or '🎫 نظام التذاكر')[:256], description=str(settings.get('ticket_panel_description') or 'تحتاج مساعدة؟ اختر القسم المناسب من الأزرار بالأسفل.')[:4000], color=discord.Color.blurple())
        embed.set_footer(text=TICKET_FOOTER)
        buttons = settings.get('ticket_buttons') or [{'label': '🎫 فتح تذكرة', 'style': 'success'}]
        await channel.send(embed=embed, view=TicketPanelView(self, ctx.guild.id, buttons))
        await ctx.reply(f'✅ تم إرسال لوحة التذاكر في {channel.mention}.')

    @commands.command(name='تكت')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_panel(self, ctx):
        await self.send_panel(ctx)

    @commands.command(name='استلام')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def claim_prefix(self, ctx):
        await ctx.reply(f'📥 تم استلام التذكرة بواسطة {ctx.author.mention}.')
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Ticket Claim', f'Channel: {ctx.channel.mention}', actor=ctx.author)

    @commands.command(name='اغلاق')
    @commands.guild_only()
    async def close_prefix(self, ctx):
        await self.close_ticket(ctx)

    @commands.command(name='اضافة')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def add_prefix(self, ctx, member: discord.Member):
        await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await ctx.reply(f'✅ تمت إضافة {member.mention} للتذكرة.')
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Ticket Add Member', f'Channel: {ctx.channel.mention}\nMember: {member.mention}', actor=ctx.author)

    @commands.command(name='ازالة')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def remove_prefix(self, ctx, member: discord.Member):
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.reply(f'✅ تمت إزالة {member.mention} من التذكرة.')
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Ticket Remove Member', f'Channel: {ctx.channel.mention}\nMember: {member.mention}', actor=ctx.author)

    def register_persistent_views(self):
        if not getattr(self.bot, '_flame_ticket_base_view_added', False):
            self.bot.add_view(TicketView(self))
            self.bot._flame_ticket_base_view_added = True
        for guild in self.bot.guilds:
            settings = get_guild_data(guild.id)
            buttons = settings.get('ticket_buttons') or [{'label': '🎫 فتح تذكرة', 'style': 'success'}]
            self.bot.add_view(TicketPanelView(self, guild.id, buttons))

    def cog_unload(self):
        self.bot._flame_ticket_base_view_added = False


async def setup(bot):
    cog = Tickets(bot)
    await bot.add_cog(cog)
    cog.register_persistent_views()
