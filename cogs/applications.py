import discord
from discord.ext import commands
from database import get_guild_data, connection, log_activity

class ApplicationReviewView(discord.ui.View):
    def __init__(self,cog,application_id): super().__init__(timeout=86400); self.cog=cog; self.application_id=application_id
    async def review(self,interaction,status):
        if not interaction.user.guild_permissions.manage_guild: return await interaction.response.send_message('❌ هذا الزر للإدارة فقط.',ephemeral=True)
        with connection() as conn:
            row=conn.execute('SELECT * FROM applications WHERE id=? AND guild_id=?',(self.application_id,interaction.guild.id)).fetchone()
            if not row: return await interaction.response.send_message('❌ التقديم غير موجود.',ephemeral=True)
            if row['status']!='pending': return await interaction.response.send_message('⚠️ هذا التقديم تمت مراجعته مسبقاً.',ephemeral=True)
            conn.execute('UPDATE applications SET status=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=?',(status,self.application_id))
        label='تم قبول التقديم' if status=='accepted' else 'تم رفض التقديم'
        embed=interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color=discord.Color.green() if status=='accepted' else discord.Color.red(); embed.set_footer(text=f'الحالة: {label} بواسطة {interaction.user}')
        for item in self.children: item.disabled=True
        try:
            await interaction.message.edit(embed=embed,view=self)
        except discord.HTTPException:
            with connection() as conn:
                conn.execute('UPDATE applications SET status=?, reviewed_at=NULL WHERE id=? AND guild_id=?',('pending',self.application_id,interaction.guild.id))
            return await interaction.response.send_message('❌ تعذر تحديث رسالة التقديم. لم يتم اعتماد التغيير.',ephemeral=True)
        user=interaction.guild.get_member(row['user_id'])
        if user:
            try: await user.send(f'📨 بخصوص تقديمك في **{interaction.guild.name}**: **{label}**.')
            except discord.HTTPException: pass
        logs=self.cog.bot.get_cog('Logs')
        if logs: await logs.send_log(interaction.guild, 'Application Review', f'📋 التقديم **#{self.application_id}**: {label} بواسطة {interaction.user.mention}.', actor=interaction.user, color=discord.Color.green() if status=='accepted' else discord.Color.red())
        log_activity(interaction.guild.id,'application_review',f'#{self.application_id} -> {status}',interaction.user.id)
        await interaction.response.send_message(f'✅ {label}.',ephemeral=True)
    @discord.ui.button(label='قبول',style=discord.ButtonStyle.success)
    async def accept(self,interaction,button): await self.review(interaction,'accepted')
    @discord.ui.button(label='رفض',style=discord.ButtonStyle.danger)
    async def reject(self,interaction,button): await self.review(interaction,'rejected')

class ApplicationModal(discord.ui.Modal,title='نموذج التقديم'):
    answer=discord.ui.TextInput(label='اكتب تقديمك',style=discord.TextStyle.paragraph,min_length=10,max_length=2000,placeholder='اكتب التفاصيل هنا...')
    def __init__(self,cog): super().__init__(); self.cog=cog
    async def on_submit(self,interaction):
        guild=interaction.guild
        if not guild:
            return await interaction.response.send_message('❌ هذا النموذج يعمل داخل السيرفر فقط.',ephemeral=True)
        settings=get_guild_data(guild.id)
        if settings.get('applications_enabled', True) is False:
            return await interaction.response.send_message('❌ نظام التقديمات متوقف حاليًا.',ephemeral=True)
        channel=guild.get_channel(int(settings['applications_channel_id'])) if settings.get('applications_channel_id') else None
        if not isinstance(channel,discord.TextChannel): return await interaction.response.send_message('❌ الإدارة لم تحدد روم التقديمات من الداشبورد.',ephemeral=True)
        with connection() as conn:
            cur=conn.execute('INSERT INTO applications(guild_id,user_id,content) VALUES(?,?,?)',(guild.id,interaction.user.id,str(self.answer))); application_id=cur.lastrowid
        embed=discord.Embed(title=f'📨 تقديم جديد #{application_id}',description=str(self.answer),color=discord.Color.blurple()); embed.add_field(name='المتقدم',value=interaction.user.mention); embed.set_footer(text='الحالة: قيد المراجعة')
        try:
            await channel.send(embed=embed,view=ApplicationReviewView(self.cog,application_id))
        except discord.HTTPException:
            with connection() as conn:
                conn.execute('DELETE FROM applications WHERE id=? AND guild_id=?',(application_id,guild.id))
            return await interaction.response.send_message('❌ تعذر إرسال التقديم للإدارة. حاول مرة أخرى.',ephemeral=True)
        log_activity(guild.id,'application_submit',f'#{application_id}',interaction.user.id)
        logs=self.cog.bot.get_cog('Logs')
        if logs: await logs.send_log(guild, 'Application Submit', f'#{application_id} by {interaction.user.mention}', actor=interaction.user)
        await interaction.response.send_message('✅ تم ارسال تقديمك يرجى انتظار رد الإدارة.',ephemeral=True)

class Applications(commands.Cog):
    def __init__(self,bot): self.bot=bot
    @commands.command(name='تقديم')
    @commands.guild_only()
    async def application_prefix(self,ctx):
        if get_guild_data(ctx.guild.id).get('applications_enabled', True) is False:
            return await ctx.reply('❌ نظام التقديمات متوقف حاليًا.')
        view=discord.ui.View(timeout=300); button=discord.ui.Button(label='فتح التقديم',style=discord.ButtonStyle.success,emoji='📝')
        async def callback(interaction): await interaction.response.send_modal(ApplicationModal(self))
        button.callback=callback; view.add_item(button); await ctx.reply('📝 اضغط الزر لفتح نموذج التقديم.',view=view)
    @commands.command(name='تقديمات')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def set_channel(self,ctx,channel:discord.TextChannel):
        from database import update_guild_data; update_guild_data(ctx.guild.id,applications_channel_id=channel.id); await ctx.reply(f'✅ تم تحديد روم التقديمات: {channel.mention}.')
    @commands.command(name='تقديمات_لوق')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def set_log(self,ctx,channel:discord.TextChannel):
        from database import update_guild_data
        update_guild_data(ctx.guild.id,log_channel_id=channel.id)
        await ctx.reply(f'✅ تم تحديد روم اللوق الموحد: {channel.mention}. كل أنظمة البوت تستخدم هذا الروم.')
    @commands.command(name='قبول_تقديم')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def accept_prefix(self,ctx,application_id:int): await self.change_status(ctx,application_id,'accepted')
    @commands.command(name='رفض_تقديم')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reject_prefix(self,ctx,application_id:int): await self.change_status(ctx,application_id,'rejected')
    async def change_status(self,ctx,application_id,status):
        with connection() as conn:
            row=conn.execute('SELECT * FROM applications WHERE id=? AND guild_id=?',(application_id,ctx.guild.id)).fetchone()
            if not row: return await ctx.reply('❌ التقديم غير موجود.')
            conn.execute('UPDATE applications SET status=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?',(status,application_id))
        label='مقبول' if status=='accepted' else 'مرفوض'; user=ctx.guild.get_member(row['user_id'])
        if user:
            try: await user.send(f'📨 تقديمك في **{ctx.guild.name}** أصبح: **{label}**.')
            except discord.HTTPException: pass
        await ctx.reply(f'✅ تم تحديث التقديم #{application_id} إلى **{label}**.')
        logs=self.bot.get_cog('Logs')
        if logs: await logs.send_log(ctx.guild, 'Application Review', f'#{application_id} -> {label}', actor=ctx.author, color=discord.Color.green() if status=='accepted' else discord.Color.red())

async def setup(bot): await bot.add_cog(Applications(bot))
