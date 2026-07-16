from telegram import Update
from telegram.ext import ContextTypes

from exchange.market_data import MarketData


market = MarketData()


async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = market.get_price("BTCUSDT")

        message = (
            f"₿ {data['symbol']}\n\n"
            f"Цена: {data['price']:.2f}$\n"
            f"High 24h: {data['high']:.2f}$\n"
            f"Low 24h: {data['low']:.2f}$\n\n"
            f"Объём: {data['volume']/1_000_000_000:.2f}B USDT"
        )

        await update.message.reply_text(message)

    except Exception as e:

        await update.message.reply_text(
            f"Ошибка получения данных:\n{e}"
        )