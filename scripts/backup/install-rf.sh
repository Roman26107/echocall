#!/usr/bin/env bash
set -euo pipefail

[ "${EUID:-$(id -u)}" -eq 0 ] || { echo "Run as root." >&2; exit 1; }
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y restic rclone

install -d -m 700 /etc/echocall-backup /var/lib/echocall-backup/staging
install -d -m 700 /var/cache/echocall-backup/restic
install -m 755 "$SCRIPT_DIR/echocall-backup-lib.sh" /usr/local/lib/echocall-backup-lib.sh
install -m 755 "$SCRIPT_DIR/echocall-backup.sh" /usr/local/sbin/echocall-backup
install -m 755 "$SCRIPT_DIR/echocall-backup-init.sh" /usr/local/sbin/echocall-backup-init
install -m 755 "$SCRIPT_DIR/echocall-restore-test.sh" /usr/local/sbin/echocall-restore-test
install -m 755 "$SCRIPT_DIR/echocall-backup-trigger.py" /usr/local/sbin/echocall-backup-trigger

# Installed entrypoints source the library from their own directory.
ln -sfn /usr/local/lib/echocall-backup-lib.sh /usr/local/sbin/echocall-backup-lib.sh

install -m 644 "$SCRIPT_DIR"/systemd/*.service /etc/systemd/system/
install -m 644 "$SCRIPT_DIR"/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now echocall-backup-trigger.service

if [ ! -e /etc/echocall-backup/backup.env ]; then
  tr -d '\r' <"$SCRIPT_DIR/backup.env.example" >/etc/echocall-backup/backup.env
  chown root:root /etc/echocall-backup/backup.env
  chmod 600 /etc/echocall-backup/backup.env
fi

echo "Backup tools and restricted trigger installed. Backup timers were intentionally NOT enabled."
