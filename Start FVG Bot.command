#!/bin/zsh
# Запускать двойным кликом в Finder.

set -u

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "Запуск FVG Alert Bot…"
echo ""

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Не найдено виртуальное окружение .venv."
  echo "Откройте Terminal в папке проекта и установите зависимости:"
  echo "  .venv/bin/python -m pip install -r requirements.txt"
  echo ""
  read -k 1 "?Нажмите любую клавишу для закрытия…"
  exit 1
fi

if [[ ! -f ".env" ]] || ! grep -q '^TELEGRAM_TOKEN=.' ".env"; then
  echo "В файле .env не задан TELEGRAM_TOKEN."
  echo "Добавьте актуальный токен от BotFather и запустите скрипт снова."
  echo ""
  read -k 1 "?Нажмите любую клавишу для закрытия…"
  exit 1
fi

mkdir -p data /tmp/trading-assistant-mpl
export MPLCONFIGDIR=/tmp/trading-assistant-mpl

echo "Бот запущен. Не закрывайте это окно, пока он должен работать."
echo "Для остановки нажмите Control+C."
echo ""

exec .venv/bin/python -u bot.py
