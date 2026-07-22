"""No-look-ahead FVG and Fibonacci filters for the NY opening-range tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd


@dataclass
class FVG:
    available_at: pd.Timestamp
    direction: str
    lower: float
    upper: float


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    frame = df[["time", "open", "high", "low", "close"]].copy()
    frame["_count"] = 1
    five_minutes = pd.Timedelta(minutes=5)
    timestamps = pd.to_datetime(frame["time"])
    frame["_on_grid"] = (
        timestamps.dt.minute.mod(5).eq(0)
        & timestamps.dt.second.eq(0)
        & timestamps.dt.microsecond.eq(0)
    )
    indexed = frame.set_index("time")
    bars = indexed.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "_count": "sum",
            "_on_grid": "all",
        }
    )
    expected_count = int(pd.Timedelta(rule) / five_minutes)
    complete = bars[(bars["_count"] == expected_count) & bars["_on_grid"]]
    return complete.drop(columns=["_count", "_on_grid"]).reset_index()


def fvg_zones(df: pd.DataFrame, rule: str, duration: timedelta) -> list[FVG]:
    bars = _resample(df, rule)
    zones: list[FVG] = []
    for i in range(2, len(bars)):
        first, middle, third = bars.iloc[i - 2], bars.iloc[i - 1], bars.iloc[i]
        if (
            middle.time - first.time != duration
            or third.time - middle.time != duration
        ):
            continue
        available = third.time + duration
        if float(third.low) > float(first.high):
            zones.append(FVG(available, "bullish", float(first.high), float(third.low)))
        elif float(third.high) < float(first.low):
            zones.append(FVG(available, "bearish", float(third.high), float(first.low)))
    return zones


def fvg_membership(
    df: pd.DataFrame,
    rule: str,
    duration: timedelta,
    invalidate_before_membership: bool = True,
    sparse: bool = False,
) -> dict[pd.Timestamp, set[str]]:
    """Return FVG directions containing each 5m close while still uninvalidated.

    A bullish gap is invalidated after price trades through its lower edge and a
    bearish gap after price trades through its upper edge. By default the
    current candle invalidates a zone before membership is evaluated. This
    prevents a candle that has already traded completely through an FVG from
    qualifying merely because it closes back inside the former zone.
    """
    zones = fvg_zones(df, rule, duration)
    active: list[FVG] = []
    result: dict[pd.Timestamp, set[str]] = {}
    cursor = 0
    previous_time: pd.Timestamp | None = None
    for candle in df.itertuples(index=False):
        gap = (
            previous_time is not None
            and candle.time - previous_time != timedelta(minutes=5)
        )
        if gap:
            active.clear()
            # A zone that existed before unavailable market data cannot safely
            # remain active after the gap. Skip all such historical zones.
            while cursor < len(zones) and zones[cursor].available_at <= candle.time:
                cursor += 1
        close_time = candle.time + timedelta(minutes=5)
        while cursor < len(zones) and zones[cursor].available_at <= close_time:
            active.append(zones[cursor])
            cursor += 1
        invalidated = lambda zone: (
            (zone.direction == "bullish" and float(candle.low) <= zone.lower)
            or (zone.direction == "bearish" and float(candle.high) >= zone.upper)
        )
        if invalidate_before_membership:
            active = [zone for zone in active if not invalidated(zone)]
        close = float(candle.close)
        membership = {
            zone.direction for zone in active if zone.lower <= close <= zone.upper
        }
        if membership or not sparse:
            result[candle.time] = membership
        if not invalidate_before_membership:
            active = [zone for zone in active if not invalidated(zone)]
        previous_time = candle.time
    return result


def fvg_membership_ages(
    df: pd.DataFrame,
    rule: str,
    duration: timedelta,
) -> dict[pd.Timestamp, dict[str, float]]:
    """Return the age in hours of the youngest active FVG containing each close.

    Zones use strict invalidation, complete consecutive higher-timeframe bars,
    and are reset across missing 5-minute data. An age of zero means the FVG
    became available at the close of the current 5-minute candle.
    """
    zones = fvg_zones(df, rule, duration)
    active: list[FVG] = []
    result: dict[pd.Timestamp, dict[str, float]] = {}
    cursor = 0
    previous_time: pd.Timestamp | None = None
    for candle in df.itertuples(index=False):
        gap = (
            previous_time is not None
            and candle.time - previous_time != timedelta(minutes=5)
        )
        if gap:
            active.clear()
            while cursor < len(zones) and zones[cursor].available_at <= candle.time:
                cursor += 1
        close_time = candle.time + timedelta(minutes=5)
        while cursor < len(zones) and zones[cursor].available_at <= close_time:
            active.append(zones[cursor])
            cursor += 1
        active = [
            zone
            for zone in active
            if not (
                (zone.direction == "bullish" and float(candle.low) <= zone.lower)
                or (
                    zone.direction == "bearish"
                    and float(candle.high) >= zone.upper
                )
            )
        ]
        close = float(candle.close)
        ages: dict[str, float] = {}
        for zone in active:
            if not zone.lower <= close <= zone.upper:
                continue
            age = (close_time - zone.available_at).total_seconds() / 3600
            current = ages.get(zone.direction)
            if current is None or age < current:
                ages[zone.direction] = float(age)
        if ages:
            result[candle.time] = ages
        previous_time = candle.time
    return result


def build_fvg_features(df: pd.DataFrame, strict: bool = True) -> tuple[dict, dict]:
    return (
        fvg_membership(df, "15min", timedelta(minutes=15), strict),
        fvg_membership(df, "4h", timedelta(hours=4), strict),
    )


def build_all_fvg_features(df: pd.DataFrame, strict: bool = True) -> dict[str, dict]:
    """Build sparse-ready membership maps for every strategy timeframe."""
    fvg_15m, fvg_4h = build_fvg_features(df, strict)
    return {
        "5m": fvg_membership(df, "5min", timedelta(minutes=5), strict),
        "10m": fvg_membership(df, "10min", timedelta(minutes=10), strict),
        "15m": fvg_15m,
        "1h": fvg_membership(df, "1h", timedelta(hours=1), strict),
        "4h": fvg_4h,
    }


def in_fibonacci_zone(close: float, low: float, high: float, direction: str) -> bool:
    """Check the 0.50-0.618 retracement zone of the first NY 4H range."""
    width = high - low
    if direction == "LONG":
        lower, upper = low + width * 0.5, low + width * 0.618
    else:
        lower, upper = low + width * (1 - 0.618), low + width * 0.5
    return lower <= close <= upper
