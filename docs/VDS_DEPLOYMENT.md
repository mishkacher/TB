# Установка FVG Alert Bot на VDS

Инструкция рассчитана на Ubuntu 22.04/24.04 или Debian 12. После настройки
бот запускается автоматически при перезагрузке сервера и восстанавливается при
сбое.

> Важно: один Telegram-токен может обслуживаться только одним экземпляром
> бота. Перед запуском на VDS остановите локальный запуск на Mac.

## Быстрый запуск установочным скриптом

На чистом VDS подключитесь к серверу, скачайте проект и запустите скрипт:

```bash
ssh root@IP_ВАШЕГО_СЕРВЕРА
apt update && apt install -y git
git clone https://github.com/mishkacher/TB.git fvg-alert-bot
cd fvg-alert-bot
bash scripts/install_vds.sh
```

Скрипт запросит токен BotFather и ваш числовой Telegram ID, а затем сам:

- установит Python и зависимости;
- создаст пользователя `fvgbot`;
- разместит проект в `/opt/fvg-alert-bot`;
- создаст и включит службу `fvg-alert-bot`;
- запустит бота.

После завершения смотрите логи командой:

```bash
journalctl -u fvg-alert-bot -f
```

Для установки вручную используйте инструкцию ниже.

## 1. Подключитесь к серверу

```bash
ssh root@IP_ВАШЕГО_СЕРВЕРА
```

Создайте отдельного системного пользователя и установите Python, Git и
инструменты для виртуального окружения:

```bash
adduser --disabled-password --gecos "" fvgbot
apt update
apt install -y git python3 python3-venv python3-pip
```

## 2. Склонируйте проект

```bash
sudo -u fvgbot -H bash
cd /home/fvgbot
git clone https://github.com/mishkacher/TB.git fvg-alert-bot
cd fvg-alert-bot
```

Если репозиторий приватный, настройте SSH-ключ для GitHub и используйте адрес
вида `git@github.com:mishkacher/TB.git`.

## 3. Установите зависимости

Всё ещё от имени `fvgbot`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
nano .env
```

Заполните минимум эти поля:

```env
TELEGRAM_TOKEN=токен_из_BotFather
ADMIN_TELEGRAM_IDS=ваш_числовой_Telegram_ID
ALLOWED_TELEGRAM_IDS=ваш_числовой_Telegram_ID
```

`BITUNIX_API_KEY` и `BITUNIX_SECRET` для FVG-уведомлений не требуются: бот
использует публичные рыночные данные.

Сохраните файл в `nano`: `Control+O`, `Enter`, затем `Control+X`. Ограничьте
доступ к токену:

```bash
chmod 600 .env
exit
```

## 4. Проверьте запуск вручную

```bash
sudo -u fvgbot -H bash -c 'cd /home/fvgbot/fvg-alert-bot && .venv/bin/python bot.py'
```

В консоли должно появиться `Trading Assistant запущен`. Остановите тестовый
запуск сочетанием `Control+C`.

Если Telegram показывает `Conflict`, где-то уже работает другой экземпляр с
этим токеном. Остановите его и повторите запуск.

## 5. Включите автозапуск systemd

Создайте файл службы от имени `root`:

```bash
nano /etc/systemd/system/fvg-alert-bot.service
```

Вставьте содержимое:

```ini
[Unit]
Description=FVG Alert Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=fvgbot
WorkingDirectory=/home/fvgbot/fvg-alert-bot
Environment=MPLCONFIGDIR=/tmp/trading-assistant-mpl
ExecStart=/home/fvgbot/fvg-alert-bot/.venv/bin/python -u bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активируйте и запустите службу:

```bash
systemctl daemon-reload
systemctl enable --now fvg-alert-bot
systemctl status fvg-alert-bot
```

В статусе должно быть `active (running)`.

## Управление и логи

```bash
# Смотреть логи в реальном времени
journalctl -u fvg-alert-bot -f

# Перезапустить бота
systemctl restart fvg-alert-bot

# Остановить бота
systemctl stop fvg-alert-bot

# Проверить статус
systemctl status fvg-alert-bot
```

## Обновление бота

```bash
systemctl stop fvg-alert-bot
sudo -u fvgbot -H bash -c '
  cd /home/fvgbot/fvg-alert-bot &&
  git pull &&
  .venv/bin/python -m pip install -r requirements.txt
'
systemctl start fvg-alert-bot
```

Файл `.env` не входит в Git и при обновлении сохраняется.
