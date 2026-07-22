#!/usr/bin/env python3
"""Independent candle-by-candle test of the New York opening-range strategy."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from strategy_lab.ny_open_range_features import build_all_fvg_features, in_fibonacci_zone


NY = ZoneInfo("America/New_York")


def body_inside(candle, lower, upper):
    return min(candle.open, candle.close) >= lower and max(candle.open, candle.close) <= upper


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", required=True)
    parser.add_argument("--initial-capital", type=float, default=1000.0)
    parser.add_argument("--risk-percent", type=float, default=5.0)
    parser.add_argument("--report-file")
    parser.add_argument("--features-file", help="optional sparse FVG feature exchange file for Backtrader")
    parser.add_argument("--strict-fvg-invalidation", action="store_true")
    args = parser.parse_args()
    path = Path(args.data_file)
    dataframe = pd.read_csv(path, parse_dates=["time"]).sort_values("time").reset_index(drop=True)
    all_fvg = build_all_fvg_features(dataframe, strict=args.strict_fvg_invalidation)
    fvg_15m, fvg_4h = all_fvg["15m"], all_fvg["4h"]
    if args.features_file:
        feature_payload = {
            timeframe: {str(key): sorted(value) for key, value in memberships.items() if value}
            for timeframe, memberships in all_fvg.items()
        }
        feature_path = Path(args.features_file)
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        feature_path.write_text(json.dumps(feature_payload))
    dataframe["ny_time"] = dataframe["time"].dt.tz_localize(timezone.utc).dt.tz_convert(NY)

    session_date = None
    range_high = range_low = None
    breakout = None
    pending = position = None
    trades = []

    for candle in dataframe.itertuples(index=False):
        now = candle.ny_time
        if now.date() != session_date:
            session_date = now.date()
            range_high = range_low = None
            breakout = None

        # Market entry sent on prior 5m close fills at this candle's open.
        if pending is not None:
            entry = float(candle.open)
            stop = pending["stop"]
            direction = pending["direction"]
            valid = stop < entry if direction == "LONG" else stop > entry
            if valid:
                risk = abs(entry - stop)
                position = {
                    **pending,
                    "entry": entry,
                    "risk": risk,
                    "target": entry + risk * 2 if direction == "LONG" else entry - risk * 2,
                }
            pending = None

        # Conservative OHLC convention: if both stop and target are touched,
        # the stop is counted first because their intrabar sequence is unknown.
        if position is not None:
            if position["direction"] == "LONG":
                if candle.low <= position["stop"]:
                    exit_price, reason = position["stop"], "stop"
                elif candle.high >= position["target"]:
                    exit_price, reason = position["target"], "target"
                else:
                    exit_price = reason = None
            else:
                if candle.high >= position["stop"]:
                    exit_price, reason = position["stop"], "stop"
                elif candle.low <= position["target"]:
                    exit_price, reason = position["target"], "target"
                else:
                    exit_price = reason = None
            if exit_price is not None:
                r_multiple = -1.0 if reason == "stop" else 2.0
                trades.append({
                    "entry_time_ny": position["entry_time_ny"],
                    "close_time_ny": now.isoformat(),
                    "direction": position["direction"],
                    "entry": round(position["entry"], 4),
                    "stop": round(position["stop"], 4),
                    "target": round(position["target"], 4),
                    "fvg_15m": position["fvg_15m"],
                    "fvg_4h": position["fvg_4h"],
                    "r_multiple": r_multiple,
                })
                position = None

        # First closed New York 4H candle: 00:00 through 03:55.
        if now.hour < 4:
            range_high = candle.high if range_high is None else max(range_high, candle.high)
            range_low = candle.low if range_low is None else min(range_low, candle.low)
            continue
        if range_high is None or position is not None or pending is not None or breakout == "TRADED":
            continue

        body_low, body_high = min(candle.open, candle.close), max(candle.open, candle.close)
        if breakout is None:
            if body_high < range_low:
                breakout = {"side": "LOW", "wick": candle.low}
            elif body_low > range_high:
                breakout = {"side": "HIGH", "wick": candle.high}
            continue

        if breakout["side"] == "LOW":
            breakout["wick"] = min(breakout["wick"], candle.low)
        else:
            breakout["wick"] = max(breakout["wick"], candle.high)
        if not body_inside(candle, range_low, range_high):
            continue

        if breakout["side"] == "LOW":
            direction, fvg_direction = "LONG", "bullish"
            stop = breakout["wick"] * 0.999
        else:
            direction, fvg_direction = "SHORT", "bearish"
            stop = breakout["wick"] * 1.001
        has_15m = fvg_direction in fvg_15m.get(candle.time, set())
        has_4h = fvg_direction in fvg_4h.get(candle.time, set())
        if not (has_15m or has_4h):
            continue
        if not in_fibonacci_zone(float(candle.close), range_low, range_high, direction):
            continue
        pending = {
            "direction": direction,
            "stop": stop,
            "entry_time_ny": now.isoformat(),
            "fvg_15m": has_15m,
            "fvg_4h": has_4h,
        }
        breakout = "TRADED"

    longs = [trade for trade in trades if trade["direction"] == "LONG"]
    shorts = [trade for trade in trades if trade["direction"] == "SHORT"]
    wins = [trade for trade in trades if trade["r_multiple"] > 0]
    losses = [trade for trade in trades if trade["r_multiple"] < 0]
    win_rate = lambda items: sum(item["r_multiple"] > 0 for item in items) / len(items) * 100 if items else 0
    curve = peak = drawdown = 0.0
    for trade in trades:
        curve += trade["r_multiple"]
        peak = max(peak, curve)
        drawdown = max(drawdown, peak - curve)
    equity = peak_equity = args.initial_capital
    max_equity_drawdown = 0.0
    for trade in trades:
        equity *= 1 + trade["r_multiple"] * args.risk_percent / 100
        peak_equity = max(peak_equity, equity)
        max_equity_drawdown = max(max_equity_drawdown, (peak_equity - equity) / peak_equity * 100)
    summary = {
        "data_range_utc": f"{dataframe.time.iloc[0]} — {dataframe.time.iloc[-1]}",
        "trades": len(trades),
        "long_trades": len(longs),
        "short_trades": len(shorts),
        "win_rate_percent": round(win_rate(trades), 2),
        "long_win_rate_percent": round(win_rate(longs), 2),
        "short_win_rate_percent": round(win_rate(shorts), 2),
        "net_r": round(sum(item["r_multiple"] for item in trades), 2),
        "average_r": round(sum(item["r_multiple"] for item in trades) / len(trades), 4) if trades else 0,
        "profit_factor": round(sum(item["r_multiple"] for item in wins) / abs(sum(item["r_multiple"] for item in losses)), 4) if losses else None,
        "max_drawdown_r": round(drawdown, 2),
        "initial_capital_usdt": args.initial_capital,
        "risk_percent_per_trade": args.risk_percent,
        "final_capital_usdt": round(equity, 2),
        "pnl_usdt": round(equity - args.initial_capital, 2),
        "portfolio_return_percent": round((equity / args.initial_capital - 1) * 100, 2),
        "portfolio_max_drawdown_percent": round(max_equity_drawdown, 2),
        "both_fvg_trades": sum(x["fvg_15m"] and x["fvg_4h"] for x in trades),
        "assumptions": {
            "timezone": "America/New_York",
            "first_4h_range": "00:00-04:00 NY",
            "signal": "full 5m body outside, then full body back inside",
            "fvg": "entry close in an active direction-aligned 15m or 4h three-candle FVG",
            "fibonacci": "entry close in 0.50-0.618 retracement of the first NY 4H range",
            "entry": "next 5m open",
            "stop": "extreme breakout wick plus/minus 0.1%",
            "target": "2R",
            "intrabar": "stop first when stop and target occur in the same candle",
            "commission": 0,
            "slippage": 0,
        },
    }
    by_month = defaultdict(list)
    for trade in trades:
        by_month[trade["entry_time_ny"][:7]].append(trade)
    monthly = []
    for month, items in sorted(by_month.items()):
        month_wins = sum(x["r_multiple"] > 0 for x in items)
        net_r = sum(x["r_multiple"] for x in items)
        monthly.append({
            "month": month,
            "trades": len(items),
            "wins": month_wins,
            "win_rate_percent": round(month_wins / len(items) * 100, 2),
            "net_r": round(net_r, 2),
        })
    report = {"monthly": monthly, "overall": summary, "trades": trades}
    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
