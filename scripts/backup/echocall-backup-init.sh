#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=echocall-backup-lib.sh
source "$SCRIPT_DIR/echocall-backup-lib.sh"

require_command restic
load_backup_config
select_backend "${1:-}"
acquire_backend_lock

if run_restic cat config >/dev/null 2>&1; then
  echo "Restic repository '${BACKEND}' is already initialized."
else
  run_restic init
  echo "Restic repository '${BACKEND}' initialized."
fi
