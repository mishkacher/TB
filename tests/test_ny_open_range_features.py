from datetime import timedelta

import pandas as pd

from strategy_lab.ny_open_range_features import (
    fvg_membership,
    fvg_membership_ages,
    fvg_zones,
)


def test_fvg_is_unavailable_before_formation_close_and_invalidates_first():
    candles = pd.DataFrame(
        [
            ("2026-01-01 00:00:00", 96.0, 100.0, 95.0, 99.0),
            ("2026-01-01 00:05:00", 101.0, 103.0, 101.0, 102.0),
            ("2026-01-01 00:10:00", 102.0, 104.0, 102.0, 102.0),
            # This candle closes in the bullish 100-102 FVG, but its low has
            # already traded through the lower edge and invalidated the zone.
            ("2026-01-01 00:15:00", 101.0, 102.0, 99.0, 101.0),
        ],
        columns=("time", "open", "high", "low", "close"),
    )
    candles["time"] = pd.to_datetime(candles["time"])

    strict = fvg_membership(candles, "5min", timedelta(minutes=5))
    legacy = fvg_membership(
        candles,
        "5min",
        timedelta(minutes=5),
        invalidate_before_membership=False,
    )

    assert "bullish" not in strict[candles.time.iloc[1]]
    assert "bullish" in strict[candles.time.iloc[2]]
    assert "bullish" not in strict[candles.time.iloc[3]]
    assert "bullish" in legacy[candles.time.iloc[3]]


def test_sparse_membership_omits_empty_timestamps():
    candles = pd.DataFrame(
        [
            ("2026-01-01 00:00:00", 96.0, 100.0, 95.0, 99.0),
            ("2026-01-01 00:05:00", 101.0, 103.0, 101.0, 102.0),
            ("2026-01-01 00:10:00", 102.0, 104.0, 102.0, 102.0),
        ],
        columns=("time", "open", "high", "low", "close"),
    )
    candles["time"] = pd.to_datetime(candles["time"])

    sparse = fvg_membership(
        candles,
        "5min",
        timedelta(minutes=5),
        sparse=True,
    )

    assert list(sparse) == [candles.time.iloc[2]]


def test_incomplete_or_nonconsecutive_higher_timeframe_bars_do_not_form_fvg():
    times = list(pd.date_range("2026-01-01 00:00:00", periods=15, freq="5min"))
    # Removing 00:35 makes the 00:30 15-minute candle incomplete. Without the
    # completeness/continuity guard, bars on either side could form a false FVG.
    times.remove(pd.Timestamp("2026-01-01 00:35:00"))
    candles = pd.DataFrame(
        {
            "time": times,
            "open": [100.0 + index for index in range(len(times))],
            "high": [101.0 + index for index in range(len(times))],
            "low": [99.0 + index for index in range(len(times))],
            "close": [100.5 + index for index in range(len(times))],
        }
    )

    assert fvg_zones(candles, "15min", timedelta(minutes=15)) == []


def test_active_fvg_is_cleared_by_a_five_minute_data_gap():
    candles = pd.DataFrame(
        [
            ("2026-01-01 00:00:00", 96.0, 100.0, 95.0, 99.0),
            ("2026-01-01 00:05:00", 101.0, 103.0, 101.0, 102.0),
            ("2026-01-01 00:10:00", 102.0, 104.0, 102.0, 102.0),
            # 00:15 is missing; this close would otherwise sit in the old FVG.
            ("2026-01-01 00:20:00", 101.0, 102.0, 100.5, 101.0),
        ],
        columns=("time", "open", "high", "low", "close"),
    )
    candles["time"] = pd.to_datetime(candles["time"])

    membership = fvg_membership(
        candles,
        "5min",
        timedelta(minutes=5),
        sparse=True,
    )

    assert candles.time.iloc[3] not in membership


def test_fvg_age_starts_at_formation_close_and_advances_causally():
    candles = pd.DataFrame(
        [
            ("2026-01-01 00:00:00", 96.0, 100.0, 95.0, 99.0),
            ("2026-01-01 00:05:00", 101.0, 103.0, 101.0, 102.0),
            ("2026-01-01 00:10:00", 102.0, 104.0, 102.0, 102.0),
            ("2026-01-01 00:15:00", 101.5, 102.0, 100.5, 101.0),
        ],
        columns=("time", "open", "high", "low", "close"),
    )
    candles["time"] = pd.to_datetime(candles["time"])

    ages = fvg_membership_ages(candles, "5min", timedelta(minutes=5))

    assert ages[candles.time.iloc[2]]["bullish"] == 0.0
    assert ages[candles.time.iloc[3]]["bullish"] == 5 / 60
