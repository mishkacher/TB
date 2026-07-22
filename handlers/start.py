from telegram import Update
from telegram.ext import ContextTypes

from handlers.auth import authorized
from handlers.menu import show_menu


@authorized
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.effective_message.reply_text(
        "🤖 FVG Alert Bot запущен!\n\n"
        "Бот специализируется на Fair Value Gap (FVG) для фьючерсов Bitunix.\n"
        "Он отслеживает предварительные FVG в точке T−3 и подтверждённые FVG "
        "на 15-минутном таймфрейме.\n\n"
        "Команды:\n"
        "/fvg_alert on|off — FVG 15m уведомления\n"
        "/fvg_pre_alert on|off — пред-FVG за 3 минуты\n"
        "/fvg_symbol add ETHUSDT — добавить инструмент\n"
        "/fvg_price BTCUSDT 50000 90000 both — фильтр цены\n"
        "/fvg_size — фильтр размера FVG\n"
        "/fvg_stats — статистика FVG-событий\n"
        "/menu — кнопки управления\n\n"
        "/admin — админ-панель и статистика пользователей.\n\n"
        "Кнопка меню рядом с полем сообщения открывает настройки FVG."
    )
    await show_menu(update.effective_message, update.effective_chat.id)
