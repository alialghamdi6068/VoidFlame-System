import secrets
import time
import requests
from flask import redirect, request, session, url_for, render_template
from config import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI
from web.security import rate_limit, csrf_token, validate_csrf, validate_same_origin

DISCORD_API = 'https://discord.com/api/v10'


def _managed_guilds_from_token(token):
    if not token:
        return set()
    try:
        response = requests.get(
            f'{DISCORD_API}/users/@me/guilds',
            headers={'Authorization': f'Bearer {token}'},
            timeout=15,
        )
        if response.status_code != 200:
            return set()
        allowed = set()
        for guild in response.json():
            try:
                permissions = int(guild.get('permissions_new', guild.get('permissions', 0)))
            except (TypeError, ValueError):
                permissions = 0
            if guild.get('owner') is True or permissions & 0x20 or permissions & 0x8:
                try:
                    allowed.add(int(guild['id']))
                except (KeyError, TypeError, ValueError):
                    continue
        return allowed
    except (requests.RequestException, ValueError, TypeError):
        return set()


def _refresh_access_token():
    oauth = session.get('oauth') or {}
    refresh_token = oauth.get('refresh_token')
    if not refresh_token or not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        return None
    try:
        response = requests.post(
            f'{DISCORD_API}/oauth2/token',
            data={
                'client_id': DISCORD_CLIENT_ID,
                'client_secret': DISCORD_CLIENT_SECRET,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
            },
            timeout=15,
        )
        if response.status_code != 200:
            return None
        token = response.json()
        access_token = token.get('access_token')
        if not isinstance(access_token, str) or not access_token:
            return None
        session['oauth'] = {
            'access_token': access_token,
            'refresh_token': token.get('refresh_token') or refresh_token,
            'expires_at': time.time() + int(token.get('expires_in', 604800)),
        }
        return access_token
    except (requests.RequestException, ValueError, TypeError):
        return None


def register_auth(app, bot):
    @app.get('/login')
    def login():
        rate_limit('login')
        if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET or not DISCORD_REDIRECT_URI:
            return render_template('error.html'), 500
        state = secrets.token_urlsafe(32)
        session.clear()
        session['oauth_state'] = state
        csrf_token()
        params = {
            'client_id': DISCORD_CLIENT_ID,
            'redirect_uri': DISCORD_REDIRECT_URI,
            'response_type': 'code',
            'scope': 'identify guilds',
            'state': state,
        }
        query = '&'.join(
            f'{k}={requests.utils.quote(str(v), safe="")}' for k, v in params.items()
        )
        return redirect(f'{DISCORD_API}/oauth2/authorize?{query}')

    @app.get('/callback')
    def callback():
        rate_limit('callback')
        state = request.args.get('state', '')
        expected = session.get('oauth_state')
        if not state or not expected or not secrets.compare_digest(state, str(expected)):
            return render_template('error.html'), 500
        code = request.args.get('code', '')
        if not code or len(code) > 2048:
            session.clear()
            return render_template('error.html'), 500
        try:
            response = requests.post(
                f'{DISCORD_API}/oauth2/token',
                data={
                    'client_id': DISCORD_CLIENT_ID,
                    'client_secret': DISCORD_CLIENT_SECRET,
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': DISCORD_REDIRECT_URI,
                },
                timeout=15,
            )
            if response.status_code != 200:
                session.clear()
                return render_template('error.html'), 500
            token = response.json()
            access_token = token.get('access_token')
            if not isinstance(access_token, str) or not access_token:
                session.clear()
                return render_template('error.html'), 500
            user_response = requests.get(
                f'{DISCORD_API}/users/@me',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=15,
            )
            if user_response.status_code != 200:
                session.clear()
                return render_template('error.html'), 500
            guilds = _managed_guilds_from_token(access_token)
            user = user_response.json()
            session.clear()
            session['oauth'] = {
                'access_token': access_token,
                'refresh_token': token.get('refresh_token'),
                'expires_at': time.time() + int(token.get('expires_in', 604800)),
            }
            session['user'] = {
                'id': str(user.get('id', '')),
                'username': user.get('username'),
                'global_name': user.get('global_name'),
                'avatar': user.get('avatar'),
            }
            session['managed_guild_ids'] = sorted(guilds)
            csrf_token()
            return redirect(url_for('servers'))
        except (requests.RequestException, ValueError, TypeError):
            session.clear()
            return render_template('error.html'), 500

    @app.post('/logout')
    def logout():
        rate_limit('logout')
        validate_same_origin()
        validate_csrf()
        session.clear()
        return redirect(url_for('home'))


def discord_token():
    oauth = session.get('oauth') or {}
    token = oauth.get('access_token')
    try:
        expires_at = float(oauth.get('expires_at', 0))
    except (TypeError, ValueError):
        expires_at = 0

    # Refresh slightly before expiry so the dashboard does not suddenly log out
    # during normal use. Discord refresh tokens are rotated, so persist the new one.
    if token and time.time() < expires_at - 60:
        return token

    refreshed = _refresh_access_token()
    if refreshed:
        return refreshed

    return None


def managed_guild_ids():
    """Return the user's current Discord-managed guilds.

    The session copy is only a fallback. Permissions can change after OAuth login,
    so authorization checks refresh the guild list from Discord when possible.
    """
    token = discord_token()
    if token:
        current = _managed_guilds_from_token(token)
        if current:
            session['managed_guild_ids'] = sorted(current)
            return current
    cached = session.get('managed_guild_ids')
    if isinstance(cached, list):
        result = set()
        for guild_id in cached:
            try:
                result.add(int(guild_id))
            except (TypeError, ValueError):
                continue
        return result
    return set()
