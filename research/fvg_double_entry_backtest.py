"""Backtest a pre-close impulse entry plus a confirmed FVG retest entry."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.fibonacci import FibonacciEngine


MAKER_FEE = 0.00016
TAKER_FEE = 0.0005
STOP_SLIPPAGE = 0.0002


def aggregate_15m(minutes):
    frame = minutes.copy()
    frame["bucket"] = frame["time"].dt.floor("15min")
    return frame.groupby("bucket", sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"), count=("time", "size"),
    ).reset_index(names="time")


def exit_trade(minutes, direction, entry, stop, target, start_time):
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    entry_exec = entry
    for _, candle in minutes[minutes["time"] >= start_time].iterrows():
        if direction == "LONG":
            stopped, won = candle["low"] <= stop, candle["high"] >= target
            raw_exit = stop if stopped else target if won else None
            exit_exec = (
                raw_exit * (1 - STOP_SLIPPAGE)
                if stopped else raw_exit
            )
            gross = None if exit_exec is None else exit_exec - entry_exec
        else:
            stopped, won = candle["high"] >= stop, candle["low"] <= target
            raw_exit = stop if stopped else target if won else None
            exit_exec = (
                raw_exit * (1 + STOP_SLIPPAGE)
                if stopped else raw_exit
            )
            gross = None if exit_exec is None else entry_exec - exit_exec
        if raw_exit is not None:
            exit_fee = TAKER_FEE if stopped else MAKER_FEE
            net = gross - entry_exec * MAKER_FEE - exit_exec * exit_fee
            return {"won": not stopped, "net_r": net / risk, "net_percent": net / entry_exec * 100, "exit_time": candle["time"]}
    return None


def run(minutes, fibonacci_levels=()):
    minutes = minutes.sort_values("time").reset_index(drop=True)
    fifteen = aggregate_15m(minutes)
    first_legs, second_legs = [], []
    for position in range(6, len(fifteen)):
        current = fifteen.iloc[position]
        if current["count"] != 15:
            continue
        previous = fifteen.iloc[position - 6:position]
        if len(previous) != 6 or not previous["time"].diff().dropna().eq(pd.Timedelta(minutes=15)).all():
            continue
        bucket = current["time"]
        partial = minutes[(minutes["time"] >= bucket) & (minutes["time"] < bucket + pd.Timedelta(minutes=14))]
        if len(partial) != 14 or partial["volume"].sum() <= previous.iloc[:-1]["volume"].max():
            continue
        first, middle = previous.iloc[-2], previous.iloc[-1]
        direction = None
        if partial["low"].min() > first["high"] and current["low"] > first["high"]:
            direction, lower, upper = "LONG", float(first["high"]), float(current["low"])
            stop = float(min(first["low"], middle["low"], partial["low"].min()))
        elif partial["high"].max() < first["low"] and current["high"] < first["low"]:
            direction, lower, upper = "SHORT", float(current["high"]), float(first["low"])
            stop = float(max(first["high"], middle["high"], partial["high"].max()))
        if direction is None or current["volume"] <= previous.iloc[:-1]["volume"].max():
            continue

        if fibonacci_levels:
            fib_history = fifteen.iloc[:position - 2]
            if len(fib_history) < 7:
                continue
            try:
                fibonacci = FibonacciEngine().analyze(
                    fib_history, lookback=200, pivot_span=3
                )
            except ValueError:
                continue
            expected_direction = "BULLISH" if direction == "LONG" else "BEARISH"
            if fibonacci["direction"] != expected_direction:
                continue
            path_high = max(float(first["high"]), float(middle["high"]), float(partial["high"].max()))
            path_low = min(float(first["low"]), float(middle["low"]), float(partial["low"].min()))
            reached = any(
                path_high >= fibonacci["levels"][level]
                if direction == "LONG"
                else path_low <= fibonacci["levels"][level]
                for level in fibonacci_levels
            )
            if not reached:
                continue

        signal_minute = partial.iloc[-1]
        first_entry = float(signal_minute["close"])
        first_target = first_entry * (1.0025 if direction == "LONG" else 0.9975)
        first_stop = lower if direction == "LONG" else upper
        first_result = exit_trade(
            minutes,
            direction,
            first_entry,
            first_stop,
            first_target,
            signal_minute["time"] + pd.Timedelta(minutes=1),
        )
        if first_result:
            first_result.update({"signal_time": bucket, "direction": direction})
            first_legs.append(first_result)

        second_entry = upper if direction == "LONG" else lower
        second_risk = abs(second_entry - stop)
        if second_risk / second_entry * 100 < 0.5:
            continue
        available = bucket + pd.Timedelta(minutes=15)
        expiry = available + pd.Timedelta(hours=4)
        entry_candle = None
        for _, candle in minutes[(minutes["time"] >= available) & (minutes["time"] < expiry)].iterrows():
            touched = candle["low"] <= second_entry if direction == "LONG" else candle["high"] >= second_entry
            if touched:
                entry_candle = candle
                break
        if entry_candle is None:
            continue
        second_target = second_entry + second_risk if direction == "LONG" else second_entry - second_risk
        second_result = exit_trade(minutes, direction, second_entry, stop, second_target, entry_candle["time"])
        if second_result:
            second_result.update({"signal_time": bucket, "direction": direction})
            second_legs.append(second_result)
    return pd.DataFrame(first_legs), pd.DataFrame(second_legs)


def metrics(trades):
    if trades.empty:
        return {"trades": 0, "win_rate": 0, "net_r": 0, "avg_r": 0, "net_percent_sum": 0}
    return {
        "trades": len(trades),
        "win_rate": float(trades["won"].mean() * 100),
        "net_r": float(trades["net_r"].sum()),
        "avg_r": float(trades["net_r"].mean()),
        "net_percent_sum": float(trades["net_percent"].sum()),
    }


if __name__ == "__main__":
    data = pd.read_csv("data/historical/btcusdt_1m_preclose_test.csv", parse_dates=["time"])
    variants = (("FIB_-0.18", ("-0.18",)), ("FIB_-0.618", ("-0.618",)), ("FIB_EITHER", ("-0.18", "-0.618")))
    periods = (("MAY", "2026-05-01", "2026-06-01"), ("JUNE", "2026-06-01", "2026-07-01"), ("TOTAL", "2026-05-01", "2026-07-01"))
    for variant_name, levels in variants:
        print(variant_name)
        for name, start, end in periods:
            sample = data[(data["time"] >= start) & (data["time"] < end)].reset_index(drop=True)
            first, second = run(sample, levels)
            combined = pd.concat([first.assign(leg="PRE"), second.assign(leg="RETEST")], ignore_index=True)
            print(name, "PRE", metrics(first))
            print(name, "RETEST", metrics(second))
            print(name, "COMBINED", metrics(combined))
