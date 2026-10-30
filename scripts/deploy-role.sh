#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:-}"

case "$ROLE" in
  rf)
    COMPOSE_FILE="docker-compose.rf.yml"
    ENV_FILE=".env.rf"
    BUILD_SERVICE="migrate"
    ;;
  foreign)
    COMPOSE_FILE="docker-compose.foreign.yml"
    ENV_FILE=".env.foreign"
    BUILD_SERVICE="telegram-gateway"
    ;;
  *)
    echo "Usage: $0 {rf|foreign}" >&2
    exit 2
    ;;
esac

cd "$(dirname "$0")/.."

if [ ! -f "$ENV_FILE" ]; then
  echo "$ENV_FILE not found; copy the matching .example and fill secrets." >&2
  exit 1
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/dev/null
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build "$BUILD_SERVICE"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-build --remove-orphans

# Nginx resolves Compose service names when its config is loaded. If web or
# internal-api was recreated with a new container IP, a still-running Nginx
# would keep the stale address and return 502 until it reloads.
if [ "$ROLE" = "rf" ]; then
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
    up -d --no-build --no-deps --force-recreate nginx
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
