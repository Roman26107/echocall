#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=echocall-backup-lib.sh
source "$SCRIPT_DIR/echocall-backup-lib.sh"

require_command docker
require_command restic
load_backup_config
select_backend "${1:-}"
acquire_backend_lock

umask 077
install -d -m 700 "$STAGING_DIR" "$RESTIC_CACHE_DIR"
DUMP_FILE="$(mktemp "$STAGING_DIR/echocall.XXXXXX.dump")"
CONTAINER_DUMP="/tmp/echocall-backup-$RANDOM-$$.dump"

cleanup() {
  rm -f "$DUMP_FILE"
  docker exec "$POSTGRES_CONTAINER" rm -f "$CONTAINER_DUMP" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

[ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER" 2>/dev/null)" = "true" ] \
  || fail "PostgreSQL container is not running: $POSTGRES_CONTAINER"

docker exec "$POSTGRES_CONTAINER" sh -eu -c \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' \
  >"$DUMP_FILE"
[ -s "$DUMP_FILE" ] || fail "pg_dump produced an empty archive"

# Validate the archive with the same PostgreSQL tool version before uploading.
docker cp "$DUMP_FILE" "$POSTGRES_CONTAINER:$CONTAINER_DUMP" >/dev/null
docker exec "$POSTGRES_CONTAINER" pg_restore --list "$CONTAINER_DUMP" >/dev/null
docker exec "$POSTGRES_CONTAINER" rm -f "$CONTAINER_DUMP"

run_restic backup \
  --stdin \
  --stdin-filename echocall.dump \
  --tag "$RESTIC_TAG" \
  <"$DUMP_FILE"

run_restic forget \
  --tag "$RESTIC_TAG" \
  --keep-daily "${KEEP_DAILY:-7}" \
  --keep-weekly "${KEEP_WEEKLY:-4}" \
  --keep-monthly "${KEEP_MONTHLY:-6}" \
  --prune

echo "EchoCall PostgreSQL backup completed: backend=${BACKEND}"
