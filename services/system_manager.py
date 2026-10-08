import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from database import get_guild_data, update_guild_data

SYSTEM_EXTENSIONS = {
    "moderation": "cogs.moderation",
    "tickets": "cogs.tickets",
    "applications": "cogs.applications",
    "levels": "cogs.levels",
    "welcome": "cogs.welcome",
    "logs": "cogs.logs",
    "giveaways": "cogs.giveaways",
    "suggestions": "cogs.suggestions",
    "afk": "cogs.afk",
    "autoreply": "cogs.autoreply",
    "autorole": "cogs.autorole",
    "announcements": "cogs.announcements",
    "reminders": "cogs.reminders",
    "scheduler": "cogs.scheduler",
    "utility": "cogs.utility",
    "owner": "cogs.owner",
    "messaging": "cogs.messaging",
    "dashboard": "cogs.dashboard_commands",
    "extra_commands": "cogs.extra_commands",
    "new_commands": "cogs.new_commands",
    "ai_guard": "cogs.ai_guard",
    "event_logger": "cogs.event_logger",
    "protector_guard": "cogs.protector_guard",
}

SYSTEM_LABELS = {
    "moderation": "Moderation", "tickets": "Tickets", "applications": "Applications",
    "levels": "Levels / XP", "welcome": "Welcome", "logs": "Selective Logs",
    "giveaways": "Giveaways", "suggestions": "Suggestions", "afk": "AFK",
    "autoreply": "Auto Reply", "autorole": "Auto Role", "announcements": "Announcements",
    "reminders": "Reminders", "scheduler": "Scheduler", "utility": "Utility",
    "owner": "Owner", "messaging": "Messaging", "dashboard": "Dashboard Commands",
    "extra_commands": "Extra Commands", "new_commands": "New Commands",
    "ai_guard": "AI Guard", "event_logger": "Event Logger", "protector_guard": "Protector Guard",
}
DEFAULT_ENABLED = {name: name != "event_logger" for name in SYSTEM_EXTENSIONS}

def normalize_name(value):
    value = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"level":"levels","xp":"levels","auto_reply":"autoreply","auto_role":"autorole",
               "giveaway":"giveaways","suggestion":"suggestions","announcement":"announcements",
               "log":"logs","security":"protector_guard","protection":"protector_guard",
               "event_logs":"event_logger"}
    value = aliases.get(value, value)
    return value if value in SYSTEM_EXTENSIONS else None

def get_states(guild_id):
    data = get_guild_data(guild_id)
    stored = data.get("systems", {}) if isinstance(data, dict) else {}
    stored = stored if isinstance(stored, dict) else {}
    states = dict(DEFAULT_ENABLED)
    for name in SYSTEM_EXTENSIONS:
        if name in stored:
            states[name] = bool(stored[name])
    return states

def save_state(guild_id, name, enabled):
    states = get_states(guild_id)
    states[name] = bool(enabled)
    update_guild_data(guild_id, systems=states)
    return states

class SystemSelect(discord.ui.Select):
    def __init__(self, manager):
        self.manager = manager
        options = [discord.SelectOption(label=SYSTEM_LABELS[n], value=n,
                   emoji="🟢" if manager.is_enabled(n) else "🔴") for n in SYSTEM_EXTENSIONS]
        super().__init__(placeholder="Select a system to toggle", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction):
        if not await self.manager.authorized(interaction): return
        name = self.values[0]
        await self.manager.set_system(interaction, name, not self.manager.is_enabled(name))

class SystemControlView(discord.ui.View):
    def __init__(self, manager):
        super().__init__(timeout=180)
        self.manager = manager
        self.add_item(SystemSelect(manager))

    @discord.ui.button(label="Enable All", style=discord.ButtonStyle.success, row=1)
    async def enable_all(self, interaction, button):
        if not await self.manager.authorized(interaction): return
        for name in SYSTEM_EXTENSIONS: await self.manager.set_system(None, name, True)
        await self.manager.reply_status(interaction, "All systems enabled.")

    @discord.ui.button(label="Disable All", style=discord.ButtonStyle.danger, row=1)
    async def disable_all(self, interaction, button):
        if not await self.manager.authorized(interaction): return
        for name in SYSTEM_EXTENSIONS: await self.manager.set_system(None, name, False)
        await self.manager.reply_status(interaction, "All systems disabled.")

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, button):
        if not await self.manager.authorized(interaction): return
        await interaction.response.edit_message(embed=self.manager.status_embed(interaction.guild), view=SystemControlView(self.manager))

class SystemManager(commands.Cog):
    system_group = app_commands.Group(name="system", description="Enable, disable and inspect bot systems")

    def __init__(self, bot):
        self.bot = bot
        self._bootstrapped = False
        self._lock = asyncio.Lock()

    def primary_guild(self):
        gid = getattr(self.bot, "instance_guild_id", 0)
        return self.bot.get_guild(int(gid)) if gid else (self.bot.guilds[0] if self.bot.guilds else None)

    def is_enabled(self, name):
        guild = self.primary_guild()
        return get_states(guild.id).get(name, False) if guild else DEFAULT_ENABLED.get(name, False)

    async def authorized(self, interaction):
        if not interaction.guild:
            await interaction.response.send_message("This control is available inside a server only.", ephemeral=True); return False
        if interaction.user.id == getattr(self.bot, "owner_id", 0): return True
        perms = getattr(interaction.user, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild): return True
        await interaction.response.send_message("You need Administrator or Manage Server to change bot systems.", ephemeral=True)
        return False

    async def bootstrap(self):
        if self._bootstrapped: return
        guild = self.primary_guild()
        if not guild: return
        async with self._lock:
            if self._bootstrapped: return
            states = get_states(guild.id)
            for name, extension in SYSTEM_EXTENSIONS.items():
                if states.get(name, False): await self._load(name, extension)
            self._bootstrapped = True

    async def _load(self, name, extension):
        if extension in self.bot.extensions: return
        try: await self.bot.load_extension(extension)
        except commands.ExtensionNotFound: print(f"[{getattr(self.bot,'instance_name','VoidFlame')}] Missing {extension}; skipped.")
        except commands.ExtensionAlreadyLoaded: pass
        except Exception as exc: print(f"[{getattr(self.bot,'instance_name','VoidFlame')}] Failed loading {name}: {type(exc).__name__}: {exc}")

    async def _unload(self, name, extension):
        if extension not in self.bot.extensions: return
        try: await self.bot.unload_extension(extension)
        except commands.ExtensionNotLoaded: pass
        except Exception as exc: print(f"[{getattr(self.bot,'instance_name','VoidFlame')}] Failed unloading {name}: {type(exc).__name__}: {exc}")

    async def set_system(self, interaction, name, enabled):
        guild = interaction.guild if interaction else self.primary_guild()
        if not guild: return False
        extension = SYSTEM_EXTENSIONS[name]
        async with self._lock:
            save_state(guild.id, name, enabled)
            await (self._load(name, extension) if enabled else self._unload(name, extension))
        try: await self.bot.tree.sync(guild=guild)
        except Exception: pass
        if interaction: await self.reply_status(interaction, f"{SYSTEM_LABELS[name]} {'enabled' if enabled else 'disabled'}.")
        return True

    def status_embed(self, guild):
        states = get_states(guild.id) if guild else DEFAULT_ENABLED
        enabled = sum(1 for v in states.values() if v)
        embed = discord.Embed(title="VoidFlame • System Control", description=f"**{enabled}/{len(states)}** systems enabled.", color=discord.Color.blurple())
        for name, label in SYSTEM_LABELS.items(): embed.add_field(name=f"{'🟢' if states.get(name) else '🔴'} {label}", value="Enabled" if states.get(name) else "Disabled", inline=True)
        if guild: embed.set_footer(text=f"{guild.name} • Saved per bot instance")
        return embed

    async def reply_status(self, interaction, text):
        embed = self.status_embed(interaction.guild); embed.description = f"**{text}**\n\n" + (embed.description or "")
        if interaction.response.is_done(): await interaction.followup.send(embed=embed, ephemeral=True)
        else: await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="systems", description="Open the Discord system control panel")
    @app_commands.guild_only()
    async def systems_panel(self, interaction):
        if not await self.authorized(interaction): return
        await interaction.response.send_message(embed=self.status_embed(interaction.guild), view=SystemControlView(self), ephemeral=True)

    @system_group.command(name="status", description="Show system status")
    @app_commands.guild_only()
    async def system_status(self, interaction):
        if not await self.authorized(interaction): return
        await interaction.response.send_message(embed=self.status_embed(interaction.guild), ephemeral=True)

    @system_group.command(name="enable", description="Enable one system")
    @app_commands.guild_only()
    async def system_enable(self, interaction, system: str):
        if not await self.authorized(interaction): return
        name = normalize_name(system)
        if not name: return await interaction.response.send_message("Unknown system. Use /systems.", ephemeral=True)
        await self.set_system(interaction, name, True)

    @system_group.command(name="disable", description="Disable one system")
    @app_commands.guild_only()
    async def system_disable(self, interaction, system: str):
        if not await self.authorized(interaction): return
        name = normalize_name(system)
        if not name: return await interaction.response.send_message("Unknown system. Use /systems.", ephemeral=True)
        await self.set_system(interaction, name, False)

    @system_group.command(name="reload", description="Reload one system")
    @app_commands.guild_only()
    async def system_reload(self, interaction, system: str):
        if not await self.authorized(interaction): return
        name = normalize_name(system)
        if not name: return await interaction.response.send_message("Unknown system.", ephemeral=True)
        await self.set_system(interaction, name, False); await self.set_system(interaction, name, True)

    @commands.group(name="system", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def system_prefix(self, ctx): await ctx.reply(embed=self.status_embed(ctx.guild))

    @system_prefix.command(name="status")
    async def system_prefix_status(self, ctx): await ctx.reply(embed=self.status_embed(ctx.guild))

    @system_prefix.command(name="enable")
    async def system_prefix_enable(self, ctx, system: str):
        name = normalize_name(system)
        if not name: return await ctx.reply("❌ Unknown system. Use !system status.")
        await self.set_system_prefix(ctx, name, True)

    @system_prefix.command(name="disable")
    async def system_prefix_disable(self, ctx, system: str):
        name = normalize_name(system)
        if not name: return await ctx.reply("❌ Unknown system. Use !system status.")
        await self.set_system_prefix(ctx, name, False)

    async def set_system_prefix(self, ctx, name, enabled):
        extension = SYSTEM_EXTENSIONS[name]
        async with self._lock:
            save_state(ctx.guild.id, name, enabled)
            await (self._load(name, extension) if enabled else self._unload(name, extension))
        try: await self.bot.tree.sync(guild=ctx.guild)
        except Exception: pass
        await ctx.reply(f"✅ **{SYSTEM_LABELS[name]}** {'enabled' if enabled else 'disabled'}.")

    @commands.command(name="systems")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def systems_prefix(self, ctx): await ctx.reply(embed=self.status_embed(ctx.guild), view=SystemControlView(self))

async def setup(bot):
    cog = SystemManager(bot)
    await bot.add_cog(cog)
    bot.system_manager = cog
