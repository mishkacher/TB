from telegram.ext import Application, CommandHandler

from config import TELEGRAM_TOKEN

from handlers.start import start
from handlers.market import btc


def main():

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команды Telegram
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("btc", btc)
    )

    print("Trading Assistant запущен 🚀")

    app.run_polling()


if __name__ == "__main__":
    main()