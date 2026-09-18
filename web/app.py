from flask import Flask, Response, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from config import SESSION_SECRET
from web.security import csrf_token, rate_limit


def create_app(bot):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.secret_key = SESSION_SECRET
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=True,
        MAX_CONTENT_LENGTH=256 * 1024,
        PROPAGATE_EXCEPTIONS=False,
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.context_processor
    def inject_security():
        return {'csrf_token': csrf_token()}

    @app.before_request
    def request_guards():
        if request.path == '/health':
            rate_limit('health')
        if request.method == 'POST' and request.content_length and request.content_length > 256 * 1024:
            return ('الطلب كبير جدًا.', 413)

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://cdn.discordapp.com https://media.discordapp.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
        )
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        if session.get('user'):
            response.headers['Cache-Control'] = 'no-store, max-age=0'
            response.headers['Pragma'] = 'no-cache'
        return response

    from web.auth import register_auth
    from web.dashboard import register_dashboard
    from web.api import register_api

    register_auth(app, bot)
    register_dashboard(app, bot)
    register_api(app, bot)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'bot_ready': bot.is_ready()}

    @app.get('/robots.txt')
    def robots():
        return Response(
            'User-agent: *\n'
            'Allow: /\n'
            'Disallow: /dashboard/\n'
            'Disallow: /api/\n'
            'Disallow: /login\n'
            'Disallow: /callback\n'
            'Disallow: /logout\n'
            'Sitemap: /sitemap.xml\n',
            mimetype='text/plain',
        )

    @app.get('/sitemap.xml')
    def sitemap():
        root = request.url_root.rstrip('/')
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'<url><loc>{root}/</loc></url>'
            '</urlset>'
        )
        return Response(xml, mimetype='application/xml')

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('error.html'), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    @app.errorhandler(413)
    def too_large(error):
        return render_template('error.html'), 413

    @app.errorhandler(429)
    def too_many(error):
        return render_template('error.html'), 429

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html'), 500

    return app
