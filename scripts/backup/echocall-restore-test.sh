#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=echocall-backup-lib.sh
source "$SCRIPT_DIR/echocall-backup-lib.sh"

require_command docker
require_command openssl
require_command restic
load_backup_config
select_backend "${1:-}"
acquire_backend_lock

umask 077
RESTORE_DIR="$(mktemp -d /var/tmp/echocall-restore.XXXXXX)"
TEST_CONTAINER="echocall-restore-test-${BACKEND}-$$"
TEST_PASSWORD="$(openssl rand -hex 24)"

cleanup() {
  docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$RESTORE_DIR"
}
trap cleanup EXIT INT TERM

run_restic check
run_restic restore latest --tag "$RESTIC_TAG" --target "$RESTORE_DIR"
DUMP_FILE="$RESTORE_DIR/echocall.dump"
[ -s "$DUMP_FILE" ] || fail "restored dump is missing or empty"

docker run -d --rm \
  --name "$TEST_CONTAINER" \
  --network none \
  -e POSTGRES_USER=restore_test \
  -e POSTGRES_PASSWORD="$TEST_PASSWORD" \
  -e POSTGRES_DB=restore_test \
  -v "$DUMP_FILE:/backup/echocall.dump:ro" \
  postgres:16-alpine >/dev/null

# The official image briefly exposes an initialization server and then restarts
# PostgreSQL. Waiting for pg_isready alone can succeed during that first phase.
INIT_COMPLETE=false
for _ in $(seq 1 60); do
  if docker logs "$TEST_CONTAINER" 2>&1 | grep -q 'PostgreSQL init process complete'; then
    INIT_COMPLETE=true
    break
  fi
  sleep 1
done
if [ "$INIT_COMPLETE" != true ]; then
  docker logs --tail 50 "$TEST_CONTAINER" >&2 || true
  fail "temporary PostgreSQL initialization timed out"
fi

READY=false
for _ in $(seq 1 60); do
  if docker exec "$TEST_CONTAINER" pg_isready -U restore_test -d restore_test >/dev/null 2>&1; then
    READY=true
    break
  fi
  sleep 1
done
if [ "$READY" != true ]; then
  docker logs --tail 50 "$TEST_CONTAINER" >&2 || true
  fail "temporary PostgreSQL did not become ready"
fi

docker exec "$TEST_CONTAINER" pg_restore \
  --exit-on-error \
  -U restore_test \
  -d restore_test \
  --no-owner \
  --no-acl \
  /backup/echocall.dump

TABLE_COUNT="$(docker exec "$TEST_CONTAINER" psql -U restore_test -d restore_test -Atqc \
  "select count(*) from pg_catalog.pg_tables where schemaname = 'public';")"
[ "$TABLE_COUNT" -gt 0 ] || fail "restore succeeded but no public tables were found"

echo "EchoCall restore test completed: backend=${BACKEND}, public_tables=${TABLE_COUNT}"
