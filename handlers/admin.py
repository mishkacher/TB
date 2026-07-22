"""Administrator dashboard and user activity statistics."""

from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import is_admin
from database.user_activity import UserActivityRegistry


def admin_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        "👥 Статистика пользователей", callback_data="admin:users"
    )]])


def _format_time(raw):
    if not raw:
        return "—"
    return datetime.fromisoformat(raw).astimezone().strftime("%d.%m.%Y %H:%M")


def format_user_stats(registry=None, now=None):
    registry = registry or UserActivityRegistry()
    now = now or datetime.now(timezone.utc)
    users = list(registry.users().values())

    def active_since(delta):
        return sum(
            datetime.fromisoformat(user["last_seen"]) >= now - delta
            for user in users if user.get("last_seen")
        )

    latest = sorted(users, key=lambda user: user.get("last_seen", ""), reverse=True)[:5]
    lines = [
        "👥 Статистика пользователей",
        "",
        f"Всего пользователей: {len(users)}",
        f"Активны за 24 часа: {active_since(timedelta(days=1))}",
        f"Активны за 7 дней: {active_since(timedelta(days=7))}",
        f"Активны за 30 дней: {active_since(timedelta(days=30))}",
    ]
    if latest:
        lines.extend(["", "Последняя активность:"])
        for user in latest:
            username = f" @{user['username']}" if user.get("username") else ""
            lines.append(f"• {user.get('name', 'Без имени')}{username} — {_format_time(user.get('last_seen'))}")
    return "\n".join(lines)


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None or not is_admin(user.id):
        await update.effective_message.reply_text("Эта панель доступна только администраторам.")
        return
    await update.effective_message.reply_text("🛠 Админ-панель", reply_markup=admin_keyboard())


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not is_admin(user.id):
        await query.edit_message_text("Эта панель доступна только администраторам.")
        return
    if query.data == "admin:users":
        await query.edit_message_text(format_user_stats(), reply_markup=admin_keyboard())
