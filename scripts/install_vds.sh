#!/usr/bin/env bash
# Установка FVG Alert Bot на Ubuntu/Debian VDS.
# Запуск: sudo bash scripts/install_vds.sh

set -euo pipefail

SERVICE_USER="fvgbot"
INSTALL_DIR="/opt/fvg-alert-bot"
SERVICE_NAME="fvg-alert-bot"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запустите скрипт с sudo: sudo bash scripts/install_vds.sh"
  exit 1
fi

if [[ ! -f "${PROJECT_DIR}/bot.py" ]]; then
  echo "Скрипт нужно запускать из папки проекта FVG Alert Bot."
  exit 1
fi

echo "Устанавливаю системные зависимости…"
apt update
apt install -y git python3 python3-venv python3-pip rsync

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  adduser --system --group --home /var/lib/fvgbot "${SERVICE_USER}"
fi

mkdir -p "${INSTALL_DIR}"
rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '.env' \
  --exclude 'data' \
  "${PROJECT_DIR}/" "${INSTALL_DIR}/"

if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"

  read -r -s -p "Введите токен BotFather: " TELEGRAM_TOKEN
  echo
  read -r -p "Введите ваш числовой Telegram ID (админ): " TELEGRAM_ID

  if [[ -z "${TELEGRAM_TOKEN}" || ! "${TELEGRAM_ID}" =~ ^[0-9]+$ ]]; then
    echo "Токен или Telegram ID заполнен неверно. Установка остановлена."
    exit 1
  fi

  sed -i "s|^TELEGRAM_TOKEN=.*|TELEGRAM_TOKEN=${TELEGRAM_TOKEN}|" "${INSTALL_DIR}/.env"
  sed -i "s|^ADMIN_TELEGRAM_IDS=.*|ADMIN_TELEGRAM_IDS=${TELEGRAM_ID}|" "${INSTALL_DIR}/.env"
  sed -i "s|^ALLOWED_TELEGRAM_IDS=.*|ALLOWED_TELEGRAM_IDS=${TELEGRAM_ID}|" "${INSTALL_DIR}/.env"
fi

echo "Создаю виртуальное окружение и устанавливаю зависимости…"
runuser -u "${SERVICE_USER}" -- python3 -m venv "${INSTALL_DIR}/.venv"
runuser -u "${SERVICE_USER}" -- "${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip
runuser -u "${SERVICE_USER}" -- "${INSTALL_DIR}/.venv/bin/python" -m pip install -r "${INSTALL_DIR}/requirements.txt"

mkdir -p "${INSTALL_DIR}/data" /tmp/trading-assistant-mpl
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}" /tmp/trading-assistant-mpl
chmod 600 "${INSTALL_DIR}/.env"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=FVG Alert Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=MPLCONFIGDIR=/tmp/trading-assistant-mpl
ExecStart=${INSTALL_DIR}/.venv/bin/python -u bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo
echo "Готово. Статус службы:"
systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo
echo "Логи:    journalctl -u ${SERVICE_NAME} -f"
echo "Статус:  systemctl status ${SERVICE_NAME}"
echo "Рестарт: systemctl restart ${SERVICE_NAME}"
