"""Telegram JobQueue integration for approved setup alerts."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

from alerts.alerts import AlertService
from alerts.fvg_service import FvgAlertService
from alerts.fvg_stream import BitunixFvgStream
from config import ALLOWED_TELEGRAM_IDS
from handlers.chart import build_chart
from pipeline.live import run_live_candidate_pipeline
from strategy_lab.report_store import ReportStore
from strategy_lab.outcomes import ReportOutcomeProvider, StrategyReportRegistry


logger = logging.getLogger(__name__)


def load_strategy_validation(report_path="data/reports/btcusdt_15m_365d_v0_1_0.json"):
    """Read the latest persisted validation verdict; missing data means reject."""
    return ReportStore.load_validation(report_path)


async def run_scheduled_alerts(context):
    """Run one scan and notify only setups approved by all safety gates."""
    candidates = await asyncio.to_thread(run_live_candidate_pipeline)
    service = context.job.data["alert_service"]
    reports = context.job.data["report_registry"]
    approved = []
    for candidate in candidates:
        report_path = reports.path_for(candidate["symbol"])
        validation = ReportStore.load_validation(report_path)
        approved.extend(
            service.approved_once(
                [candidate],
                validation,
                outcome_provider=ReportOutcomeProvider(report_path),
            )
        )

    for evaluation in approved:
        candidate = evaluation["candidate"]
        path = None
        try:
            path, _ = await asyncio.to_thread(build_chart, candidate["symbol"])
            caption = (
                f"✅ APPROVED SETUP\n{candidate['symbol']} | {candidate['signal']}\n"
                f"Confluence: {candidate['confluence_score']}\n"
                f"Probability: {evaluation['probability']['probability_percent']:.1f}%\n"
                f"Confidence: {evaluation['confidence']['confidence_percent']:.1f}%"
            )
            for chat_id in ALLOWED_TELEGRAM_IDS:
                with path.open("rb") as image:
                    await context.bot.send_photo(chat_id=chat_id, photo=image, caption=caption)
        finally:
            if path is not None:
                Path(path).unlink(missing_ok=True)


def schedule_alerts(application, interval_minutes):
    """Register the periodic scan once; it starts only when explicitly enabled."""
    if application.job_queue is None:
        raise RuntimeError("Telegram JobQueue is unavailable")
    application.job_queue.run_repeating(
        run_scheduled_alerts,
        interval=interval_minutes * 60,
        first=10,
        name="approved-setup-alerts",
        data={
            "alert_service": AlertService(),
            "report_registry": StrategyReportRegistry(),
        },
    )


_FVG_SERVICE = None
_FVG_STREAM = None


def get_fvg_service():
    global _FVG_SERVICE
    if _FVG_SERVICE is None:
        _FVG_SERVICE = FvgAlertService()
    return _FVG_SERVICE


async def run_fvg_recovery(context):
    """Periodic REST safety net; WebSocket remains the primary source."""
    service = context.job.data["fvg_service"]
    for symbol in sorted(service.settings.active_symbols()):
        try:
            events = await asyncio.to_thread(service.recover, symbol)
            await service.deliver(context.bot, events)
        except (requests.RequestException, ValueError) as error:
            logger.warning("Bitunix FVG recovery failed for %s: %s", symbol, error)
            service.event_store.update_health(last_error=str(error))


async def run_fvg_control_point(context):
    """Evaluate cached candles around boundaries without another REST request."""
    service = context.job.data["fvg_service"]
    now = context.job.data.get("clock", None)
    if callable(now):
        now = now()
    if now is None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
    for symbol in sorted(service.settings.active_symbols()):
        await service.deliver(context.bot, service.evaluate(symbol, now))


def schedule_fvg_alerts(application):
    """Register lightweight control points and the REST recovery safety net."""
    if application.job_queue is None:
        raise RuntimeError("Telegram JobQueue is unavailable")
    service = get_fvg_service()
    seconds = datetime.now(timezone.utc).timestamp() % 900
    confirmed_delay = 900 - seconds + 5
    pre_delay = (725 - seconds) % 900
    if pre_delay < 1:
        pre_delay += 900
    application.job_queue.run_repeating(
        run_fvg_control_point,
        interval=900,
        first=confirmed_delay,
        name="fvg-confirmed-control",
        data={"fvg_service": service},
    )
    application.job_queue.run_repeating(
        run_fvg_control_point,
        interval=900,
        first=pre_delay,
        name="fvg-pre-control-t-minus-3",
        data={"fvg_service": service},
    )
    application.job_queue.run_repeating(
        run_fvg_recovery,
        interval=300,
        first=15,
        name="fvg-rest-recovery",
        data={"fvg_service": service},
    )


async def start_fvg_stream(application):
    global _FVG_STREAM
    service = get_fvg_service()
    _FVG_STREAM = BitunixFvgStream(service)
    application.create_task(_FVG_STREAM.run(application.bot), name="bitunix-fvg-stream")


async def stop_fvg_stream(application):
    if _FVG_STREAM is not None:
        _FVG_STREAM.stop()
