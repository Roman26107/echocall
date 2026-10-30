#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo ".env not found. Copy .env.example to .env and fill values first." >&2
  exit 1
fi

docker compose config >/dev/null
docker compose up -d --build --remove-orphans
docker compose ps
