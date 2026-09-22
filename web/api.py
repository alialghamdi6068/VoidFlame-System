import asyncio
import time
from flask import request, jsonify
from database import get_guild_data, update_guild_data, log_activity
from web.dashboard import logged_in, can_manage_guild
from web.security import protected_post
from services.settings_cache import settings_cache

ALLOWED_SETTINGS = {
    'welcome_channel_id', 'welcome_message', 'auto_role_id', 'log_channel_id',
    'ticket_category_id', 'ticket_panel_channel_id', 'ticket_panel_message_id', 'ticket_support_role_id',
    'ticket_panel_title', 'ticket_panel_description', 'ticket_name_template', 'ticket_topic',
    'applications_channel_id',
    'suggestions_channel_id',
    'level_channel_id', 'level_announce', 'levels_enabled', 'xp_min', 'xp_max', 'level_cooldown', 'log_rate_limit', 'spam_window_seconds', 'spam_message_limit', 'mention_limit', 'raid_window_seconds', 'raid_join_threshold', 'raid_timeout_minutes', 'mass_change_window_seconds', 'mass_change_threshold', 'protection_timeout_minutes', 'ai_min_score', 'ai_medium_score', 'ai_high_score', 'ai_timeout_minutes', 'ai_repeat_threshold', 'ai_action_cooldown_seconds', 'mass_change_action', 'mass_change_lockdown', 'webhook_protection', 'permission_change_protection', 'guild_update_protection', 'trusted_user_ids', 'trusted_role_ids', 'raid_action', 'protection_action', 'warn_dm_enabled', 'warn_dm_message', 'ai_enabled', 'protection_enabled', 'anti_raid_enabled', 'mass_change_protection', 'disabled_log_events', 'ai_ignore_channels', 'ai_ignore_roles', 'protection_ignore_channels', 'protection_ignore_roles',
    'giveaways_channel_id', 'autoreply_channel_id', 'announcements_channel_id',
    'scheduler_channel_id', 'reminder_channel_id', 'afk_channel_id'
}

SYSTEM_ENABLED_SETTINGS = {
    'welcome_enabled', 'tickets_enabled', 'applications_enabled', 'levels_enabled',
    'autoreply_enabled', 'giveaways_enabled', 'suggestions_enabled', 'logs_enabled',
    'autorole_enabled', 'announcements_enabled', 'reminders_enabled', 'scheduler_enabled',
    'afk_enabled'
}

INTEGER_SETTINGS = {
    'welcome_channel_id', 'auto_role_id', 'log_channel_id', 'ticket_category_id',
    'ticket_panel_channel_id', 'ticket_panel_message_id', 'ticket_support_role_id',
    'applications_channel_id',
    'suggestions_channel_id',
    'level_channel_id', 'giveaways_channel_id', 'autoreply_channel_id',
    'announcements_channel_id', 'scheduler_channel_id', 'reminder_channel_id', 'afk_channel_id'
}

NUMERIC_LIMITS = {
    'xp_min': (0, 100000), 'xp_max': (0, 100000), 'level_cooldown': (0, 86400), 'log_rate_limit': (5, 50),
    'spam_window_seconds': (2, 60), 'spam_message_limit': (3, 30), 'mention_limit': (3, 30),
    'raid_window_seconds': (5, 120), 'raid_join_threshold': (3, 50), 'raid_timeout_minutes': (1, 1440),
    'mass_change_window_seconds': (5, 120), 'mass_change_threshold': (3, 30), 'protection_timeout_minutes': (1, 40320),
    'ai_min_score': (0, 100), 'ai_medium_score': (1, 100), 'ai_high_score': (1, 100),
    'ai_timeout_minutes': (1, 40320), 'ai_repeat_threshold': (2, 12), 'ai_action_cooldown_seconds': (5, 3600),
}

NUMERIC_SETTINGS = {
    'xp_min', 'xp_max', 'level_cooldown', 'log_rate_limit', 'spam_window_seconds', 'spam_message_limit',
    'mention_limit', 'raid_window_seconds', 'raid_join_threshold', 'raid_timeout_minutes',
    'mass_change_window_seconds', 'mass_change_threshold', 'protection_timeout_minutes',
    'ai_min_score', 'ai_medium_score', 'ai_high_score', 'ai_timeout_minutes', 'ai_repeat_threshold',
    'ai_action_cooldown_seconds'
}

BOOLEAN_SETTINGS = {'level_announce', 'levels_enabled', 'warn_dm_enabled', 'ai_enabled', 'protection_enabled', 'anti_raid_enabled', 'mass_change_protection', 'mass_change_lockdown', 'webhook_protection', 'permission_change_protection', 'guild_update_protection'} | SYSTEM_ENABLED_SETTINGS
STRING_SETTINGS = {'mass_change_action', 'raid_action', 'protection_action'}


def _get_bot_guild(bot, guild_id):
    # The dashboard/API run outside discord.py's event-loop thread. A gateway
    # reconnect can temporarily leave the guild cache empty, so wait for the
    # client to become ready before declaring the guild unavailable.
    ready_wait_deadline = time.time() + 15
    while not bot.is_ready() and time.time() < ready_wait_deadline:
        time.sleep(0.25)
    try:
        guild_id = int(guild_id)
    except (TypeError, ValueError):
        return None
    # Flask runs in its own thread while discord.py fills its cache asynchronously.
    # A short retry prevents a false "bot is not connected" response during startup/reconnect.
    for _ in range(40):
        try:
            guild = bot.get_guild(guild_id)
            if guild is not None:
                return guild
        except Exception:
            pass
        time.sleep(0.25)
    return None


def _valid_resource(guild, key, value):
    if value in ('', None):
        return True
    try:
        value = int(value)
    except (TypeError, ValueError):
        return False
    if key == 'auto_role_id':
        return any(role.id == value and not role.is_default() for role in guild.roles)
    if key == 'ticket_category_id':
        return any(category.id == value for category in guild.categories)
    if key == 'ticket_support_role_id':
        return any(role.id == value and not role.is_default() for role in guild.roles)
    if key == 'ticket_panel_channel_id':
        return any(isinstance(channel, __import__('discord').TextChannel) and channel.id == value for channel in guild.channels)
    return any(channel.id == value for channel in guild.channels)


def _clean_ticket_buttons(value, guild):
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        label = str(item.get('label', '')).strip()[:80]
        if not label:
            continue
        button = {
            'label': label,
            'style': item.get('style') if item.get('style') in {'primary', 'secondary', 'success', 'danger'} else 'success'
        }
        for key in ('category_id', 'support_role_id'):
            if item.get(key):
                try:
                    resource_id = int(item[key])
                except (TypeError, ValueError):
                    continue
                if key == 'category_id' and any(c.id == resource_id for c in guild.categories):
                    button[key] = resource_id
                elif key == 'support_role_id' and any(r.id == resource_id and not r.is_default() for r in guild.roles):
                    button[key] = resource_id
        if item.get('title'):
            button['title'] = str(item['title'])[:256]
        if item.get('name_template'):
            button['name_template'] = str(item['name_template']).strip()[:100]
        if item.get('description'):
            button['description'] = str(item['description'])[:4000]
        if item.get('topic'):
            button['topic'] = str(item['topic'])[:1024]
        result.append(button)
    return result


def _clean_level_rewards(value, guild):
    if not isinstance(value, dict):
        return {}
    valid_roles = {role.id for role in guild.roles if not role.is_default()}
    rewards = {}
    for level, role_id in value.items():
        try:
            level_int = int(level)
            role_int = int(role_id)
        except (TypeError, ValueError):
            continue
        if 1 <= level_int <= 100 and role_int in valid_roles:
            rewards[str(level_int)] = role_int
    return rewards


def register_api(app, bot):
    @app.get('/api/guild/<int:guild_id>/settings')
    @logged_in
    def get_settings(guild_id):
        guild = _get_bot_guild(bot, guild_id)
        if guild is None:
            return jsonify({'ok': False, 'error': 'السيرفر غير موجود أو البوت غير متصل به.'}), 404
        if not can_manage_guild(guild):
            return jsonify({'ok': False, 'error': 'غير مصرح لك بإدارة هذا السيرفر.'}), 403
        return jsonify({'ok': True, 'settings': get_guild_data(guild_id)})

    @app.post('/api/guild/<int:guild_id>/settings')
    @logged_in
    @protected_post
    def save_settings(guild_id):
        guild = _get_bot_guild(bot, guild_id)
        if guild is None:
            return jsonify({'ok': False, 'error': 'السيرفر غير موجود أو البوت غير متصل به.'}), 404
        if not can_manage_guild(guild):
            return jsonify({'ok': False, 'error': 'غير مصرح لك بإدارة هذا السيرفر.'}), 403

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict) or len(payload) > 100:
            return jsonify({'ok': False, 'error': 'بيانات الطلب غير صحيحة.'}), 400
        data = get_guild_data(guild_id)

        action = payload.get('autoreply_action')
        if action in ('add', 'delete'):
            replies = dict(data.get('autoreplies', {}))
            trigger = str(payload.get('trigger', '')).strip()[:100]
            if not trigger:
                return jsonify({'ok': False, 'error': 'اكتب كلمة الرد.'}), 400
            if action == 'add':
                response = str(payload.get('response', '')).strip()[:2000]
                if not response:
                    return jsonify({'ok': False, 'error': 'اكتب الرد.'}), 400
                replies[trigger] = response
            else:
                replies.pop(trigger, None)
            data['autoreplies'] = replies

        if 'ticket_buttons' in payload:
            data['ticket_buttons'] = _clean_ticket_buttons(payload.get('ticket_buttons'), guild)
        if 'level_rewards' in payload:
            data['level_rewards'] = _clean_level_rewards(payload.get('level_rewards'), guild)

        for key in ALLOWED_SETTINGS | SYSTEM_ENABLED_SETTINGS:
            if key not in payload:
                continue
            value = payload[key]
            if key in INTEGER_SETTINGS:
                if value in ('', None):
                    value = None
                else:
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        return jsonify({'ok': False, 'error': f'القيمة غير صحيحة: {key}'}), 400
                    if not _valid_resource(guild, key, value):
                        return jsonify({'ok': False, 'error': 'العنصر المحدد غير موجود في هذا السيرفر.'}), 400
            elif key in NUMERIC_SETTINGS:
                if value in ('', None):
                    value = None
                else:
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        return jsonify({'ok': False, 'error': 'القيمة الرقمية غير صحيحة.'}), 400
                    low, high = NUMERIC_LIMITS[key]
                    if not low <= value <= high:
                        return jsonify({'ok': False, 'error': f'القيمة خارج النطاق المسموح: {key}'}), 400
            elif key in BOOLEAN_SETTINGS:
                if isinstance(value, bool):
                    value = value
                elif isinstance(value, (int, float)) and value in (0, 1):
                    value = bool(value)
                elif isinstance(value, str) and value.strip().lower() in {'true', '1', 'yes', 'on'}:
                    value = True
                elif isinstance(value, str) and value.strip().lower() in {'false', '0', 'no', 'off'}:
                    value = False
                else:
                    return jsonify({'ok': False, 'error': f'القيمة المنطقية غير صحيحة: {key}'}), 400
            elif key in STRING_SETTINGS:
                value = str(value).strip().lower()
                allowed = {'mass_change_action': {'log', 'kick'}, 'raid_action': {'timeout', 'log'}, 'protection_action': {'timeout', 'kick'}}[key]
                if value not in allowed:
                    return jsonify({'ok': False, 'error': f'القيمة غير صحيحة: {key}'}), 400
            elif key in {'ai_ignore_channels', 'ai_ignore_roles', 'disabled_log_events', 'protection_ignore_channels', 'protection_ignore_roles', 'trusted_user_ids', 'trusted_role_ids'}:
                if not isinstance(value, list):
                    return jsonify({'ok': False, 'error': f'القيمة غير صحيحة: {key}'}), 400
                value = [str(x)[:30] for x in value[:100]]
            elif key in {'welcome_message', 'ticket_panel_title', 'ticket_panel_description', 'ticket_name_template', 'warn_dm_message'}:
                value = str(value)
                limits = {'welcome_message': 2000, 'ticket_panel_title': 256, 'ticket_panel_description': 4000, 'ticket_name_template': 100, 'ticket_topic': 1024, 'warn_dm_message': 2000}
                value = value[:limits[key]]
            data[key] = value

        if 'warning_escalation' in payload:
            rules = payload.get('warning_escalation')
            if not isinstance(rules, dict):
                return jsonify({'ok': False, 'error': 'إعدادات تصعيد التحذيرات غير صحيحة.'}), 400
            clean = {}
            for level, rule in list(rules.items())[:10]:
                if str(level).isdigit() and isinstance(rule, dict):
                    action = rule.get('action', 'warning')
                    if action not in {'warning', 'timeout', 'kick'}:
                        continue
                    try:
                        minutes = int(rule.get('minutes', 10))
                    except (TypeError, ValueError):
                        minutes = 10
                    clean[str(max(1, min(10, int(level))))] = {
                        'action': action,
                        'minutes': max(1, min(40320, minutes))
                    }
            data['warning_escalation'] = clean
        if data.get('xp_min') is not None and data.get('xp_max') is not None and int(data['xp_min']) > int(data['xp_max']):
            return jsonify({'ok': False, 'error': 'الحد الأدنى للـXP لا يمكن أن يكون أكبر من الحد الأقصى.'}), 400
        score_values = [data.get('ai_min_score'), data.get('ai_medium_score'), data.get('ai_high_score')]
        if all(value is not None for value in score_values):
            minimum, medium, high = map(int, score_values)
            if not minimum <= medium <= high:
                return jsonify({'ok': False, 'error': 'ترتيب درجات الحماية الذكية غير صحيح.'}), 400
        data.pop('ticket_panel_footer', None)
        changed_keys = sorted({key for key in (ALLOWED_SETTINGS | SYSTEM_ENABLED_SETTINGS) if key in payload} | ({'ticket_buttons'} if 'ticket_buttons' in payload else set()) | ({'level_rewards'} if 'level_rewards' in payload else set()) | ({'warning_escalation'} if 'warning_escalation' in payload else set()) | ({'autoreplies'} if action in ('add', 'delete') else set()))
        update_guild_data(guild_id, **data)
        settings_cache.invalidate(guild_id)
        tickets_cog = bot.get_cog('Tickets')
        if tickets_cog and getattr(bot, 'loop', None) and bot.loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(tickets_cog.refresh_panel(guild), bot.loop)
                future.result(timeout=5)
            except Exception:
                # Dashboard saving must not fail because Discord is reconnecting
                # or the panel channel/message is temporarily unavailable.
                pass
        if changed_keys:
            log_activity(guild_id, 'dashboard_settings_update', ', '.join(changed_keys)[:500])
        return jsonify({'ok': True, 'settings': get_guild_data(guild_id)})
