#!/usr/bin/env python3
"""Fast, no-look-ahead research sweep for the NY opening-range fade.

This utility is deliberately independent of the production Telegram and
Backtrader code.  It screens many variants quickly, reports chronological
stability, and keeps the original Backtrader configuration in every preset as
a benchmark.  Promising finalists should still be re-run in Backtrader before
they are considered for live use.

The signal sequence is:

1. Build the high/low of the closed 00:00-04:00 New York range.
2. Observe a qualifying 5-minute break of one boundary.
3. Wait for a qualifying reclaim of the range.
4. Require direction-aligned active FVG membership and a Fibonacci zone.
5. Enter on the next 5-minute open, stop beyond the breakout wick, and target
   the configured reward/risk multiple.

OHLC ambiguity is handled conservatively: when stop and target are both
touched in one bar, the stop is counted first.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data/historical/btcusdt_5m_bitunix_2y.csv"
DEFAULT_FEATURES = ROOT / "data/historical/ny_open_range_fvg_features_2y.json"
DEFAULT_REPORT = ROOT / "data/reports/ny_strategy_sweep_limited.json"

TIMEFRAMES = ("5m", "10m", "15m", "1h", "4h")
TF_BITS = {name: 1 << index for index, name in enumerate(TIMEFRAMES)}

# (operator, participating masks).  "count2" means at least two aligned FVGs.
FVG_SPECS: dict[str, tuple[str, tuple[int, ...]]] = {
    "none": ("none", ()),
    **{name: ("any", (TF_BITS[name],)) for name in TIMEFRAMES},
    "10m_or_15m": ("any", (TF_BITS["10m"], TF_BITS["15m"])),
    "10m_or_4h": ("any", (TF_BITS["10m"], TF_BITS["4h"])),
    "15m_or_4h": ("any", (TF_BITS["15m"], TF_BITS["4h"])),
    "10m_or_15m_or_1h": (
        "any",
        (TF_BITS["10m"], TF_BITS["15m"], TF_BITS["1h"]),
    ),
    "10m_and_15m": ("all", (TF_BITS["10m"], TF_BITS["15m"])),
    "10m_and_4h": ("all", (TF_BITS["10m"], TF_BITS["4h"])),
    "15m_and_1h": ("all", (TF_BITS["15m"], TF_BITS["1h"])),
    "15m_and_4h": ("all", (TF_BITS["15m"], TF_BITS["4h"])),
    "at_least_2": ("count2", tuple(TF_BITS.values())),
    "any": ("any", tuple(TF_BITS.values())),
}

# Break definition, reclaim definition.  "full" means the entire candle body;
# "close" means only the close must be on the requested side of the boundary.
BODY_MODES: dict[str, tuple[str, str]] = {
    "full_full": ("full", "full"),
    "full_close": ("full", "close"),
    "close_full": ("close", "full"),
    "close_close": ("close", "close"),
}


@dataclass(frozen=True, slots=True)
class DayData:
    session_date: date
    start_idx: int
    end_idx: int
    post_start_idx: int
    range_low: float
    range_high: float
    range_complete: bool


@dataclass(frozen=True, slots=True)
class Opportunity:
    """One possible reclaim after a fixed first breakout."""

    signal_idx: int
    entry_idx: int
    side: int  # +1 LONG, -1 SHORT
    wick: float
    fib_depth: float
    fvg_mask: int
    minute_of_day: int


@dataclass(frozen=True, slots=True)
class BaseConfig:
    body_mode: str
    fvg_mode: str
    direction: str
    fib_low: float
    fib_high: float
    cutoff_hour: float

    @property
    def name(self) -> str:
        fib = f"{self.fib_low:g}-{self.fib_high:g}"
        cutoff = f"{self.cutoff_hour:g}"
        return (
            f"{self.body_mode}|{self.fvg_mode}|{self.direction}|"
            f"fib={fib}|cutoff={cutoff}"
        )


@dataclass(frozen=True, slots=True)
class ExitOutcome:
    exit_idx: int
    gross_r: float
    entry: float
    stop: float
    target: float
    exit_price: float
    reason: str = "price"


@dataclass(frozen=True, slots=True)
class FeeModel:
    """Trading costs in basis points, selected by how the trade exits."""

    entry_taker_bps: float = 0.0
    stop_taker_bps: float = 0.0
    target_maker_bps: float = 0.0
    time_stop_taker_bps: float = 0.0

    @classmethod
    def uniform(cls, side_cost_bps: float) -> "FeeModel":
        return cls(
            side_cost_bps,
            side_cost_bps,
            side_cost_bps,
            side_cost_bps,
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "entry_taker_bps": self.entry_taker_bps,
            "stop_taker_bps": self.stop_taker_bps,
            "target_maker_bps": self.target_maker_bps,
            "time_stop_taker_bps": self.time_stop_taker_bps,
        }


@dataclass(slots=True)
class MarketData:
    times_utc: pd.Series
    times_ny: pd.Series
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    ny_hour: np.ndarray
    ny_minute: np.ndarray
    aligned_bull_fvg: np.ndarray
    aligned_bear_fvg: np.ndarray
    days: list[DayData]
    complete_range_sessions: frozenset[date]
    incomplete_range_sessions: tuple[date, ...]

    @property
    def size(self) -> int:
        return len(self.open)


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _csv_floats(value: str) -> list[float]:
    return [float(item) for item in _csv_values(value)]


def _fib_values(value: str) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for item in _csv_values(value):
        parts = item.split(":", maxsplit=1)
        if len(parts) != 2:
            raise argparse.ArgumentTypeError(
                f"invalid Fibonacci zone {item!r}; expected LOW:HIGH"
            )
        low, high = float(parts[0]), float(parts[1])
        if not 0 <= low < high <= 1:
            raise argparse.ArgumentTypeError(
                f"invalid Fibonacci zone {item!r}; require 0 <= LOW < HIGH <= 1"
            )
        result.append((low, high))
    return result


def _fvg_passes(mask: int, mode: str) -> bool:
    operator, bits = FVG_SPECS[mode]
    if operator == "none":
        return True
    if operator == "any":
        return any(mask & bit for bit in bits)
    if operator == "all":
        return all(mask & bit for bit in bits)
    if operator == "count2":
        return sum(bool(mask & bit) for bit in bits) >= 2
    raise ValueError(f"unsupported FVG operator: {operator}")


def _load_market(data_file: Path, features_file: Path) -> MarketData:
    frame = pd.read_csv(data_file)
    required = {"time", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing CSV columns: {', '.join(sorted(missing))}")
    parsed = pd.to_datetime(frame["time"], utc=True, errors="raise")
    order = np.argsort(parsed.to_numpy())
    frame = frame.iloc[order].reset_index(drop=True)
    parsed = parsed.iloc[order].reset_index(drop=True)
    if parsed.duplicated().any():
        raise ValueError("duplicate 5-minute timestamps are not supported")

    times_ny = parsed.dt.tz_convert("America/New_York")
    n = len(frame)
    bull = np.zeros(n, dtype=np.uint8)
    bear = np.zeros(n, dtype=np.uint8)
    feature_payload = json.loads(features_file.read_text())
    time_keys = parsed.dt.strftime("%Y-%m-%d %H:%M:%S")
    row_by_key = dict(zip(time_keys, range(n)))
    for timeframe in TIMEFRAMES:
        memberships = feature_payload.get(timeframe, {})
        bit = TF_BITS[timeframe]
        for key, directions in memberships.items():
            row = row_by_key.get(key)
            if row is None:
                continue
            if "bullish" in directions:
                bull[row] |= bit
            if "bearish" in directions:
                bear[row] |= bit

    ny_dates = times_ny.dt.date.to_numpy()
    ny_hours = times_ny.dt.hour.to_numpy(dtype=np.int16)
    ny_minutes = times_ny.dt.minute.to_numpy(dtype=np.int16)
    lows = frame["low"].to_numpy(dtype=float)
    highs = frame["high"].to_numpy(dtype=float)
    days: list[DayData] = []
    complete_range_sessions: set[date] = set()
    incomplete_range_sessions: list[date] = []
    group_start = 0
    while group_start < n:
        group_end = group_start + 1
        session_date = ny_dates[group_start]
        while group_end < n and ny_dates[group_end] == session_date:
            group_end += 1
        group_indices = np.arange(group_start, group_end)
        range_indices = group_indices[ny_hours[group_indices] < 4]
        post_indices = group_indices[ny_hours[group_indices] >= 4]
        if len(range_indices) and len(post_indices):
            expected_start = pd.Timestamp(
                f"{session_date.isoformat()} 00:00:00",
                tz="America/New_York",
            ).tz_convert("UTC")
            expected_end = pd.Timestamp(
                f"{session_date.isoformat()} 04:00:00",
                tz="America/New_York",
            ).tz_convert("UTC")
            actual_range_times = parsed.iloc[range_indices]
            range_complete = bool(
                actual_range_times.iloc[0] == expected_start
                and actual_range_times.iloc[-1] + pd.Timedelta(minutes=5)
                == expected_end
                and (
                    len(actual_range_times) == 1
                    or actual_range_times.diff()
                    .iloc[1:]
                    .eq(pd.Timedelta(minutes=5))
                    .all()
                )
            )
            if range_complete:
                complete_range_sessions.add(session_date)
            else:
                incomplete_range_sessions.append(session_date)
            days.append(
                DayData(
                    session_date=session_date,
                    start_idx=group_start,
                    end_idx=group_end - 1,
                    post_start_idx=int(post_indices[0]),
                    range_low=float(np.min(lows[range_indices])),
                    range_high=float(np.max(highs[range_indices])),
                    range_complete=range_complete,
                )
            )
        group_start = group_end

    return MarketData(
        times_utc=parsed,
        times_ny=times_ny,
        open=frame["open"].to_numpy(dtype=float),
        high=highs,
        low=lows,
        close=frame["close"].to_numpy(dtype=float),
        ny_hour=ny_hours,
        ny_minute=ny_minutes,
        aligned_bull_fvg=bull,
        aligned_bear_fvg=bear,
        days=days,
        complete_range_sessions=frozenset(complete_range_sessions),
        incomplete_range_sessions=tuple(incomplete_range_sessions),
    )


def _is_break(
    market: MarketData,
    index: int,
    range_low: float,
    range_high: float,
    definition: str,
) -> int:
    candle_open = market.open[index]
    candle_close = market.close[index]
    if definition == "full":
        if max(candle_open, candle_close) < range_low:
            return 1
        if min(candle_open, candle_close) > range_high:
            return -1
    else:
        if candle_close < range_low:
            return 1
        if candle_close > range_high:
            return -1
    return 0


def _is_reclaim(
    market: MarketData,
    index: int,
    range_low: float,
    range_high: float,
    definition: str,
) -> bool:
    candle_open = market.open[index]
    candle_close = market.close[index]
    if definition == "full":
        return (
            min(candle_open, candle_close) >= range_low
            and max(candle_open, candle_close) <= range_high
        )
    return range_low <= candle_close <= range_high


def _opportunities_from(
    market: MarketData,
    day: DayData,
    body_mode: str,
    start_idx: int | None = None,
) -> list[Opportunity]:
    """Return every reclaim following the first break after ``start_idx``."""
    break_definition, reclaim_definition = BODY_MODES[body_mode]
    start = max(day.post_start_idx, start_idx if start_idx is not None else -1)
    breakout_side = 0
    wick = math.nan
    result: list[Opportunity] = []
    width = day.range_high - day.range_low
    if width <= 0:
        return result
    for index in range(start, day.end_idx + 1):
        if breakout_side == 0:
            breakout_side = _is_break(
                market,
                index,
                day.range_low,
                day.range_high,
                break_definition,
            )
            if breakout_side == 1:
                wick = market.low[index]
            elif breakout_side == -1:
                wick = market.high[index]
            # A candle that establishes a break cannot reclaim it simultaneously.
            if breakout_side:
                continue
        if breakout_side == 0:
            continue
        if breakout_side == 1:
            wick = min(wick, market.low[index])
        else:
            wick = max(wick, market.high[index])
        if not _is_reclaim(
            market,
            index,
            day.range_low,
            day.range_high,
            reclaim_definition,
        ):
            continue
        close = market.close[index]
        if breakout_side == 1:
            fib_depth = (close - day.range_low) / width
            mask = int(market.aligned_bull_fvg[index])
        else:
            fib_depth = (day.range_high - close) / width
            mask = int(market.aligned_bear_fvg[index])
        if index + 1 >= market.size:
            continue
        result.append(
            Opportunity(
                signal_idx=index,
                entry_idx=index + 1,
                side=breakout_side,
                wick=float(wick),
                fib_depth=float(fib_depth),
                fvg_mask=mask,
                minute_of_day=int(
                    market.ny_hour[index] * 60 + market.ny_minute[index]
                ),
            )
        )
    return result


def _opportunity_passes(opportunity: Opportunity, config: BaseConfig) -> bool:
    if config.direction == "long" and opportunity.side != 1:
        return False
    if config.direction == "short" and opportunity.side != -1:
        return False
    if opportunity.minute_of_day >= round(config.cutoff_hour * 60):
        return False
    if not config.fib_low <= opportunity.fib_depth <= config.fib_high:
        return False
    return _fvg_passes(opportunity.fvg_mask, config.fvg_mode)


def _first_passing(
    opportunities: Sequence[Opportunity], config: BaseConfig
) -> Opportunity | None:
    for opportunity in opportunities:
        if _opportunity_passes(opportunity, config):
            return opportunity
    return None


def _trade_outcome(
    market: MarketData,
    opportunity: Opportunity,
    stop_buffer: float,
    reward_to_risk: float,
    time_stop_hours: float | None = None,
    time_stop_policy: str = "close",
) -> ExitOutcome | None:
    entry = market.open[opportunity.entry_idx]
    if opportunity.side == 1:
        stop = opportunity.wick * (1 - stop_buffer)
        if stop >= entry:
            return None
        risk = entry - stop
        target = entry + risk * reward_to_risk
    else:
        stop = opportunity.wick * (1 + stop_buffer)
        if stop <= entry:
            return None
        risk = stop - entry
        target = entry - risk * reward_to_risk

    deadline = None
    if time_stop_hours is not None:
        deadline = market.times_utc.iloc[opportunity.entry_idx] + pd.Timedelta(
            hours=time_stop_hours
        )
    for index in range(opportunity.entry_idx, market.size):
        if opportunity.side == 1:
            if market.low[index] <= stop:
                return ExitOutcome(index, -1.0, entry, stop, target, stop, "stop")
            if market.high[index] >= target:
                return ExitOutcome(
                    index, reward_to_risk, entry, stop, target, target, "target"
                )
        else:
            if market.high[index] >= stop:
                return ExitOutcome(index, -1.0, entry, stop, target, stop, "stop")
            if market.low[index] <= target:
                return ExitOutcome(
                    index, reward_to_risk, entry, stop, target, target, "target"
                )
        if deadline is not None:
            candle_close_time = market.times_utc.iloc[index] + pd.Timedelta(minutes=5)
            if candle_close_time >= deadline:
                if time_stop_policy == "close":
                    exit_index = index
                    exit_price = market.close[index]
                elif time_stop_policy == "next_open":
                    exit_index = index + 1
                    if exit_index >= market.size:
                        return ExitOutcome(
                            market.size,
                            math.nan,
                            entry,
                            stop,
                            target,
                            math.nan,
                            "open",
                        )
                    exit_price = market.open[exit_index]
                else:
                    raise ValueError(
                        f"unsupported time-stop policy: {time_stop_policy}"
                    )
                gross_r = (
                    (exit_price - entry) / risk
                    if opportunity.side == 1
                    else (entry - exit_price) / risk
                )
                return ExitOutcome(
                    exit_index,
                    float(gross_r),
                    entry,
                    stop,
                    target,
                    float(exit_price),
                    f"time_stop_{time_stop_policy}",
                )
    # An unclosed final position blocks later setups but is not a closed trade.
    return ExitOutcome(
        market.size, math.nan, entry, stop, target, math.nan, "open"
    )


def _cost_in_r(outcome: ExitOutcome, fees: FeeModel) -> float:
    if math.isnan(outcome.exit_price):
        return 0.0
    risk = abs(outcome.entry - outcome.stop)
    if risk == 0:
        return 0.0
    if outcome.reason == "target":
        exit_bps = fees.target_maker_bps
    elif outcome.reason.startswith("time_stop"):
        exit_bps = fees.time_stop_taker_bps
    else:
        exit_bps = fees.stop_taker_bps
    cash_cost = (
        outcome.entry * fees.entry_taker_bps + outcome.exit_price * exit_bps
    ) / 10_000
    return float(cash_cost / risk)


def _drawdown(values: Iterable[float]) -> float:
    curve = peak = maximum = 0.0
    for value in values:
        curve += value
        peak = max(peak, curve)
        maximum = max(maximum, peak - curve)
    return maximum


def _longest_streak(values: Sequence[float], positive: bool) -> int:
    longest = current = 0
    for value in values:
        matches = value > 0 if positive else value < 0
        current = current + 1 if matches else 0
        longest = max(longest, current)
    return longest


def _fold_labels(market: MarketData, folds: int = 4) -> list[str]:
    labels: list[str] = []
    for fold in range(folds):
        start = market.times_ny.iloc[min(market.size - 1, fold * market.size // folds)]
        end_index = min(market.size - 1, (fold + 1) * market.size // folds - 1)
        end = market.times_ny.iloc[end_index]
        labels.append(f"{start.date().isoformat()}..{end.date().isoformat()}")
    return labels


def _summarize(
    market: MarketData,
    config: BaseConfig,
    stop_buffer: float,
    reward_to_risk: float,
    records: list[tuple[Opportunity, ExitOutcome, float]],
    fees: FeeModel,
    fold_count: int = 4,
) -> dict:
    r_values = [record[2] for record in records]
    wins = [value for value in r_values if value > 0]
    losses = [value for value in r_values if value < 0]
    fold_labels = _fold_labels(market, fold_count)
    fold_values: list[list[float]] = [[] for _ in fold_labels]
    for opportunity, _, net_r in records:
        fold = min(len(fold_labels) - 1, opportunity.signal_idx * len(fold_labels) // market.size)
        fold_values[fold].append(net_r)
    folds = []
    for label, values in zip(fold_labels, fold_values):
        folds.append(
            {
                "period": label,
                "trades": len(values),
                "win_rate_percent": round(
                    sum(value > 0 for value in values) / len(values) * 100, 2
                )
                if values
                else 0.0,
                "net_r": round(sum(values), 4),
            }
        )
    net_r = sum(r_values)
    max_drawdown = _drawdown(r_values)
    def equity_metrics(risk_percent: float) -> dict[str, float]:
        equity = peak_equity = 1.0
        max_equity_drawdown = 0.0
        for value in r_values:
            equity *= max(0.0, 1 + value * risk_percent / 100)
            peak_equity = max(peak_equity, equity)
            if peak_equity:
                max_equity_drawdown = max(
                    max_equity_drawdown, (peak_equity - equity) / peak_equity
                )
        return {
            "risk_percent": risk_percent,
            "final_equity_multiple": round(equity, 6),
            "return_percent": round((equity - 1) * 100, 2),
            "max_drawdown_percent": round(max_equity_drawdown * 100, 2),
        }

    annual_values: dict[int, list[float]] = {
        year: []
        for year in range(
            market.times_ny.iloc[0].year,
            market.times_ny.iloc[-1].year + 1,
        )
    }
    for opportunity, _, net_trade_r in records:
        annual_values[market.times_ny.iloc[opportunity.signal_idx].year].append(
            net_trade_r
        )
    annual = []
    for year, values in annual_values.items():
        year_wins = [value for value in values if value > 0]
        year_losses = [value for value in values if value < 0]
        annual.append(
            {
                "year": year,
                "trades": len(values),
                "win_rate_percent": round(
                    len(year_wins) / len(values) * 100, 2
                )
                if values
                else 0.0,
                "net_r": round(sum(values), 4),
                "profit_factor": round(
                    sum(year_wins) / abs(sum(year_losses)), 4
                )
                if year_losses
                else None,
            }
        )
    fold_net = [fold["net_r"] for fold in folds]
    first_half_folds = folds[: len(folds) // 2]
    second_half_folds = folds[len(folds) // 2 :]
    worst_fold = min(fold_net) if fold_net else 0.0
    stable_score = net_r - 0.75 * max_drawdown - 0.5 * (max(fold_net) - worst_fold)
    annual_net = [year["net_r"] for year in annual]
    incomplete_range_trade_dates = sorted(
        {
            market.times_ny.iloc[opportunity.signal_idx].date().isoformat()
            for opportunity, _, _ in records
            if market.times_ny.iloc[opportunity.signal_idx].date()
            not in market.complete_range_sessions
        }
    )
    annual_dispersion = float(np.std(annual_net)) if annual_net else 0.0
    robust_score = (
        net_r
        - max_drawdown
        - 0.5 * annual_dispersion
        + 2 * min(0.0, min(annual_net) if annual_net else 0.0)
    )
    return {
        "config": config.name,
        "body_mode": config.body_mode,
        "fvg_mode": config.fvg_mode,
        "direction": config.direction,
        "fib_zone": [config.fib_low, config.fib_high],
        "session_cutoff_ny": config.cutoff_hour,
        "reward_to_risk": reward_to_risk,
        "stop_buffer_percent": stop_buffer * 100,
        "fees_bps": fees.as_dict(),
        "trades": len(records),
        "long_trades": sum(record[0].side == 1 for record in records),
        "short_trades": sum(record[0].side == -1 for record in records),
        "wins": len(wins),
        "win_rate_percent": round(len(wins) / len(records) * 100, 2)
        if records
        else 0.0,
        "net_r": round(net_r, 4),
        "average_r": round(net_r / len(records), 4) if records else 0.0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 4)
        if losses
        else None,
        "max_drawdown_r": round(max_drawdown, 4),
        "longest_win_streak": _longest_streak(r_values, positive=True),
        "longest_loss_streak": _longest_streak(r_values, positive=False),
        "equity_1pct_risk": equity_metrics(1.0),
        "equity_5pct_risk": equity_metrics(5.0),
        "profitable_folds": sum(value > 0 for value in fold_net),
        "worst_fold_r": worst_fold,
        "first_half_trades": sum(fold["trades"] for fold in first_half_folds),
        "first_half_r": round(sum(fold["net_r"] for fold in first_half_folds), 4),
        "second_half_trades": sum(fold["trades"] for fold in second_half_folds),
        "second_half_r": round(sum(fold["net_r"] for fold in second_half_folds), 4),
        "stability_score": round(stable_score, 4),
        "robust_score": round(robust_score, 4),
        "profitable_years": sum(value > 0 for value in annual_net),
        "nonnegative_years": sum(value >= 0 for value in annual_net),
        "worst_year_r": min(annual_net) if annual_net else 0.0,
        "median_year_r": round(float(np.median(annual_net)), 4)
        if annual_net
        else 0.0,
        "trades_on_incomplete_ny_range": sum(
            market.times_ny.iloc[opportunity.signal_idx].date()
            not in market.complete_range_sessions
            for opportunity, _, _ in records
        ),
        "incomplete_ny_range_trade_dates": incomplete_range_trade_dates,
        "annual": annual,
        "folds": folds,
    }


def _holding_distribution(
    market: MarketData,
    records: Sequence[tuple[Opportunity, ExitOutcome, float]],
) -> dict:
    """Summarize elapsed time to the exit candle at five-minute resolution."""
    hours = np.asarray(
        [
            (
                market.times_utc.iloc[outcome.exit_idx]
                - market.times_utc.iloc[opportunity.entry_idx]
            ).total_seconds()
            / 3600
            for opportunity, outcome, _ in records
            if outcome.exit_idx < market.size
        ],
        dtype=float,
    )
    if not len(hours):
        return {"count": 0}
    boundaries = [0, 6, 24, 48, 72, 168, math.inf]
    labels = ["0-6h", "6-24h", "24-48h", "48-72h", "72-168h", ">168h"]
    buckets = {}
    for label, lower, upper in zip(labels, boundaries, boundaries[1:]):
        count = int(np.sum((hours >= lower) & (hours < upper)))
        buckets[label] = {
            "trades": count,
            "percent": round(count / len(hours) * 100, 2),
        }
    return {
        "count": int(len(hours)),
        "resolution": "exit candle timestamp, 5-minute bars",
        "mean_hours": round(float(np.mean(hours)), 3),
        "median_hours": round(float(np.median(hours)), 3),
        "p75_hours": round(float(np.percentile(hours, 75)), 3),
        "p90_hours": round(float(np.percentile(hours, 90)), 3),
        "p95_hours": round(float(np.percentile(hours, 95)), 3),
        "max_hours": round(float(np.max(hours)), 3),
        "buckets": buckets,
    }


def _collect_records(
    market: MarketData,
    config: BaseConfig,
    normal_signals: Sequence[Opportunity | None],
    stop_buffer: float,
    reward_to_risk: float,
    fees: FeeModel,
    outcome_cache: dict[
        tuple[Opportunity, float, float, float | None, str],
        ExitOutcome | None,
    ],
    time_stop_hours: float | None = None,
    time_stop_policy: str = "close",
) -> list[tuple[Opportunity, ExitOutcome, float]]:
    records: list[tuple[Opportunity, ExitOutcome, float]] = []
    busy_until = -1
    for day_index, day in enumerate(market.days):
        if busy_until > day.end_idx:
            continue
        opportunity = normal_signals[day_index]
        if day.post_start_idx <= busy_until <= day.end_idx:
            # Exact correction for a position that carried into this NY day:
            # the strategy starts looking for a fresh breakout only once flat.
            dynamic = _opportunities_from(
                market, day, config.body_mode, start_idx=busy_until
            )
            opportunity = _first_passing(dynamic, config)
        if opportunity is None or opportunity.signal_idx < busy_until:
            continue
        cache_key = (
            opportunity,
            stop_buffer,
            reward_to_risk,
            time_stop_hours,
            time_stop_policy,
        )
        if cache_key not in outcome_cache:
            outcome_cache[cache_key] = _trade_outcome(
                market,
                opportunity,
                stop_buffer,
                reward_to_risk,
                time_stop_hours,
                time_stop_policy,
            )
        outcome = outcome_cache[cache_key]
        if outcome is None:
            # Invalid next-open fill still consumes the day's setup.
            continue
        busy_until = outcome.exit_idx
        if math.isnan(outcome.gross_r):
            continue
        net_r = float(outcome.gross_r - _cost_in_r(outcome, fees))
        records.append((opportunity, outcome, net_r))
    return records


def _evaluate(
    market: MarketData,
    config: BaseConfig,
    normal_signals: Sequence[Opportunity | None],
    stop_buffer: float,
    reward_to_risk: float,
    fees: FeeModel,
    fold_count: int,
    outcome_cache: dict[
        tuple[Opportunity, float, float, float | None, str],
        ExitOutcome | None,
    ],
) -> dict:
    records = _collect_records(
        market,
        config,
        normal_signals,
        stop_buffer,
        reward_to_risk,
        fees,
        outcome_cache,
    )
    return _summarize(
        market,
        config,
        stop_buffer,
        reward_to_risk,
        records,
        fees,
        fold_count,
    )


def _preset(name: str) -> dict[str, list]:
    if name == "limited":
        return {
            "body_modes": ["full_full", "full_close", "close_full"],
            "fvg_modes": [
                "5m",
                "10m",
                "15m",
                "1h",
                "4h",
                "10m_or_15m",
                "10m_or_4h",
                "15m_or_4h",
                "10m_and_15m",
                "any",
            ],
            "directions": ["both", "long", "short"],
            "fib_zones": [(0.382, 0.5), (0.5, 0.618), (0.382, 0.618), (0.5, 0.786)],
            "cutoffs": [12.0, 16.0, 24.0],
            "rrs": [1.5, 2.0, 2.5, 3.0],
            "stop_buffers": [0.0005, 0.001],
        }
    if name == "expanded":
        return {
            "body_modes": list(BODY_MODES),
            "fvg_modes": list(FVG_SPECS),
            "directions": ["both", "long", "short"],
            "fib_zones": [
                (0.236, 0.382),
                (0.382, 0.5),
                (0.5, 0.618),
                (0.618, 0.786),
                (0.382, 0.618),
                (0.5, 0.786),
            ],
            "cutoffs": [10.0, 12.0, 14.0, 16.0, 24.0],
            "rrs": [1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
            "stop_buffers": [0.0, 0.0005, 0.001, 0.0015],
        }
    raise ValueError(f"unknown preset: {name}")


def _apply_overrides(grid: dict[str, list], args: argparse.Namespace) -> None:
    overrides = {
        "body_modes": args.body_modes,
        "fvg_modes": args.fvg_modes,
        "directions": args.directions,
        "cutoffs": args.cutoffs,
        "rrs": args.rrs,
        "stop_buffers": args.stop_buffers,
    }
    for key, value in overrides.items():
        if value is not None:
            grid[key] = value
    if args.fib_zones is not None:
        grid["fib_zones"] = args.fib_zones
    invalid_body = set(grid["body_modes"]).difference(BODY_MODES)
    invalid_fvg = set(grid["fvg_modes"]).difference(FVG_SPECS)
    invalid_direction = set(grid["directions"]).difference({"both", "long", "short"})
    if invalid_body:
        raise ValueError(f"unknown body modes: {sorted(invalid_body)}")
    if invalid_fvg:
        raise ValueError(f"unknown FVG modes: {sorted(invalid_fvg)}")
    if invalid_direction:
        raise ValueError(f"unknown directions: {sorted(invalid_direction)}")


def _write_csv(path: Path, rows: Sequence[dict]) -> None:
    fields = [
        "rank",
        "config",
        "body_mode",
        "fvg_mode",
        "direction",
        "fib_zone",
        "session_cutoff_ny",
        "reward_to_risk",
        "stop_buffer_percent",
        "trades",
        "win_rate_percent",
        "net_r",
        "average_r",
        "profit_factor",
        "max_drawdown_r",
        "profitable_folds",
        "worst_fold_r",
        "first_half_r",
        "second_half_r",
        "stability_score",
        "robust_score",
        "profitable_years",
        "worst_year_r",
        "equity_5pct_return_percent",
        "equity_5pct_max_drawdown_percent",
    ]
    fold_count = max((len(row.get("folds", [])) for row in rows), default=0)
    fields.extend(f"fold_{index}_r" for index in range(1, fold_count + 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            flat = {field: row.get(field) for field in fields}
            flat["rank"] = rank
            flat["fib_zone"] = "-".join(map(str, row["fib_zone"]))
            flat["equity_5pct_return_percent"] = row["equity_5pct_risk"][
                "return_percent"
            ]
            flat["equity_5pct_max_drawdown_percent"] = row["equity_5pct_risk"][
                "max_drawdown_percent"
            ]
            for index, fold in enumerate(row["folds"], start=1):
                flat[f"fold_{index}_r"] = fold["net_r"]
            writer.writerow(flat)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--features-file", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--report-file", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--preset", choices=("limited", "expanded"), default="limited")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--benchmark-r", type=float, default=32.0)
    parser.add_argument("--fold-count", type=int, default=4)
    parser.add_argument(
        "--require-complete-ny-range",
        action="store_true",
        help="skip sessions whose 00:00-04:00 NY source bars are not continuous",
    )
    parser.add_argument(
        "--side-cost-bps",
        type=float,
        default=0.0,
        help="commission/slippage cost per entry and exit side, in basis points",
    )
    parser.add_argument("--entry-taker-bps", type=float)
    parser.add_argument("--stop-taker-bps", type=float)
    parser.add_argument("--target-maker-bps", type=float)
    parser.add_argument("--time-stop-taker-bps", type=float)
    parser.add_argument("--body-modes", type=_csv_values)
    parser.add_argument("--fvg-modes", type=_csv_values)
    parser.add_argument("--directions", type=_csv_values)
    parser.add_argument("--fib-zones", type=_fib_values)
    parser.add_argument("--cutoffs", type=_csv_floats)
    parser.add_argument("--rrs", type=_csv_floats)
    parser.add_argument("--stop-buffers", type=_csv_floats)
    parser.add_argument(
        "--time-stops-hours",
        type=_csv_floats,
        help="optional holding-period analysis, e.g. 24,48,72,168",
    )
    parser.add_argument(
        "--time-stop-policies",
        type=_csv_values,
        default=["close", "next_open"],
        help="comma-separated close and/or next_open",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    started = time.perf_counter()
    if not args.data_file.is_file():
        raise SystemExit(f"data file not found: {args.data_file}")
    if not args.features_file.is_file():
        raise SystemExit(f"features file not found: {args.features_file}")
    if args.fold_count < 2:
        raise SystemExit("--fold-count must be at least 2")
    explicit_fees = any(
        value is not None
        for value in (
            args.entry_taker_bps,
            args.stop_taker_bps,
            args.target_maker_bps,
            args.time_stop_taker_bps,
        )
    )
    if explicit_fees:
        fees = FeeModel(
            entry_taker_bps=(
                args.entry_taker_bps
                if args.entry_taker_bps is not None
                else args.side_cost_bps
            ),
            stop_taker_bps=(
                args.stop_taker_bps
                if args.stop_taker_bps is not None
                else args.side_cost_bps
            ),
            target_maker_bps=(
                args.target_maker_bps
                if args.target_maker_bps is not None
                else args.side_cost_bps
            ),
            time_stop_taker_bps=(
                args.time_stop_taker_bps
                if args.time_stop_taker_bps is not None
                else args.side_cost_bps
            ),
        )
    else:
        fees = FeeModel.uniform(args.side_cost_bps)
    grid = _preset(args.preset)
    _apply_overrides(grid, args)
    market = _load_market(args.data_file, args.features_file)
    if args.require_complete_ny_range:
        market.days = [day for day in market.days if day.range_complete]

    body_day_opportunities: dict[tuple[str, int], list[Opportunity]] = {}
    for body_mode in grid["body_modes"]:
        for day_index, day in enumerate(market.days):
            body_day_opportunities[(body_mode, day_index)] = _opportunities_from(
                market, day, body_mode
            )

    base_configs: list[BaseConfig] = []
    base_signals: list[list[Opportunity | None]] = []
    for body_mode in grid["body_modes"]:
        for fvg_mode in grid["fvg_modes"]:
            for direction in grid["directions"]:
                for fib_low, fib_high in grid["fib_zones"]:
                    for cutoff in grid["cutoffs"]:
                        config = BaseConfig(
                            body_mode,
                            fvg_mode,
                            direction,
                            fib_low,
                            fib_high,
                            cutoff,
                        )
                        base_configs.append(config)
                        base_signals.append(
                            [
                                _first_passing(
                                    body_day_opportunities[(body_mode, day_index)],
                                    config,
                                )
                                for day_index in range(len(market.days))
                            ]
                        )

    results: list[dict] = []
    time_stop_analysis: list[dict] = []
    outcome_cache: dict[
        tuple[Opportunity, float, float, float | None, str], ExitOutcome | None
    ] = {}
    requested_configurations = (
        len(base_configs) * len(grid["stop_buffers"]) * len(grid["rrs"])
    )
    if args.time_stops_hours and requested_configurations > 100:
        raise SystemExit(
            "time-stop analysis is limited to 100 configurations; narrow the grid"
        )
    invalid_time_policies = set(args.time_stop_policies).difference(
        {"close", "next_open"}
    )
    if invalid_time_policies:
        raise SystemExit(
            f"unknown time-stop policies: {sorted(invalid_time_policies)}"
        )
    for config, normal_signals in zip(base_configs, base_signals):
        for stop_buffer in grid["stop_buffers"]:
            for reward_to_risk in grid["rrs"]:
                summary = _evaluate(
                    market,
                    config,
                    normal_signals,
                    stop_buffer,
                    reward_to_risk,
                    fees,
                    args.fold_count,
                    outcome_cache,
                )
                results.append(summary)
                if args.time_stops_hours:
                    baseline_records = _collect_records(
                        market,
                        config,
                        normal_signals,
                        stop_buffer,
                        reward_to_risk,
                        fees,
                        outcome_cache,
                    )
                    time_item = {
                        "configuration": {
                            key: summary[key]
                            for key in (
                                "config",
                                "reward_to_risk",
                                "stop_buffer_percent",
                            )
                        },
                        "baseline": summary,
                        "holding_distribution": _holding_distribution(
                            market, baseline_records
                        ),
                        "time_stops": [],
                    }
                    for policy in args.time_stop_policies:
                        for hours in args.time_stops_hours:
                            timed_records = _collect_records(
                                market,
                                config,
                                normal_signals,
                                stop_buffer,
                                reward_to_risk,
                                fees,
                                outcome_cache,
                                time_stop_hours=hours,
                                time_stop_policy=policy,
                            )
                            timed_summary = _summarize(
                                market,
                                config,
                                stop_buffer,
                                reward_to_risk,
                                timed_records,
                                fees,
                                args.fold_count,
                            )
                            timed_summary["time_stop_hours"] = hours
                            timed_summary["time_stop_policy"] = policy
                            timed_summary["time_stop_exits"] = sum(
                                outcome.reason.startswith("time_stop")
                                for _, outcome, _ in timed_records
                            )
                            time_item["time_stops"].append(timed_summary)
                    time_stop_analysis.append(time_item)

    eligible = [row for row in results if row["trades"] >= args.min_trades]
    top_net = sorted(
        eligible,
        key=lambda row: (
            row["net_r"],
            row["profitable_folds"],
            -row["max_drawdown_r"],
            row["trades"],
        ),
        reverse=True,
    )[: args.top]
    top_stable = sorted(
        eligible,
        key=lambda row: (
            row["profitable_folds"],
            row["worst_fold_r"],
            row["stability_score"],
            row["net_r"],
        ),
        reverse=True,
    )[: args.top]
    top_robust = sorted(
        eligible,
        key=lambda row: (
            row["nonnegative_years"],
            row["profitable_years"],
            row["worst_year_r"],
            row["robust_score"],
            row["net_r"],
        ),
        reverse=True,
    )[: args.top]
    # Honest chronological holdout view: configurations are ranked using only
    # the first half of folds; the remaining folds are displayed
    # but never used in this selection.
    train_minimum = max(15, args.min_trades // 2)
    holdout_candidates = [
        row for row in results if row["first_half_trades"] >= train_minimum
    ]
    holdout_selected = sorted(
        holdout_candidates,
        key=lambda row: (
            row["first_half_r"],
            min(
                fold["net_r"]
                for fold in row["folds"][: args.fold_count // 2]
            ),
            row["first_half_trades"],
        ),
        reverse=True,
    )[: args.top]

    # Expanding-window walk-forward diagnostics.  At each boundary, choose one
    # configuration solely from completed folds and expose its next-fold result.
    walk_forward = []
    for test_fold in range(1, args.fold_count):
        minimum_train_trades = max(
            10, round(args.min_trades * test_fold / args.fold_count)
        )
        candidates = [
            row
            for row in results
            if sum(fold["trades"] for fold in row["folds"][:test_fold])
            >= minimum_train_trades
        ]
        selected = max(
            candidates,
            key=lambda row: (
                sum(fold["net_r"] for fold in row["folds"][:test_fold]),
                min(fold["net_r"] for fold in row["folds"][:test_fold]),
                sum(fold["trades"] for fold in row["folds"][:test_fold]),
            ),
        )
        walk_forward.append(
            {
                "selected_config": {
                    key: selected[key]
                    for key in (
                        "config",
                        "reward_to_risk",
                        "stop_buffer_percent",
                    )
                },
                "training_folds": selected["folds"][:test_fold],
                "out_of_sample_fold": selected["folds"][test_fold],
            }
        )
    benchmark = next(
        (
            row
            for row in results
            if row["body_mode"] == "full_full"
            and row["fvg_mode"] == "10m_or_4h"
            and row["direction"] == "both"
            and row["fib_zone"] == [0.5, 0.618]
            and row["session_cutoff_ny"] == 24.0
            and row["reward_to_risk"] == 2.0
            and row["stop_buffer_percent"] == 0.1
        ),
        None,
    )
    elapsed = time.perf_counter() - started
    payload = {
        "metadata": {
            "data_file": str(args.data_file),
            "features_file": str(args.features_file),
            "data_range_utc": (
                f"{market.times_utc.iloc[0].isoformat()}.."
                f"{market.times_utc.iloc[-1].isoformat()}"
            ),
            "preset": args.preset,
            "configurations_tested": len(results),
            "base_signal_configurations": len(base_configs),
            "minimum_trades_for_ranking": args.min_trades,
            "chronological_fold_count": args.fold_count,
            "require_complete_ny_range": args.require_complete_ny_range,
            "complete_ny_range_sessions": len(market.complete_range_sessions),
            "incomplete_ny_range_sessions": len(market.incomplete_range_sessions),
            "incomplete_ny_range_session_dates": [
                value.isoformat() for value in market.incomplete_range_sessions
            ],
            "fees_bps": fees.as_dict(),
            "benchmark_threshold_r": args.benchmark_r,
            "configs_above_benchmark": int(
                sum(
                    row["trades"] >= args.min_trades
                    and row["net_r"] > args.benchmark_r
                    for row in results
                )
            ),
            "elapsed_seconds": round(elapsed, 3),
            "lookahead_policy": "FVG features available at candle close; entry next open",
            "intrabar_policy": "stop before target when both touch the same candle",
            "ranking_warning": (
                "Full-period rankings are in-sample. The chronological holdout "
                "section selects on the first half only and reports the second, "
                "but it is "
                "still a single market/window. Re-run finalists in Backtrader."
            ),
            "grid": grid,
        },
        "backtrader_benchmark_config": benchmark,
        "top_by_net_r": top_net,
        "top_by_temporal_stability": top_stable,
        "top_by_robustness": top_robust,
        "first_half_selection_second_half_holdout": holdout_selected,
        "expanding_walk_forward": walk_forward,
        "time_stop_analysis": time_stop_analysis,
    }
    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.report_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    csv_path = args.report_file.with_suffix(".csv")
    _write_csv(csv_path, top_net)
    print(
        json.dumps(
            {
                "metadata": payload["metadata"],
                "benchmark": benchmark,
                "top_by_net_r": top_net[: min(5, len(top_net))],
                "top_by_temporal_stability": top_stable[: min(5, len(top_stable))],
                "top_by_robustness": top_robust[: min(5, len(top_robust))],
                "first_half_selection_second_half_holdout": holdout_selected[
                    : min(5, len(holdout_selected))
                ],
                "expanding_walk_forward": walk_forward,
                "time_stop_analysis": time_stop_analysis,
                "report": str(args.report_file),
                "csv": str(csv_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
