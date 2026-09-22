import re
import discord
from discord.ext import commands
from database import get_guild_data, connection, log_activity


TICKET_FOOTER = 'VoidFlame • System'


class TicketPanelView(discord.ui.View):
    def __init__(self, cog, guild_id, buttons=None):
        super().__init__(timeout=None)
        configs = buttons if isinstance(buttons, list) else []
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
        if not interaction.guild:
            return await interaction.response.send_message('❌ هذا الزر يعمل داخل السيرفر فقط.', ephemeral=True)
        if get_guild_data(interaction.guild.id).get('tickets_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام التذاكر متوقف حاليًا.', ephemeral=True)
        index = self.custom_id.rsplit(':', 1)[-1]
        if not self.cog._panel_config_exists(interaction.guild.id, index):
            return await interaction.response.send_message('❌ هذه اللوحة قديمة. أرسل لوحة التذاكر الجديدة من جديد.', ephemeral=True)
        config = self.cog.get_panel_button_config(interaction.guild.id, index)
        await self.cog.create_ticket(interaction, config)


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
        if not self.cog.is_ticket_channel(interaction.channel):
            return await interaction.response.send_message('❌ هذه القناة ليست تذكرة مفتوحة.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
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
            await interaction.followup.send(f'✅ تمت إضافة {member.mention} إلى التذكرة.', ephemeral=True)
            log_activity(interaction.guild.id, 'ticket_add_member', str(member.id), interaction.user.id)
        else:
            await interaction.channel.set_permissions(member, overwrite=None)
            await interaction.followup.send(f'✅ تمت إزالة {member.mention} من التذكرة.', ephemeral=True)
            log_activity(interaction.guild.id, 'ticket_remove_member', str(member.id), interaction.user.id)


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self, cog, channel_id, user_id):
        super().__init__(timeout=120)
        self.cog = cog
        self.channel_id = int(channel_id)
        self.user_id = int(user_id)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ هذا التأكيد خاص بالشخص الذي ضغط إغلاق.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='تأكيد الإغلاق', style=discord.ButtonStyle.danger, emoji='🔒')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.edit_original_response(content='❌ هذا الإجراء يعمل داخل السيرفر فقط.', view=None)
        if get_guild_data(interaction.guild.id).get('tickets_enabled', True) is False:
            return await interaction.edit_original_response(content='❌ نظام التذاكر متوقف حاليًا.', view=None)
        await interaction.response.defer(ephemeral=True)
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.edit_original_response(content='❌ لم تعد قناة التذكرة موجودة.', view=None)
        with connection() as conn:
            row = conn.execute('SELECT * FROM tickets WHERE channel_id=? AND status="open"', (self.channel_id,)).fetchone()
        if not row:
            return await interaction.edit_original_response(content='❌ هذه التذكرة مغلقة أو غير موجودة.', view=None)
        opener = interaction.guild.get_member(int(row['user_id']))
        if not opener:
            try:
                opener = await interaction.guild.fetch_member(int(row['user_id']))
            except (discord.NotFound, discord.HTTPException):
                opener = None
        try:
            if opener:
                await channel.set_permissions(opener, view_channel=False, send_messages=False, read_message_history=False)
            with connection() as conn:
                conn.execute("UPDATE tickets SET status='closed', closed_at=CURRENT_TIMESTAMP WHERE channel_id=? AND status='open'", (self.channel_id,))
            log_activity(interaction.guild.id, 'ticket_close', str(channel), interaction.user.id)
            try:
                await self.cog.write_ticket_log(interaction.guild, f'🔒 تم إغلاق التذكرة بواسطة {interaction.user.mention}.')
            except Exception:
                pass
            await interaction.edit_original_response(content='🔒 تم إغلاق التذكرة. اختر الإجراء المطلوب:', view=TicketCloseActionView(self.cog, self.channel_id, self.user_id, show_delete=interaction.user.guild_permissions.manage_channels))
            self.stop()
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.edit_original_response(content='❌ ما قدرت أقفل رؤية التذكرة عن صاحبها. تأكد من صلاحيات البوت.', view=None)

    @discord.ui.button(label='إلغاء', style=discord.ButtonStyle.secondary, emoji='✖️')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content='↩️ تم إلغاء إغلاق التذكرة.', view=None)
        self.stop()


class TicketCloseActionView(discord.ui.View):
    def __init__(self, cog, channel_id, user_id, show_delete=False):
        super().__init__(timeout=120)
        self.cog = cog
        self.channel_id = int(channel_id)
        self.user_id = int(user_id)
        self.show_delete = bool(show_delete)
        if not self.show_delete:
            # The delete action is an administration-only control.
            self.remove_item(self.delete)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message('❌ هذا الإجراء خاص بصاحب التذكرة أو الإدارة.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='حذف التذكرة', style=discord.ButtonStyle.danger, emoji='🗑️')
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ زر حذف التذكرة للإدارة فقط.', ephemeral=True)
        await self.cog.delete_closed_ticket(interaction, self.channel_id)
        self.stop()

    @discord.ui.button(label='فتح التذكرة', style=discord.ButtonStyle.success, emoji='🔓')
    async def reopen(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.reopen_ticket(interaction, self.channel_id)
        self.stop()


class TicketView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label='استلام', style=discord.ButtonStyle.primary, emoji='📥', custom_id='flame_ticket_claim')
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message('❌ هذا الزر يعمل داخل السيرفر فقط.', ephemeral=True)
        if get_guild_data(interaction.guild.id).get('tickets_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام التذاكر متوقف حاليًا.', ephemeral=True)
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ هذا الزر للإدارة فقط.', ephemeral=True)
        if not self.cog.is_ticket_channel(interaction.channel):
            return await interaction.response.send_message('❌ هذه القناة ليست تذكرة مفتوحة.', ephemeral=True)
        await interaction.response.send_message(f'📥 تم استلام التذكرة بواسطة {interaction.user.mention}.')
        log_activity(interaction.guild.id, 'ticket_claim', str(interaction.channel), interaction.user.id)

    @discord.ui.button(label='إضافة عضو', style=discord.ButtonStyle.success, emoji='➕', custom_id='flame_ticket_add_member')
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message('❌ هذا الزر يعمل داخل السيرفر فقط.', ephemeral=True)
        if get_guild_data(interaction.guild.id).get('tickets_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام التذاكر متوقف حاليًا.', ephemeral=True)
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ هذا الزر للإدارة فقط.', ephemeral=True)
        await interaction.response.send_modal(MemberTicketModal(self.cog, 'add'))

    @discord.ui.button(label='إزالة عضو', style=discord.ButtonStyle.secondary, emoji='➖', custom_id='flame_ticket_remove_member')
    async def remove_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message('❌ هذا الزر يعمل داخل السيرفر فقط.', ephemeral=True)
        if get_guild_data(interaction.guild.id).get('tickets_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام التذاكر متوقف حاليًا.', ephemeral=True)
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ هذا الزر للإدارة فقط.', ephemeral=True)
        await interaction.response.send_modal(MemberTicketModal(self.cog, 'remove'))

    @discord.ui.button(label='إغلاق', style=discord.ButtonStyle.danger, emoji='🔒', custom_id='flame_ticket_close')
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket(interaction)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._registered_panel_guilds = set()
        self._base_ticket_view = None
        self._panel_views = {}

    def get_panel_button_config(self, guild_id, index):
        try:
            index = int(index)
        except (TypeError, ValueError):
            return {}
        settings = get_guild_data(int(guild_id))
        buttons = settings.get('ticket_buttons') if 'ticket_buttons' in settings else [{'label': '🎫 فتح تذكرة', 'style': 'success'}]
        if not isinstance(buttons, list):
            buttons = []
        return buttons[index] if 0 <= index < len(buttons) else {}

    def get_ticket_row(self, channel_id, status=None):
        query = 'SELECT * FROM tickets WHERE channel_id=?'
        params = [int(channel_id)]
        if status:
            query += ' AND status=?'
            params.append(status)
        with connection() as conn:
            return conn.execute(query, params).fetchone()

    def is_ticket_channel(self, channel):
        return bool(channel and self.get_ticket_row(channel.id, 'open'))

    def _panel_config_exists(self, guild_id, index):
        try:
            index = int(index)
        except (TypeError, ValueError):
            return False
        settings = get_guild_data(int(guild_id))
        buttons = settings.get('ticket_buttons') if 'ticket_buttons' in settings else [{'label': '🎫 فتح تذكرة', 'style': 'success'}]
        if not isinstance(buttons, list):
            return False
        return 0 <= index < len(buttons) and isinstance(buttons[index], dict) and bool(str(buttons[index].get('label') or '').strip())

    def replace_variables(self, text, guild, user, ticket_id, category=None, support_role=None):
        return (
            str(text)
            .replace('{member}', user.mention)
            .replace('{username}', user.display_name)
            .replace('{server}', guild.name)
            .replace('{ticket}', f'#{ticket_id}')
            .replace('{number}', f'{ticket_id}')
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
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        if settings.get('tickets_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام التذاكر متوقف حاليًا.', ephemeral=True)
        button_config = button_config or {}
        category_id = button_config.get('category_id') or settings.get('ticket_category_id')
        support_role_id = button_config.get('support_role_id') or settings.get('ticket_support_role_id')
        category = guild.get_channel(int(category_id)) if category_id else None
        category = category if isinstance(category, discord.CategoryChannel) else None
        support_role = guild.get_role(int(support_role_id)) if support_role_id else None
        with connection() as conn:
            existing_row = conn.execute('SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status="open" LIMIT 1', (guild.id, user.id)).fetchone()
        if existing_row:
            existing = guild.get_channel(int(existing_row['channel_id']))
            if existing:
                return await interaction.followup.send(f'❌ عندك تذكرة مفتوحة بالفعل: {existing.mention}', ephemeral=True)
            with connection() as conn:
                conn.execute('UPDATE tickets SET status="closed", closed_at=CURRENT_TIMESTAMP WHERE channel_id=? AND status="open"', (int(existing_row['channel_id']),))
        try:
            channel = await guild.create_text_channel(f'ticket-pending-{user.id}', category=category, overwrites=self.ticket_overwrites(guild, user, support_role_id), reason='Flame ticket')
        except discord.Forbidden:
            return await interaction.followup.send('❌ البوت لا يملك Manage Channels لإنشاء التذكرة.', ephemeral=True)
        except discord.HTTPException:
            return await interaction.followup.send('❌ تعذر إنشاء التذكرة.', ephemeral=True)
        try:
            with connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                existing_row = conn.execute(
                    'SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status="open" LIMIT 1',
                    (guild.id, user.id)
                ).fetchone()
                if existing_row:
                    existing_channel = guild.get_channel(int(existing_row["channel_id"]))
                    if existing_channel:
                        raise RuntimeError(f'existing_ticket:{existing_channel.id}')
                    conn.execute(
                        'UPDATE tickets SET status="closed", closed_at=CURRENT_TIMESTAMP WHERE guild_id=? AND user_id=? AND status="open"',
                        (guild.id, user.id)
                    )
                next_number = conn.execute(
                    'SELECT COALESCE(MAX(ticket_number), 0) + 1 FROM tickets WHERE guild_id=?',
                    (guild.id,)
                ).fetchone()[0]
                try:
                    conn.execute(
                        'INSERT INTO tickets(guild_id,channel_id,user_id,ticket_number) VALUES(?,?,?,?)',
                        (guild.id, channel.id, user.id, next_number)
                    )
                except Exception:
                    raise
                ticket_id = next_number
            template = str(button_config.get('name_template') or settings.get('ticket_name_template') or '🎫・{number}')[:90].strip() or '🎫・{number}'
            channel_name = self.replace_variables(template, guild, user, ticket_id, category, support_role)
            channel_name = re.sub(r'[\\r\\n]+', ' ', channel_name).strip()[:100] or f'🎫・{ticket_id}'
            await channel.edit(name=channel_name, reason='Set guild ticket name')
        except RuntimeError as exc:
            try:
                await channel.delete(reason='Duplicate ticket prevented')
            except discord.HTTPException:
                pass
            if str(exc).startswith('existing_ticket:'):
                existing_id = str(exc).split(':', 1)[1]
                existing = guild.get_channel(int(existing_id))
                if existing:
                    return await interaction.followup.send(f'❌ عندك تذكرة مفتوحة بالفعل: {existing.mention}', ephemeral=True)
            return await interaction.followup.send('❌ تعذر حفظ التذكرة في قاعدة البيانات.', ephemeral=True)
        except Exception:
            try:
                await channel.delete(reason='Ticket database creation failed')
            except discord.HTTPException:
                pass
            return await interaction.followup.send('❌ تعذر حفظ التذكرة في قاعدة البيانات.', ephemeral=True)
        log_activity(guild.id, 'ticket_open', str(channel), user.id)
        await self.write_ticket_log(guild, f'🎫 تم فتح `{channel.name}` بواسطة {user.mention}.')
        title = str(button_config.get('title') or settings.get('ticket_embed_title') or f'🎫 تذكرة دعم #{ticket_id:04d}')[:256]
        description = str(button_config.get('description') or settings.get('ticket_embed_description') or 'أهلاً بك!\n\nاكتب تفاصيل طلبك هنا وسيقوم فريق الدعم بمساعدتك.')[:4000]
        title = self.replace_variables(title, guild, user, ticket_id, category, support_role)[:256]
        description = self.replace_variables(description, guild, user, ticket_id, category, support_role)[:4000]
        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        embed.set_footer(text=TICKET_FOOTER)
        try:
            await channel.send(content=user.mention, embed=embed, view=TicketView(self))
        except (discord.Forbidden, discord.HTTPException):
            with connection() as conn:
                conn.execute('DELETE FROM tickets WHERE channel_id=?', (channel.id,))
            try:
                await channel.delete(reason='Ticket message could not be sent')
            except discord.HTTPException:
                pass
            return await interaction.followup.send('❌ تم إنشاء القناة لكن تعذر إرسال رسالة التذكرة. تأكد من صلاحيات البوت.', ephemeral=True)
        try:
            await interaction.followup.send(f'✅ تم فتح تذكرتك: {channel.mention}', ephemeral=True)
        except discord.HTTPException:
            # The ticket is already valid; do not delete it just because the interaction expired.
            pass

    async def close_ticket(self, source):
        if isinstance(source, discord.Interaction):
            guild, channel, user = source.guild, source.channel, source.user
            async def reply(text):
                if source.response.is_done():
                    return await source.followup.send(text, ephemeral=True)
                return await source.response.send_message(text, ephemeral=True)
            async def show_confirm():
                return await source.response.send_message(
                    '⚠️ هل أنت متأكد أنك تريد إغلاق هذه التذكرة؟',
                    view=TicketCloseConfirmView(self, channel.id, user.id),
                    ephemeral=True
                )
        else:
            guild, channel, user = source.guild, source.channel, source.author
            async def reply(text):
                return await source.reply(text)
            async def show_confirm():
                return await source.reply(
                    '⚠️ هل أنت متأكد أنك تريد إغلاق هذه التذكرة؟',
                    view=TicketCloseConfirmView(self, channel.id, user.id)
                )

        if not guild or not channel:
            return
        if get_guild_data(guild.id).get('tickets_enabled', True) is False:
            if isinstance(source, discord.Interaction):
                return await reply('❌ نظام التذاكر متوقف حاليًا.')
            return await reply('❌ نظام التذاكر متوقف حاليًا.')
        with connection() as conn:
            row = conn.execute('SELECT * FROM tickets WHERE channel_id=? AND status="open"', (channel.id,)).fetchone()
        if not row:
            return await reply('❌ هذه التذكرة مغلقة أو غير موجودة.')
        if user.id != row['user_id'] and not user.guild_permissions.manage_channels:
            return await reply('❌ ما عندك صلاحية إغلاق هذه التذكرة.')
        return await show_confirm()

    async def delete_closed_ticket(self, interaction, channel_id):
        guild = interaction.guild
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        if guild and get_guild_data(guild.id).get('tickets_enabled', True) is False:
            return await interaction.edit_original_response(content='❌ نظام التذاكر متوقف حاليًا.', view=None)
        channel = guild.get_channel(int(channel_id)) if guild else None
        if not guild or not channel:
            return await interaction.edit_original_response(content='❌ لم تعد قناة التذكرة موجودة.', view=None)
        with connection() as conn:
            row = conn.execute('SELECT * FROM tickets WHERE channel_id=? AND status="closed"', (channel.id,)).fetchone()
        if not row:
            return await interaction.edit_original_response(content='❌ هذه التذكرة ليست مغلقة.', view=None)
        with connection() as conn:
            existing = conn.execute(
                'SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status="open" AND channel_id<>? LIMIT 1',
                (guild.id, int(row['user_id']), channel.id),
            ).fetchone()
        if existing:
            existing_channel = guild.get_channel(int(existing['channel_id']))
            target = existing_channel.mention if existing_channel else 'تذكرة مفتوحة أخرى'
            return await interaction.edit_original_response(
                content=f'❌ لا يمكن إعادة فتح هذه التذكرة لأن صاحبها لديه {target}. أغلق التذكرة المفتوحة أولًا.',
                view=None,
            )
        if interaction.user.id != row['user_id'] and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ ما عندك صلاحية حذف هذه التذكرة.', ephemeral=True)
        try:
            await interaction.edit_original_response(content='🗑️ جاري حذف التذكرة...', view=None)
            await channel.delete(reason=f'Ticket deleted by {interaction.user}')
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.followup.send('❌ ما قدرت أحذف قناة التذكرة. تأكد من صلاحية Manage Channels.', ephemeral=True)
        except Exception:
            return await interaction.followup.send('❌ حدث خطأ أثناء حذف التذكرة.', ephemeral=True)
        try:
            await self.write_ticket_log(guild, f'🗑️ تم حذف التذكرة بواسطة {interaction.user.mention}.')
            log_activity(guild.id, 'ticket_delete', str(channel), interaction.user.id)
        except Exception:
            pass

    async def reopen_ticket(self, interaction, channel_id):
        guild = interaction.guild
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        if guild and get_guild_data(guild.id).get('tickets_enabled', True) is False:
            return await interaction.edit_original_response(content='❌ نظام التذاكر متوقف حاليًا.', view=None)
        channel = guild.get_channel(int(channel_id)) if guild else None
        if not guild or not channel:
            return await interaction.edit_original_response(content='❌ لم تعد قناة التذكرة موجودة.', view=None)
        with connection() as conn:
            row = conn.execute('SELECT * FROM tickets WHERE channel_id=? AND status="closed"', (channel.id,)).fetchone()
        if not row:
            return await interaction.edit_original_response(content='❌ هذه التذكرة ليست مغلقة.', view=None)
        if interaction.user.id != row['user_id'] and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message('❌ ما عندك صلاحية فتح هذه التذكرة.', ephemeral=True)
        opener = guild.get_member(int(row['user_id']))
        if not opener:
            try:
                opener = await guild.fetch_member(int(row['user_id']))
            except (discord.NotFound, discord.HTTPException):
                opener = None
        if not opener:
            return await interaction.edit_original_response(content='❌ صاحب التذكرة لم يعد موجودًا في السيرفر، لذلك لا يمكن فتحها له.', view=None)
        try:
            await channel.set_permissions(opener, view_channel=True, send_messages=True, read_message_history=True)
            with connection() as conn:
                conn.execute("UPDATE tickets SET status='open', closed_at=NULL WHERE channel_id=? AND status='closed'", (channel.id,))
            log_activity(guild.id, 'ticket_reopen', str(channel), interaction.user.id)
            try:
                await self.write_ticket_log(guild, f'🔓 تم إعادة فتح التذكرة بواسطة {interaction.user.mention}.')
            except Exception:
                pass
            await interaction.edit_original_response(content='🔓 تم فتح التذكرة. صاحب التذكرة يستطيع رؤيتها الآن.', view=None)
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.edit_original_response(content='❌ ما قدرت أرجع صلاحية صاحب التذكرة. تأكد من صلاحيات البوت.', view=None)
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
        buttons = settings.get('ticket_buttons') if 'ticket_buttons' in settings else [{'label': '🎫 فتح تذكرة', 'style': 'success'}]
        if not isinstance(buttons, list):
            buttons = []
        if not buttons:
            return await ctx.reply('❌ أضف زرًا واحدًا على الأقل من لوحة التحكم أولاً.')
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
        if get_guild_data(ctx.guild.id).get('tickets_enabled', True) is False:
            return await ctx.reply('❌ نظام التذاكر متوقف حاليًا.')
        if not self.is_ticket_channel(ctx.channel):
            return await ctx.reply('❌ هذا الأمر يعمل داخل تذكرة مفتوحة فقط.')
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
        if get_guild_data(ctx.guild.id).get('tickets_enabled', True) is False:
            return await ctx.reply('❌ نظام التذاكر متوقف حاليًا.')
        if not self.is_ticket_channel(ctx.channel):
            return await ctx.reply('❌ هذا الأمر يعمل داخل تذكرة مفتوحة فقط.')
        await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await ctx.reply(f'✅ تمت إضافة {member.mention} للتذكرة.')
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Ticket Add Member', f'Channel: {ctx.channel.mention}\nMember: {member.mention}', actor=ctx.author)

    @commands.command(name='ازالة')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def remove_prefix(self, ctx, member: discord.Member):
        if get_guild_data(ctx.guild.id).get('tickets_enabled', True) is False:
            return await ctx.reply('❌ نظام التذاكر متوقف حاليًا.')
        if not self.is_ticket_channel(ctx.channel):
            return await ctx.reply('❌ هذا الأمر يعمل داخل تذكرة مفتوحة فقط.')
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.reply(f'✅ تمت إزالة {member.mention} من التذكرة.')
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Ticket Remove Member', f'Channel: {ctx.channel.mention}\nMember: {member.mention}', actor=ctx.author)

    def register_persistent_views(self):
        if self._base_ticket_view is None:
            self._base_ticket_view = TicketView(self)
            self.bot.add_view(self._base_ticket_view)
        for guild in self.bot.guilds:
            if guild.id in self._registered_panel_guilds:
                continue
            settings = get_guild_data(guild.id)
            buttons = settings.get('ticket_buttons') if 'ticket_buttons' in settings else [{'label': '🎫 فتح تذكرة', 'style': 'success'}]
            if not isinstance(buttons, list):
                buttons = []
            view = TicketPanelView(self, guild.id, buttons)
            self.bot.add_view(view)
            self._panel_views[guild.id] = view
            self._registered_panel_guilds.add(guild.id)

    def cog_unload(self):
        if self._base_ticket_view is not None:
            try:
                self.bot.remove_view(self._base_ticket_view)
            except Exception:
                pass
            self._base_ticket_view = None
        for view in list(self._panel_views.values()):
            try:
                self.bot.remove_view(view)
            except Exception:
                pass
        self._panel_views.clear()
        self._registered_panel_guilds.clear()


async def setup(bot):
    cog = Tickets(bot)
    await bot.add_cog(cog)
    cog.register_persistent_views()
