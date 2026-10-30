#!/bin/sh
set -eu

case "${DATA_ACCESS_MODE:-direct}" in
  direct)
    if [ "${DATABASE_URL:-}" = "" ]; then
      echo "DATABASE_URL is required in direct data access mode" >&2
      exit 1
    fi
    ;;
  remote)
    if [ "${INTERNAL_API_URL:-}" = "" ] || [ "${INTERNAL_API_TOKEN:-}" = "" ]; then
      echo "INTERNAL_API_URL and INTERNAL_API_TOKEN are required in remote mode" >&2
      exit 1
    fi
    ;;
  none)
    # Stateless processes such as the Telegram Gateway do not access app data.
    ;;
  *)
    echo "DATA_ACCESS_MODE must be direct, remote, or none" >&2
    exit 1
    ;;
esac

exec "$@"
