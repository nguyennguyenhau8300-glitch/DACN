import os
import re
from urllib.parse import urlsplit


def allowed_origins():
    configured = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:5173')
    return [origin.strip().rstrip('/') for origin in configured.split(',') if origin.strip()]


def loopback_web_origin():
    if os.getenv('PARKLY_LOCAL_WEB_ORIGINS') == '1':
        return r'https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?'
    return None


def accepts_websocket_origin(origin, host):
    if not origin or urlsplit(origin).netloc == host or origin.rstrip('/') in allowed_origins():
        return True
    local_pattern = loopback_web_origin()
    return local_pattern is not None and re.fullmatch(local_pattern, origin) is not None
