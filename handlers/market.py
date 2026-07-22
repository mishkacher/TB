from telegram import Update
from telegram.ext import ContextTypes

from exchange.market_data import MarketData
from handlers.auth import authorized


market = MarketData()


@authorized
async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_btc(update.effective_message)


async def send_btc(reply_target):

    try:

        data = market.get_price("BTCUSDT")

        response_text = (
            f"₿ {data['symbol']}\n\n"
            f"Цена: {data['price']:.2f}$\n"
            f"High 24h: {data['high']:.2f}$\n"
            f"Low 24h: {data['low']:.2f}$\n\n"
            f"Объём: {data['volume']/1_000_000_000:.2f}B USDT"
        )

        await reply_target.reply_text(response_text)

    except Exception as e:

        await reply_target.reply_text(
            f"Ошибка получения данных:\n{e}"
        )
