#!/usr/bin/env bash

set -euo pipefail

CONFIG_FILE="${ECHOCALL_BACKUP_CONFIG:-/etc/echocall-backup/backup.env}"

fail() {
  echo "backup error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

assert_private_file() {
  local path="$1"
  local label="$2"
  local mode
  local owner

  [ -f "$path" ] && [ ! -L "$path" ] || fail "$label must be a regular non-symlink file: $path"
  [ -r "$path" ] || fail "$label is not readable: $path"
  owner="$(stat -c '%u' "$path")"
  [ "$owner" -eq 0 ] || fail "$label must be owned by root"
  mode="$(stat -c '%a' "$path")"
  (( (8#$mode & 077) == 0 )) || fail "$label must not be accessible by group/others"
}

load_backup_config() {
  assert_private_file "$CONFIG_FILE" "backup config"
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"

  : "${POSTGRES_CONTAINER:?POSTGRES_CONTAINER is required}"
  : "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE is required}"
  : "${RESTIC_CACHE_DIR:?RESTIC_CACHE_DIR is required}"
  : "${STAGING_DIR:?STAGING_DIR is required}"

  assert_private_file "$RESTIC_PASSWORD_FILE" "restic password file"
  export RESTIC_PASSWORD_FILE RESTIC_CACHE_DIR
}

select_backend() {
  BACKEND="${1:-}"
  RESTIC_EXTRA_ARGS=()

  case "$BACKEND" in
    foreign)
      : "${RESTIC_REPOSITORY_FOREIGN:?RESTIC_REPOSITORY_FOREIGN is required}"
      : "${SFTP_USER:?SFTP_USER is required}"
      : "${SFTP_HOST:?SFTP_HOST is required}"
      : "${SFTP_IDENTITY_FILE:?SFTP_IDENTITY_FILE is required}"
      : "${SFTP_KNOWN_HOSTS_FILE:?SFTP_KNOWN_HOSTS_FILE is required}"
      assert_private_file "$SFTP_IDENTITY_FILE" "SFTP identity file"
      assert_private_file "$SFTP_KNOWN_HOSTS_FILE" "SFTP known_hosts file"
      RESTIC_REPOSITORY="$RESTIC_REPOSITORY_FOREIGN"
      RESTIC_EXTRA_ARGS=(
        -o
        "sftp.command=ssh -i ${SFTP_IDENTITY_FILE} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${SFTP_KNOWN_HOSTS_FILE} ${SFTP_USER}@${SFTP_HOST} -s sftp"
      )
      ;;
    google)
      : "${RESTIC_REPOSITORY_GOOGLE:?RESTIC_REPOSITORY_GOOGLE is required}"
      : "${RCLONE_CONFIG:?RCLONE_CONFIG is required}"
      assert_private_file "$RCLONE_CONFIG" "rclone config"
      RESTIC_REPOSITORY="$RESTIC_REPOSITORY_GOOGLE"
      export RCLONE_CONFIG
      ;;
    *)
      fail "backend must be 'foreign' or 'google'"
      ;;
  esac

  RESTIC_TAG="echocall-postgres-${BACKEND}"
  export RESTIC_REPOSITORY
}

run_restic() {
  restic "${RESTIC_EXTRA_ARGS[@]}" "$@"
}

acquire_backend_lock() {
  require_command flock
  exec 9>"/run/lock/echocall-backup-${BACKEND}.lock"
  flock -n 9 || fail "another ${BACKEND} backup operation is running"
}
