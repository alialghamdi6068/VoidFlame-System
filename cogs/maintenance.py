import discord
from discord import app_commands
from discord.ext import commands
from config import OWNER_ID
from database import get_global_setting, set_global_setting, init_db

# The maintenance module is imported by bot.py before main() calls init_db().
# Ensure its persisted global setting is readable during imports and tests.
init_db()

maintenance_mode = str(get_global_setting("maintenance_mode", "0")).lower() in {"1", "true", "yes", "on"}

def is_maintenance() -> bool:
    return maintenance_mode

class Maintenance(commands.Cog):
    """Global owner-only maintenance switch persisted in SQLite."""
    def __init__(self, bot):
        self.bot = bot

    async def _sync(self):
        try:
            await self.bot.tree.sync()
        except Exception as exc:
            print(f"[VoidFlame] Slash sync failed: {type(exc).__name__}: {exc}")

    async def _disable_all_systems(self):
        unloaded = []
        for name in list(getattr(self.bot, "system_extensions", [])):
            if name == "maintenance":
                continue
            if name in self.bot.extensions:
                try:
                    await self.bot.unload_extension(name)
                    unloaded.append(name)
                except Exception as exc:
                    print(f"[VoidFlame] Could not unload {name}: {type(exc).__name__}: {exc}")
        await self._sync()
        return unloaded

    async def _enable_all_systems(self):
        loaded = []
        for name in getattr(self.bot, "system_extensions", []):
            if name == "maintenance" or name in self.bot.extensions:
                continue
            try:
                await self.bot.load_extension(name)
                loaded.append(name)
            except Exception as exc:
                print(f"[VoidFlame] Could not reload {name}: {type(exc).__name__}: {exc}")
        await self._sync()
        return loaded

    @commands.command(name="صيانة")
    @commands.guild_only()
    async def maintenance_prefix(self, ctx):
        await self._toggle(ctx.author.id, lambda text: ctx.reply(text, mention_author=False))

    @app_commands.command(name="maintenance", description="Toggle global bot maintenance mode")
    async def maintenance_slash(self, interaction: discord.Interaction):
        await self._toggle(interaction.user.id, lambda text: interaction.response.send_message(text, ephemeral=True))

    async def _toggle(self, user_id, reply):
        global maintenance_mode
        if int(user_id) != OWNER_ID:
            await reply("❌ هذا الأمر للمالك فقط.")
            return
        maintenance_mode = not maintenance_mode
        set_global_setting("maintenance_mode", "1" if maintenance_mode else "0")
        if maintenance_mode:
            unloaded = await self._disable_all_systems()
            await reply(f"🔧 تم تفعيل الصيانة العامة. تم إيقاف {len(unloaded)} نظامًا في كل السيرفرات.\n👤 المالك الوحيد المسموح له: <@{OWNER_ID}>\nاستخدم !صيانة مرة ثانية لإرجاع كل الأنظمة.")
        else:
            loaded = await self._enable_all_systems()
            await reply(f"✅ تم إنهاء الصيانة العامة. تم تشغيل {len(loaded)} نظامًا من جديد في كل السيرفرات.")

async def setup(bot):
    await bot.add_cog(Maintenance(bot))
