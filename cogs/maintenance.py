import discord
from discord import app_commands
from discord.ext import commands

OWNER_ID = 1293157778030071920
maintenance_mode = False


def is_maintenance() -> bool:
    return maintenance_mode


class Maintenance(commands.Cog):
    """Global maintenance switch. Only the bot owner can control it."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="صيانة")
    async def maintenance_prefix(self, ctx):
        await self._toggle(ctx.author.id, lambda text: ctx.reply(text, mention_author=False))

    @app_commands.command(name="maintenance", description="Toggle bot maintenance mode")
    async def maintenance_slash(self, interaction: discord.Interaction):
        async def reply(text):
            await interaction.response.send_message(text)

        await self._toggle(interaction.user.id, reply)

    async def _toggle(self, user_id, reply):
        global maintenance_mode

        if user_id != OWNER_ID:
            await reply("❌ لا يستطيع استخدام هذا الأمر إلا <@1293157778030071920>.")
            return

        maintenance_mode = not maintenance_mode

        if maintenance_mode:
            await reply("🔧 تم تفعيل وضع الصيانة. جميع أعمال وأنظمة البوت متوقفة مؤقتًا.")
        else:
            await reply("✅ تم إنهاء وضع الصيانة. جميع أعمال وأنظمة البوت تعمل الآن.")


async def setup(bot):
    await bot.add_cog(Maintenance(bot))
