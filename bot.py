from telegram import BotCommand, MenuButtonCommands
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from alerts.scheduler import schedule_alerts, schedule_fvg_alerts, start_fvg_stream, stop_fvg_stream
from config import (
    AUTO_ALERTS_ENABLED,
    AUTO_ALERTS_INTERVAL_MINUTES,
    TELEGRAM_TOKEN,
)

from handlers.start import start
from handlers.market import btc
from handlers.myid import myid
from handlers.chart import chart
from handlers.scan import scan
from handlers.status import status
from handlers.fvg_alert import fvg_alert, fvg_pre_alert, fvg_price, fvg_stats, fvg_symbol
from handlers.menu import menu, menu_callback
from handlers.access import access_callback, request_access


BOT_COMMANDS = (
    BotCommand("menu", "Открыть панель управления"),
    BotCommand("fvg_alert", "Включить или выключить FVG"),
    BotCommand("fvg_pre_alert", "Настроить пред-FVG T−3"),
    BotCommand("fvg_stats", "Статистика FVG"),
    BotCommand("status", "Состояние системы"),
    BotCommand("btc", "BTC сейчас"),
    BotCommand("chart", "График"),
    BotCommand("scan", "Сканер рынка"),
)


async def configure_bot_interface(application):
    """Enable Telegram's compact menu button beside the message field."""
    await application.bot.set_my_commands(BOT_COMMANDS)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def post_init(application):
    await configure_bot_interface(application)
    schedule_fvg_alerts(application)
    await start_fvg_stream(application)
    if AUTO_ALERTS_ENABLED:
        schedule_alerts(application, AUTO_ALERTS_INTERVAL_MINUTES)
        print(
            "Авто-проверка одобренных сетапов включена: "
            f"каждые {AUTO_ALERTS_INTERVAL_MINUTES} мин."
        )


def main():

    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not configured")

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .post_shutdown(stop_fvg_stream)
        .build()
    )

    # Команды Telegram
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("myid", myid)
    )

    app.add_handler(
        CommandHandler("btc", btc)
    )

    app.add_handler(
        CommandHandler("chart", chart)
    )

    app.add_handler(
        CommandHandler("scan", scan)
    )

    app.add_handler(
        CommandHandler("status", status)
    )

    app.add_handler(
        CommandHandler("fvg_alert", fvg_alert)
    )
    app.add_handler(CommandHandler("fvg_pre_alert", fvg_pre_alert))
    app.add_handler(CommandHandler("fvg_stats", fvg_stats))
    app.add_handler(CommandHandler("fvg_symbol", fvg_symbol))
    app.add_handler(CommandHandler("fvg_price", fvg_price))

    app.add_handler(CommandHandler("access", request_access))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(access_callback, pattern=r"^access:"))

    print("Trading Assistant запущен 🚀")

    app.run_polling()


if __name__ == "__main__":
    main()
