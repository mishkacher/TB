from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🤖 Trading Assistant запущен!\n\n"
        "Статус системы:\n"
        "✅ Telegram\n"
        "✅ Bitunix API\n"
        "⏳ Scanner\n"
        "⏳ Analysis\n"
        "⏳ Signals"
    )