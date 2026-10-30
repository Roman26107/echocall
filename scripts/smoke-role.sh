#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:-}"

case "$ROLE" in
  rf)
    ENV_FILE=".env.rf"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    curl --connect-timeout 5 --max-time 10 -fsS "https://${APP_DOMAIN}/health/live" >/dev/null
    docker compose --env-file "$ENV_FILE" -f docker-compose.rf.yml exec -T internal-api \
      python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health/ready', timeout=3)"
    echo "RF web and internal API are alive."
    ;;
  foreign)
    ENV_FILE=".env.foreign"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    docker compose --env-file "$ENV_FILE" -f docker-compose.foreign.yml exec -T telegram-gateway \
      python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health/live', timeout=3)"
    echo "Foreign Telegram Gateway is alive."
    ;;
  *)
    echo "Usage: $0 {rf|foreign}" >&2
    exit 2
    ;;
esac
