#!/usr/bin/env bash
# Ubuntu 22.04/24.04 서버 첫 설치 스크립트. 코드가 /opt/carrygg 에 풀려 있고 .env 를 만든 뒤 실행한다.
#   sudo bash /opt/carrygg/deploy/setup.sh your.domain.example
set -euo pipefail

DOMAIN="${1:?사용법: sudo bash deploy/setup.sh <도메인>}"
APP_DIR=/opt/carrygg
DATA_DIR=/var/lib/carrygg

echo "[1/5] 패키지 설치 (python, caddy)"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip debian-keyring debian-archive-keyring apt-transport-https curl gpg
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

# 관리자 포트가 1024 미만(기본 300)이면 일반 계정(carrygg)이 열 수 없어 사이트 전체가 재시작을 반복한다
if ! grep -q '^ADMIN_PORT=' "$APP_DIR/.env"; then
  echo "ADMIN_PORT=3300" >> "$APP_DIR/.env"
fi

echo "[2/5] 실행 계정·데이터 폴더"
id carrygg >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin carrygg
mkdir -p "$DATA_DIR/backups"
chown -R carrygg:carrygg "$APP_DIR" "$DATA_DIR"
chmod 600 "$APP_DIR/.env"

echo "[3/5] 파이썬 가상환경"
sudo -u carrygg python3 -m venv "$APP_DIR/venv"
sudo -u carrygg "$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements-server.txt"

echo "[4/5] 서비스 등록"
cp "$APP_DIR/deploy/carrygg.service" /etc/systemd/system/carrygg.service
# 디스코드 봇: .env 에 봇 토큰이 있으면 같이 켠다
if grep -q '^DISCORD_BOT_TOKEN=..*' "$APP_DIR/.env"; then
  cp "$APP_DIR/deploy/carrygg-bot.service" /etc/systemd/system/carrygg-bot.service
fi
systemctl daemon-reload
systemctl enable --now carrygg
if [ -f /etc/systemd/system/carrygg-bot.service ]; then
  systemctl enable --now carrygg-bot
fi

echo "[5/5] HTTPS (Caddy)"
sed "s/YOUR_DOMAIN/$DOMAIN/" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl reload caddy || systemctl restart caddy

echo "완료: https://$DOMAIN  (로그: journalctl -u carrygg -f / $APP_DIR/server.log)"
