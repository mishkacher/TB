"""Backward-compatible imports for the redesigned FVG module."""

from alerts.fvg_service import FvgAlertService, format_fvg_message
from alerts.fvg_store import FvgAlertSettings, FvgEventStore


class BtcFvgAlertService(FvgAlertService):
    """Compatibility name; the service itself now supports multiple symbols."""

    SYMBOL = "BTCUSDT"
    INTERVAL = "15m"


__all__ = [
    "BtcFvgAlertService",
    "FvgAlertService",
    "FvgAlertSettings",
    "FvgEventStore",
    "format_fvg_message",
]
