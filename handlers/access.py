"""User access requests and administrator approval buttons."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_TELEGRAM_IDS, is_admin, is_authorized
from database.access_control import AccessRegistry


def access_keyboard(user_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"access:allow:{user_id}"),
        InlineKeyboardButton("⛔ Заблокировать", callback_data=f"access:block:{user_id}"),
    ]])


def request_description(user):
    name = " ".join(part for part in [user.first_name, user.last_name] if part) or "Без имени"
    username = f"@{user.username}" if user.username else "без username"
    return name, username


async def request_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None:
        return
    registry = AccessRegistry()
    if is_authorized(user.id) or registry.is_allowed(user.id):
        await update.effective_message.reply_text("✅ Доступ уже одобрен.")
        return

    name, username = request_description(user)
    status = registry.request(user.id, name, username)
    if status == "blocked":
        await update.effective_message.reply_text("⛔ Доступ к боту заблокирован.")
        return
    if status == "pending_existing":
        await update.effective_message.reply_text("⏳ Заявка уже ожидает решения владельца.")
        return
    if status == "pending":
        await update.effective_message.reply_text("⏳ Заявка отправлена владельцу бота.")
        text = (
            "🔐 Новая заявка на доступ\n"
            f"Имя: {name}\n"
            f"Username: {username}\n"
            f"Telegram ID: {user.id}"
        )
        for admin_id in ADMIN_TELEGRAM_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=access_keyboard(user.id),
            )


async def access_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or not query.data:
        return
    if not is_admin(user.id):
        await query.answer("Недостаточно прав.", show_alert=True)
        return
    _, decision, raw_user_id = query.data.split(":", 2)
    requested_id = int(raw_user_id)
    status = "allowed" if decision == "allow" else "blocked"
    if not AccessRegistry().decide(requested_id, status):
        await query.answer("Заявка уже обработана.")
        return

    await query.answer("Решение сохранено.")
    await query.edit_message_reply_markup(reply_markup=None)
    result = "✅ Доступ одобрен" if status == "allowed" else "⛔ Доступ заблокирован"
    await query.message.reply_text(f"{result}: {requested_id}")
    await context.bot.send_message(
        chat_id=requested_id,
        text=(
            "✅ Доступ к Trading Assistant одобрен. Отправь /start."
            if status == "allowed" else "⛔ В доступе к Trading Assistant отказано."
        ),
    )
