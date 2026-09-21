from functools import wraps
import time
import requests
from flask import render_template, redirect, session, url_for, abort, request
from database import get_guild_data, connection
from config import DISCORD_CLIENT_ID
from web.auth import discord_token, managed_guild_ids

SYSTEMS = {
    'welcome': ('الترحيب', '👋'), 'tickets': ('التذاكر', '🎫'), 'applications': ('التقديمات', '📝'),
    'levels': ('المستويات', '📈'), 'autoreply': ('الردود التلقائية', '💬'), 'giveaways': ('القيفاواي', '🎉'),
    'suggestions': ('الاقتراحات', '💡'), 'logs': ('اللوق', '📋'), 'autorole': ('الرتبة التلقائية', '🏷️'),
    'announcements': ('الإعلانات', '📢'), 'reminders': ('التذكيرات', '⏰'), 'scheduler': ('الجدولة', '🗓️'),
    'afk': ('الغياب', '💤'), 'ai': ('الحماية الذكية', '🛡️'), 'warnings': ('التحذيرات', '⚠️'),
}


def logged_in(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user') or not discord_token(): return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper


def can_manage_guild(guild):
    user_id = (session.get('user') or {}).get('id')
    if not user_id or not guild: return False
    try: user_id = int(user_id)
    except (TypeError, ValueError): return False
    if guild.owner_id == user_id: return True
    if guild.id in managed_guild_ids(): return True
    member = guild.get_member(user_id)
    return bool(member and (member.guild_permissions.administrator or member.guild_permissions.manage_guild))


def manageable_guilds(bot):
    """Return every guild the logged-in user can manage, even when the bot is absent."""
    token = discord_token()
    if not token: return []
    try:
        response = requests.get('https://discord.com/api/v10/users/@me/guilds', headers={'Authorization': f'Bearer {token}'}, timeout=15)
        if response.status_code != 200: return []
        bot_ids = {guild.id for guild in bot.guilds}
        result = []
        for item in response.json():
            try:
                permissions = int(item.get('permissions_new', item.get('permissions', 0)))
                guild_id = int(item['id'])
            except (KeyError, TypeError, ValueError):
                continue
            if not (item.get('owner') is True or permissions & 0x20 or permissions & 0x8):
                continue
            result.append({
                'id': guild_id,
                'name': item.get('name', 'سيرفر بدون اسم'),
                'icon': item.get('icon'),
                'member_count': item.get('approximate_member_count', 0),
                'bot_installed': guild_id in bot_ids,
            })
        return result
    except (requests.RequestException, ValueError, TypeError):
        return []


def require_guild(guild_id, bot):
    # Flask serves requests from a separate thread while discord.py owns the
    # gateway cache. During startup/reconnect the cache can be empty briefly.
    # Wait for readiness first, then give the cache a bounded window to settle.
    ready_wait_deadline = time.time() + 15
    while not bot.is_ready() and time.time() < ready_wait_deadline:
        time.sleep(0.25)
    try:
        guild_id = int(guild_id)
    except (TypeError, ValueError):
        abort(404)
    guild = None
    for _ in range(40):
        try:
            guild = bot.get_guild(guild_id)
            if guild is not None:
                break
        except Exception:
            pass
        time.sleep(0.25)
    if not guild:
        # Keep the response accurate: this means the bot is genuinely absent
        # from its connected guild cache, not that the OAuth user lacks access.
        abort(404, description='البوت غير موجود في هذا السيرفر. أضف VoidFlame أولًا ثم افتح لوحة التحكم.')
    if not can_manage_guild(guild):
        abort(403)
    return guild


def register_dashboard(app, bot):
    @app.get('/')
    def home():
        if request.args.get('code') and request.args.get('state'):
            return redirect(url_for('callback', code=request.args['code'], state=request.args['state']))
        if session.get('user'): return redirect(url_for('servers'))
        return render_template('index.html')

    @app.get('/servers')
    @logged_in
    def servers():
        return render_template('servers.html', user=session['user'], guilds=manageable_guilds(bot), invite_url=(f'https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions=8&scope=bot%20applications.commands' if DISCORD_CLIENT_ID else ''))

    @app.get('/dashboard/<int:guild_id>')
    @logged_in
    def dashboard(guild_id):
        guild = require_guild(guild_id, bot)
        with connection() as conn:
            activity_count = conn.execute('SELECT COUNT(*) c FROM activity WHERE guild_id=?', (guild_id,)).fetchone()['c']
            member_levels = conn.execute('SELECT COUNT(*) c FROM levels WHERE guild_id=?', (guild_id,)).fetchone()['c']
        return render_template('dashboard.html', user=session['user'], guild=guild, settings=get_guild_data(guild_id), systems=SYSTEMS, activity_count=activity_count, member_levels=member_levels)

    @app.get('/dashboard/<int:guild_id>/settings')
    @logged_in
    def settings(guild_id): return redirect(url_for('system_page', guild_id=guild_id, system='welcome'))

    @app.get('/dashboard/<int:guild_id>/system/<system>')
    @logged_in
    def system_page(guild_id, system):
        guild = require_guild(guild_id, bot)
        if system not in SYSTEMS: abort(404)
        import discord
        channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
        return render_template('system.html', user=session['user'], guild=guild, settings=get_guild_data(guild_id), channels=channels, categories=list(guild.categories), roles=guild.roles, systems=SYSTEMS, current_system=system, system_title=SYSTEMS[system][0], system_icon=SYSTEMS[system][1])

    @app.get('/dashboard/<int:guild_id>/activity')
    @logged_in
    def activity(guild_id):
        guild = require_guild(guild_id, bot)
        with connection() as conn: rows = conn.execute('SELECT * FROM activity WHERE guild_id=? ORDER BY id DESC LIMIT 100', (guild_id,)).fetchall()
        return render_template('activity.html', user=session['user'], guild=guild, rows=rows)

    @app.get('/dashboard/<int:guild_id>/commands')
    @logged_in
    def commands_page(guild_id):
        guild = require_guild(guild_id, bot)
        return render_template('commands.html', user=session['user'], guild=guild)
