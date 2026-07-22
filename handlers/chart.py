import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from analysis.analysis import AnalysisEngine
from analysis.candles import candles_to_dataframe
from analysis.indicators import add_indicators
from charts.candlestick import CandlestickChart
from exchanges.bitunix import BitunixClient
from handlers.auth import authorized

SUPPORTED_INTERVALS = {"15m", "1h", "4h"}


def parse_chart_arguments(arguments):
    symbol = arguments[0].upper() if arguments else "BTCUSDT"
    interval = arguments[1].lower() if len(arguments) > 1 else "15m"
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError("Поддерживаемые таймфреймы: 15m, 1h, 4h")
    return symbol, interval


def build_chart(symbol, interval="15m"):
    client = BitunixClient()
    # Bitunix documents 200 as the maximum kline page size.
    response = client.get_candles(symbol, interval, 200)
    dataframe = add_indicators(candles_to_dataframe(response["data"]))
    analysis = AnalysisEngine().analyze(dataframe)
    path = CandlestickChart().render(
        dataframe, symbol, analysis, interval=interval
    )
    return path, analysis


@authorized
async def chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol, interval = parse_chart_arguments(context.args)
    except ValueError as error:
        await update.effective_message.reply_text(str(error))
        return
    await send_chart(update.effective_message, symbol, interval)


async def send_chart(message, symbol, interval):
    await message.reply_text(f"Строю график {symbol} · {interval}…")
    path = None

    try:
        path, analysis = await asyncio.to_thread(build_chart, symbol, interval)
        with path.open("rb") as image:
            await message.reply_photo(
                image,
                caption=(
                    f"{symbol} · {interval}\n"
                    f"Structure: {analysis['market_structure']}\n"
                    f"Current: {analysis['current_price']:,.4f}\n"
                    "EMA 50/200 и открытые FVG"
                ),
            )
    except Exception:
        await message.reply_text(
            f"Не удалось построить график для {symbol}. Попробуй ещё раз через минуту."
        )
    finally:
        if path is not None:
            Path(path).unlink(missing_ok=True)
