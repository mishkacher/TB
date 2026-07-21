from telegram import Update
from telegram.ext import ContextTypes

from handlers.auth import authorized
from handlers.menu import show_menu


@authorized
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.effective_message.reply_text(
        "🤖 Trading Assistant запущен!\n\n"
        "Статус системы:\n"
        "✅ Telegram\n"
        "✅ Bitunix API\n"
        "✅ Scanner\n"
        "✅ Analysis + Confluence\n"
        "✅ Funding context\n"
        "🛡️ Decision Gate\n"
        "⏳ Probability — ждёт валидированной стратегии\n\n"
        "Команды:\n"
        "/btc — текущие данные BTC\n"
        "/chart BTCUSDT 1h — график: 15m, 1h или 4h\n"
        "/scan — кандидаты рынка с объяснениями\n"
        "/status — состояние стратегии и авторассылки\n"
        "/fvg_alert on|off — FVG 15m уведомления\n"
        "/fvg_pre_alert on|off — пред-FVG за 3 минуты\n"
        "/fvg_symbol add ETHUSDT — добавить инструмент\n"
        "/fvg_price BTCUSDT 50000 90000 both — фильтр цены\n"
        "/fvg_stats — статистика FVG-событий\n"
        "/backtest — локальный бэктест стратегии через Backtrader\n"
        "/menu — кнопки управления\n\n"
        "Бот временно открыт для всех пользователей.\n"
        "Кнопка меню рядом с полем сообщения открывает эти команды. "
        "Выбери «Открыть панель управления» для графического меню."
    )
    await show_menu(update.effective_message, update.effective_chat.id)
