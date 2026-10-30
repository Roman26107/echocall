import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

if BOT_TOKEN is not None:
    BOT_TOKEN = BOT_TOKEN.strip() or None

HOST = os.getenv('FLASK_HOST', '0.0.0.0')
PORT = int(os.getenv('FLASK_PORT', 8000))
DEBUG = os.getenv('DEBUG', 'False').strip().lower() in {'1', 'true', 'yes', 'on'}

JITSI_DOMAIN = os.getenv('JITSI_DOMAIN', 'meet.jit.si')

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///app.db')

BOT_USERNAME = os.getenv('BOT_USERNAME')
ADMIN = int(os.getenv('ADMIN', '0') or '0')
BOT_LINK = f'https://t.me/{BOT_USERNAME}' if BOT_USERNAME else ''
BOT_INVITE_LINK = (
    f'https://t.me/share/url?url={BOT_LINK}'
    '&text=Давай созвонимся здесь 👇📞'
    if BOT_USERNAME else ''
)

DOMAIN = os.getenv('DOMAIN', 'http://127.0.0.1:8000')

# Split deployment. ``direct`` keeps the current monolith behavior; ``remote``
# makes the Telegram bot use the private RF backend API instead of PostgreSQL.
DATA_ACCESS_MODE = os.getenv('DATA_ACCESS_MODE', 'direct').strip().lower()
INTERNAL_API_URL = os.getenv('INTERNAL_API_URL', '').strip().rstrip('/')
INTERNAL_API_TOKEN = os.getenv('INTERNAL_API_TOKEN', '').strip()
INTERNAL_API_TIMEOUT = float(os.getenv('INTERNAL_API_TIMEOUT', '8'))
INTERNAL_API_VERIFY_TLS = os.getenv(
    'INTERNAL_API_VERIFY_TLS', 'true'
).strip().lower() in {'1', 'true', 'yes', 'on'}

# Telegram Gateway is hosted with the bot outside Russia. The RF web backend
# uses it for Telegram API calls and therefore does not need BOT_TOKEN.
TELEGRAM_GATEWAY_URL = os.getenv('TELEGRAM_GATEWAY_URL', '').strip().rstrip('/')
TELEGRAM_GATEWAY_TOKEN = os.getenv('TELEGRAM_GATEWAY_TOKEN', '').strip()
TELEGRAM_GATEWAY_TIMEOUT = float(os.getenv('TELEGRAM_GATEWAY_TIMEOUT', '8'))

# Used by the RF internal API for mutation idempotency. Redis is recommended in
# split production; an empty value disables the cache for local development.
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
