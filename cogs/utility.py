import discord
from discord import app_commands
from discord.ext import commands
from config import BOT_NAME


def display_command_name(name: str) -> str:
    return name.replace('_', ' ')


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='اوامر', aliases=['مساعدة', 'help'])
    @commands.guild_only()
    async def all_commands(self, ctx):
        groups = {}
        for command in self.bot.commands:
            if command.hidden or command.name in {'اوامر', 'اوامر_الادارة', 'مساعدة', 'help'}:
                continue
            if getattr(command, 'checks', None):
                restricted = any(
                    getattr(check, '__name__', '') in {'predicate', 'is_owner'}
                    for check in command.checks
                )
                if restricted:
                    continue
            cog_name = command.cog_name or 'أخرى'
            groups.setdefault(cog_name, []).append(command)

        embed = discord.Embed(
            title=f'🔥 {BOT_NAME}  •  مركز الأوامر',
            description='كل الأوامر المتاحة لك، مرتبة حسب النظام. استخدم `!مساعدة الأمر <الأمر>` لمعرفة الاستخدام.',
            color=discord.Color.blurple()
        )
        for cog_name, commands_list in groups.items():
            names = [f'**`!{display_command_name(command.name)}`**' for command in commands_list]
            if names:
                embed.add_field(name=f'▸ {cog_name}  ·  {len(commands_list)}', value=' '.join(names)[:1024], inline=False)

        if not groups:
            embed.description = 'لا توجد أوامر عامة حاليًا.'
        embed.set_footer(text=f'{BOT_NAME} • {sum(len(v) for v in groups.values())} أمر • !مساعدة الأمر <الأمر> للتفاصيل')
        await ctx.reply(embed=embed)

    @commands.command(name='اوامر_الادارة')
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def admin_commands(self, ctx):
        groups = {}
        for command in self.bot.commands:
            if command.hidden or command.name in {'اوامر', 'اوامر_الادارة', 'مساعدة', 'help'}:
                continue
            if not getattr(command, 'checks', None):
                continue
            cog_name = command.cog_name or 'أخرى'
            groups.setdefault(cog_name, []).append(command)

        embed = discord.Embed(
            title=f'🛡️ {BOT_NAME}  •  مركز الإدارة',
            description='الأوامر الإدارية المتاحة حسب صلاحياتك. استخدم `!مساعدة الأمر <الأمر>` للتفاصيل.',
            color=discord.Color.red()
        )
        for cog_name, commands_list in groups.items():
            names = [f'`!{display_command_name(command.name)}`' for command in commands_list]
            if names:
                embed.add_field(name=f'📂 {cog_name}', value=' '.join(names)[:1024], inline=False)

        if not groups:
            embed.description = 'لا توجد أوامر إدارية حاليًا.'
        await ctx.reply(embed=embed)

    @app_commands.command(name='help', description='Show public commands')
    async def help_slash(self, interaction):
        groups = {}
        for command in self.bot.commands:
            if command.hidden:
                continue
            cog_name = command.cog_name or 'Other'
            groups.setdefault(cog_name, []).append(command.name)
        embed = discord.Embed(title=f'🔥 {BOT_NAME}  •  مركز الأوامر', description='كل الأوامر متاحة من هنا بشكل مرتب.', color=discord.Color.from_rgb(139, 92, 246))
        for cog_name, names in groups.items():
            display_names = [display_command_name(n) for n in names]
            embed.add_field(name=f'📂 {cog_name}', value=' '.join(f'`!{n}`' for n in display_names)[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name='بينج')
    async def ping(self, ctx):
        await ctx.reply(f'🏓 Pong! `{round(self.bot.latency * 1000)}ms`')

    @app_commands.command(name='ping', description='Show bot latency')
    async def ping_slash(self, interaction):
        await interaction.response.send_message(f'🏓 Pong! `{round(self.bot.latency * 1000)}ms`')


async def setup(bot):
    await bot.add_cog(Utility(bot))
