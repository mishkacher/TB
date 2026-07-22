from telegram import Update
from telegram.ext import ContextTypes


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None:
        await update.effective_message.reply_text("Не удалось определить Telegram ID.")
        return

    await update.effective_message.reply_text(
        f"Твой Telegram ID: {user.id}\n"
        "Добавь его в ALLOWED_TELEGRAM_IDS в файле .env."
    )
