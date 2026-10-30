import os
import re
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv()


def http_url(name: str, default: str = '', *, https_only: bool = False) -> str:
    value = os.getenv(name, default).strip().rstrip('/')
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in ({'https'} if https_only else {'http', 'https'})
                 and parsed.hostname and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment
                 and not re.search(r'[\s\\]', value))
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f'{name} must be a valid service URL without credentials, query or fragment')
    return value


def positive_timeout(name: str, default: str = '8') -> float:
    value = float(os.getenv(name, default))
    if not 0 < value <= 120:
        raise ValueError(f'{name} must be greater than zero and at most 120 seconds')
    return value


BOT_TOKEN = os.getenv('BOT_TOKEN')

if BOT_TOKEN is not None:
    BOT_TOKEN = BOT_TOKEN.strip() or None

HOST = os.getenv('FLASK_HOST', '0.0.0.0')
PORT = int(os.getenv('FLASK_PORT', 8000))
DEBUG = os.getenv('DEBUG', 'False').strip().lower() in {'1', 'true', 'yes', 'on'}

JITSI_DOMAIN = os.getenv('JITSI_DOMAIN', 'meet.jit.si').strip()
if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::[0-9]{1,5})?', JITSI_DOMAIN):
    raise ValueError('JITSI_DOMAIN must be a hostname with an optional port, without a URL scheme')
if urlsplit('https://' + JITSI_DOMAIN).port is not None:
    if not 1 <= urlsplit('https://' + JITSI_DOMAIN).port <= 65535:
        raise ValueError('JITSI_DOMAIN port must be between 1 and 65535')

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///app.db')

BOT_USERNAME = os.getenv('BOT_USERNAME', '').strip().lstrip('@') or None
ADMIN = int(os.getenv('ADMIN', '0') or '0')
BOT_LINK = f'https://t.me/{BOT_USERNAME}' if BOT_USERNAME else ''
BOT_INVITE_LINK = (
    f'https://t.me/share/url?url={BOT_LINK}'
    '&text=Давай созвонимся здесь 👇📞'
    if BOT_USERNAME else ''
)

DOMAIN = http_url('DOMAIN', 'http://127.0.0.1:8000')

# Split deployment. ``direct`` keeps the current monolith behavior; ``remote``
# makes the Telegram bot use the private RF backend API instead of PostgreSQL.
DATA_ACCESS_MODE = os.getenv('DATA_ACCESS_MODE', 'direct').strip().lower()
if DATA_ACCESS_MODE not in {'direct', 'remote', 'none'}:
    raise ValueError('DATA_ACCESS_MODE must be direct, remote, or none')
INTERNAL_API_URL = http_url('INTERNAL_API_URL', https_only=True)
INTERNAL_API_TOKEN = os.getenv('INTERNAL_API_TOKEN', '').strip()
INTERNAL_API_TIMEOUT = positive_timeout('INTERNAL_API_TIMEOUT')
INTERNAL_API_VERIFY_TLS = os.getenv(
    'INTERNAL_API_VERIFY_TLS', 'true'
).strip().lower() in {'1', 'true', 'yes', 'on'}

# Telegram Gateway is hosted with the bot outside Russia. The RF web backend
# uses it for Telegram API calls and therefore does not need BOT_TOKEN.
TELEGRAM_GATEWAY_URL = http_url('TELEGRAM_GATEWAY_URL', https_only=True)
TELEGRAM_GATEWAY_TOKEN = os.getenv('TELEGRAM_GATEWAY_TOKEN', '').strip()
TELEGRAM_GATEWAY_TIMEOUT = positive_timeout('TELEGRAM_GATEWAY_TIMEOUT')

# Remote mutation operations require Redis; without it only reads are available.
REDIS_URL = os.getenv('REDIS_URL', '').strip()

# Lightweight service monitoring. The app reads host-visible /proc metrics and
# performs bounded health probes without mounting the privileged Docker socket.
SYSTEM_METRICS_INTERVAL_SECONDS = max(
    60,
    int(os.getenv('SYSTEM_METRICS_INTERVAL_SECONDS', '300')),
)
RF_WEB_HEALTH_URL = os.getenv(
    'RF_WEB_HEALTH_URL',
    'http://echocall-app-web:8000/health/ready',
).strip()
FOREIGN_GATEWAY_HEALTH_URL = os.getenv(
    'FOREIGN_GATEWAY_HEALTH_URL',
    'http://telegram-gateway:8010/health/live',
).strip()
JITSI_HEALTH_URL = os.getenv(
    'JITSI_HEALTH_URL',
    f'https://{JITSI_DOMAIN}/config.js',
).strip()
TURN_HEALTH_HOST = os.getenv('TURN_HEALTH_HOST', 'turn.example.com').strip()
TURN_HEALTH_PORT = int(os.getenv('TURN_HEALTH_PORT', '3478'))
