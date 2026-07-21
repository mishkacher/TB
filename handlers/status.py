from telegram import Update
from telegram.ext import ContextTypes

from config import AUTO_ALERTS_ENABLED, AUTO_ALERTS_INTERVAL_MINUTES
from handlers.auth import authorized
from strategy_lab.report_store import ReportStore
from alerts.fvg_store import FvgAlertSettings, FvgEventStore


REPORT_PATH = "data/reports/btcusdt_15m_365d_v0_1_0.json"


def format_system_status(validation, auto_alerts_enabled, interval_minutes, fvg_health=None, fvg_symbols=None):
    if validation["approved"]:
        strategy = "✅ Strategy Lab: стратегия одобрена"
    else:
        reasons = ", ".join(validation.get("reasons", [])) or "нет отчёта"
        strategy = f"⛔ Strategy Lab: автосетапы заблокированы ({reasons})"

    auto_alerts = (
        f"✅ Авторассылка: включена, каждые {interval_minutes} мин."
        if auto_alerts_enabled
        else "⏸️ Авторассылка: выключена в настройках"
    )
    lines = [
            "📊 SYSTEM STATUS",
            "✅ Scanner + Analysis + Confluence",
            strategy,
            "🛡️ Decision Gate: активен",
            auto_alerts,
        ]
    if fvg_health is not None:
        ws = "подключён" if fvg_health.get("ws_connected") else "нет соединения"
        symbols = ", ".join(sorted(fvg_symbols or [])) or "нет активных"
        lines.extend([
            f"📡 FVG WebSocket: {ws}",
            f"FVG-инструменты: {symbols}",
            f"Последнее WS-сообщение: {fvg_health.get('last_ws_message', 'ещё не было')}",
            f"Последнее REST-восстановление: {fvg_health.get('last_rest_recovery', 'ещё не было')}",
            f"FVG-событий / доставок: {fvg_health.get('events', 0)} / {fvg_health.get('deliveries', 0)}",
            f"FVG подтверждённых / предварительных: {fvg_health.get('confirmed_events', 0)} / {fvg_health.get('pre_events', 0)}",
            f"Переподключений / ошибок доставки: {fvg_health.get('reconnects', 0)} / {fvg_health.get('delivery_failures', 0)}",
        ])
        if fvg_health.get("last_error"):
            lines.append(f"Последняя ошибка FVG: {fvg_health['last_error']}")
    return "\n".join(lines)


@authorized
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status(update.effective_message)


async def send_status(message):
    validation = ReportStore.load_validation(REPORT_PATH)
    settings = FvgAlertSettings()
    await message.reply_text(
        format_system_status(
            validation,
            AUTO_ALERTS_ENABLED,
            AUTO_ALERTS_INTERVAL_MINUTES,
            FvgEventStore().health(),
            settings.active_symbols(),
        )
    )
