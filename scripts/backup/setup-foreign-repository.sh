#!/usr/bin/env bash
set -euo pipefail

[ "${EUID:-$(id -u)}" -eq 0 ] || { echo "Run as root." >&2; exit 1; }
PUBLIC_KEY_FILE="${1:-}"
[ -r "$PUBLIC_KEY_FILE" ] || { echo "Usage: $0 PUBLIC_KEY_FILE" >&2; exit 2; }
PUBLIC_KEY="$(cat "$PUBLIC_KEY_FILE")"
case "$PUBLIC_KEY" in
  ssh-ed25519\ *|sk-ssh-ed25519@openssh.com\ *) ;;
  *) echo "Expected one Ed25519 public key." >&2; exit 1 ;;
esac

BACKUP_USER=echocall-backup
CHROOT_DIR=/srv/echocall-backup
KEY_DIR=/etc/ssh/authorized_keys
SSHD_DROPIN=/etc/ssh/sshd_config.d/60-echocall-backup.conf

if ! id "$BACKUP_USER" >/dev/null 2>&1; then
  getent group "$BACKUP_USER" >/dev/null 2>&1 || groupadd --system "$BACKUP_USER"
  useradd --system --gid "$BACKUP_USER" --home-dir /repository \
    --shell /usr/sbin/nologin "$BACKUP_USER"
fi

install -d -o root -g root -m 755 "$CHROOT_DIR"
install -d -o "$BACKUP_USER" -g "$BACKUP_USER" -m 700 "$CHROOT_DIR/repository"
install -d -o root -g root -m 755 "$KEY_DIR"
printf '%s\n' "$PUBLIC_KEY" >"$KEY_DIR/$BACKUP_USER"
# Public keys are not secrets. The file stays root-owned (not user-writable),
# while 0644 lets the unprivileged sshd authentication process read it.
chmod 644 "$KEY_DIR/$BACKUP_USER"
chown root:root "$KEY_DIR/$BACKUP_USER"

cat >"$SSHD_DROPIN" <<'SSHD_EOF'
Match User echocall-backup
    ChrootDirectory /srv/echocall-backup
    ForceCommand internal-sftp
    AuthorizedKeysFile /etc/ssh/authorized_keys/echocall-backup
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AllowAgentForwarding no
    AllowTcpForwarding no
    X11Forwarding no
    PermitTTY no
SSHD_EOF

if ! sshd -t; then
  rm -f "$SSHD_DROPIN"
  echo "Invalid sshd configuration; change rolled back." >&2
  exit 1
fi
systemctl reload ssh.service
echo "Restricted SFTP repository is ready at /repository."
