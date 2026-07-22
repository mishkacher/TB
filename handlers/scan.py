import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from handlers.auth import authorized
from pipeline.live import run_live_candidate_pipeline


RULE_TRANSLATIONS = {
    "RSI healthy": "RSI в норме",
    "RSI not oversold": "RSI не перепродан",
    "Volume increased": "Объём повышен",
    "Positive momentum": "Положительный импульс",
    "Negative momentum": "Отрицательный импульс",
}

SIGNAL_TRANSLATIONS = {
    "LONG BIAS": "ПРЕИМУЩЕСТВО LONG",
    "SHORT BIAS": "ПРЕИМУЩЕСТВО SHORT",
    "NEUTRAL": "НЕЙТРАЛЬНО",
}

STRUCTURE_TRANSLATIONS = {
    "BULLISH": "БЫЧЬЯ",
    "BEARISH": "МЕДВЕЖЬЯ",
    "RANGE": "БОКОВАЯ",
}

FVG_TRANSLATIONS = {
    "BULLISH": "БЫЧИЙ",
    "BEARISH": "МЕДВЕЖИЙ",
}

FUNDING_TRANSLATIONS = {
    "SUPPORTS_LONG_SQUEEZE": "Поддержка LONG-сценария",
    "SUPPORTS_SHORT_SQUEEZE": "Поддержка SHORT-сценария",
    "COUNTERTREND_FUNDING": "Фандинг против направления",
    "NEUTRAL": "Нейтральный фандинг",
    "UNAVAILABLE": "Данные недоступны",
    "NO_TRADE_DIRECTION": "Нет торгового направления",
}


def format_scan_results(results):
    if not results:
        return "Сканер не вернул кандидатов."

    lines = ["🔎 TOP MARKET CANDIDATES"]
    for result in results:
        reasons = ", ".join(
            RULE_TRANSLATIONS.get(rule, rule) for rule in result["rules"]
        ) or "нет подтверждений"
        structure = STRUCTURE_TRANSLATIONS.get(
            result["analysis"]["market_structure"],
            result["analysis"]["market_structure"],
        )
        funding = result["derivatives_context"]
        funding_interpretation = FUNDING_TRANSLATIONS.get(
            funding["funding_interpretation"],
            funding["funding_interpretation"],
        )
        factors = result.get("confluence_factors", {})
        technical_context = []
        fibonacci_factor = factors.get("fibonacci_proximity", {})
        if fibonacci_factor.get("score", 0) > 0:
            level = result["analysis"]["nearest_fibonacci_level"]
            technical_context.append(
                f"Фибоначчи {level['level']} ({level['distance_percent']:.2f}%)"
            )
        fvg_factor = factors.get("fair_value_gap", {})
        if fvg_factor.get("score", 0) > 0:
            technical_context.append(
                f"FVG {FVG_TRANSLATIONS.get(fvg_factor['gap']['direction'], fvg_factor['gap']['direction'])} "
                f"({fvg_factor['distance_percent']:.2f}%)"
            )
        technical_text = (
            "\nТехнические зоны: " + ", ".join(technical_context)
            if technical_context
            else ""
        )
        lines.append(
            f"\n{result['symbol']} | "
            f"{SIGNAL_TRANSLATIONS.get(result['signal'], result['signal'])}"
            f"\nСканер: {result['score']} | Рейтинг: {result['ranking_score']}"
            f" | Совпадение: {result['confluence_score']}"
            f" | Качество: {result['quality']}"
            f"\nСтруктура: {structure}"
            f"\nФандинг: {funding['funding_rate_percent']:+.4f}%"
            f" / {funding['funding_interval_hours']}ч"
            f" | {funding_interpretation}"
            f"\nПричины: {reasons}"
            f"{technical_text}"
        )

    lines.append(
        "\n⚠️ Это кандидаты Scanner, а не торговая рекомендация."
    )
    return "\n".join(lines)


@authorized
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_scan(update.effective_message)


async def send_scan(message):
    await message.reply_text("Сканирую рынок…")
    results = await asyncio.to_thread(run_live_candidate_pipeline)
    await message.reply_text(format_scan_results(results))
