import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, request, session


_RATE_BUCKETS = defaultdict(deque)
_RATE_LOCK = threading.RLock()
_RATE_LIMITS = {
    'login': (8, 60),
    'callback': (8, 60),
    'api': (30, 60),
    'logout': (10, 60),
    'health': (30, 60),
}
_MAX_RATE_BUCKETS = 10000


def client_ip():
    return request.remote_addr or 'unknown'


def rate_limit(bucket):
    limit, window = _RATE_LIMITS[bucket]
    key = (bucket, client_ip())
    now = time.monotonic()

    with _RATE_LOCK:
        events = _RATE_BUCKETS[key]
        while events and now - events[0] >= window:
            events.popleft()

        if len(events) >= limit:
            abort(429, description='تم تجاوز عدد المحاولات المسموح بها. حاول لاحقًا.')

        events.append(now)

        if len(_RATE_BUCKETS) > _MAX_RATE_BUCKETS:
            stale_before = now - 60
            stale = [
                k for k, q in _RATE_BUCKETS.items()
                if not q or q[-1] < stale_before
            ]
            for old_key in stale[:2000]:
                _RATE_BUCKETS.pop(old_key, None)


def csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return token


def validate_csrf():
    expected = session.get('csrf_token')
    supplied = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
    if not expected or not supplied or not secrets.compare_digest(str(supplied), str(expected)):
        abort(403, description='طلب غير صالح.')


def validate_same_origin():
    origin = request.headers.get('Origin')
    referer = request.headers.get('Referer')
    host = request.host_url.rstrip('/')
    if origin and origin.rstrip('/') != host:
        abort(403, description='مصدر الطلب غير مسموح.')
    if not origin and referer and not referer.startswith(host + '/'):
        abort(403, description='مصدر الطلب غير مسموح.')


def protected_post(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        rate_limit('api')
        validate_same_origin()
        validate_csrf()
        return fn(*args, **kwargs)
    return wrapper
