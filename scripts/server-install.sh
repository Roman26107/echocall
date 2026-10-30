#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/calls_tg}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash scripts/server-install.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl git rsync ufw

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi

usermod -aG docker "$DEPLOY_USER"

mkdir -p "$APP_DIR"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

systemctl enable --now docker

ufw allow OpenSSH
ufw allow 80/tcp

echo "Server is ready."
echo "Deploy user: $DEPLOY_USER"
echo "App dir: $APP_DIR"
echo "Add your GitHub Actions public SSH key to /home/$DEPLOY_USER/.ssh/authorized_keys"
