"""Two-year account backtest for SMA 72/336 with fixed fractional risk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from internet_strategy_benchmark import resample_hourly


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = df["close"].shift(1)
    true_range = pd.concat(
        [(df["high"] - df["low"]), (df["high"] - previous).abs(), (df["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def run(df: pd.DataFrame, initial: float, risk_fraction: float, cost_bps: float, leverage_cap: float) -> dict:
    fast = df["close"].rolling(72).mean()
    slow = df["close"].rolling(336).mean()
    desired = (fast > slow).astype(int) - (fast < slow).astype(int)
    volatility = atr(df)
    equity, peak = initial, initial
    position = None
    blocked_direction = None
    trades, curve, capped = [], [], 0

    for i in range(336, len(df) - 1):
        target = int(desired.iloc[i])
        next_open = float(df["open"].iloc[i + 1])
        if blocked_direction is not None and target != blocked_direction:
            blocked_direction = None

        if position is not None:
            stop_hit = (position["direction"] == 1 and float(df["low"].iloc[i]) <= position["stop"]) or (
                position["direction"] == -1 and float(df["high"].iloc[i]) >= position["stop"]
            )
            reverse = target != position["direction"]
            if stop_hit or reverse:
                raw_exit = position["stop"] if stop_hit else next_open
                slip = raw_exit * cost_bps / 10_000
                exit_price = raw_exit - slip if position["direction"] == 1 else raw_exit + slip
                pnl = position["direction"] * position["quantity"] * (exit_price - position["entry"])
                equity += pnl
                trades.append({
                    "entry_time": str(position["time"]), "exit_time": str(df.index[i + 1]),
                    "direction": "LONG" if position["direction"] == 1 else "SHORT",
                    "pnl": round(pnl, 2), "return_on_equity_pct": round(pnl / position["equity_at_entry"] * 100, 2),
                    "exit_reason": "stop" if stop_hit else "crossover",
                })
                if stop_hit:
                    blocked_direction = position["direction"]
                position = None

        if position is None and target != 0 and target != blocked_direction:
            stop_distance = 2 * float(volatility.iloc[i])
            risk_budget = equity * risk_fraction
            risk_quantity = risk_budget / stop_distance
            max_quantity = equity * leverage_cap / next_open
            quantity = min(risk_quantity, max_quantity)
            capped += quantity < risk_quantity
            entry_slip = next_open * cost_bps / 10_000
            entry = next_open + entry_slip if target == 1 else next_open - entry_slip
            stop = entry - target * stop_distance
            position = {"direction": target, "entry": entry, "stop": stop, "quantity": quantity, "time": df.index[i + 1], "equity_at_entry": equity}

        peak = max(peak, equity)
        curve.append((df.index[i], equity, peak))

    if position is not None:
        raw_exit = float(df["close"].iloc[-1])
        slip = raw_exit * cost_bps / 10_000
        exit_price = raw_exit - slip if position["direction"] == 1 else raw_exit + slip
        pnl = position["direction"] * position["quantity"] * (exit_price - position["entry"])
        equity += pnl
        trades.append({"entry_time": str(position["time"]), "exit_time": str(df.index[-1]), "direction": "LONG" if position["direction"] == 1 else "SHORT", "pnl": round(pnl, 2), "return_on_equity_pct": round(pnl / position["equity_at_entry"] * 100, 2), "exit_reason": "end"})

    # Reconstruct realized-equity drawdown (conservative intratrade MTM is not available here).
    balance = initial
    peak_balance = initial
    max_dd = 0.0
    for trade in trades:
        balance += trade["pnl"]
        peak_balance = max(peak_balance, balance)
        max_dd = max(max_dd, (peak_balance - balance) / peak_balance)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    return {
        "initial_deposit_usd": initial, "final_deposit_usd": round(equity, 2),
        "net_profit_usd": round(equity - initial, 2), "return_pct": round((equity / initial - 1) * 100, 2),
        "realized_max_drawdown_pct": round(max_dd * 100, 2), "trades": len(trades),
        "wins": len(wins), "losses": len(losses), "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0,
        "stop_exits": sum(t["exit_reason"] == "stop" for t in trades), "leverage_cap_hits": capped,
        "assumptions": {"risk_per_trade_pct": risk_fraction * 100, "stop": "2 x ATR(14), fixed", "max_leverage": leverage_cap, "cost_bps_per_side": cost_bps, "signal": "SMA(72)/SMA(336), 1h"},
        "trade_log": trades,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/historical/btcusdt_5m_bitunix_2y.csv")
    parser.add_argument("--output", default="data/reports/sma_72_336_risk5_1000usd.json")
    args = parser.parse_args()
    df = resample_hourly(pd.read_csv(args.data))
    result = run(df, initial=1000, risk_fraction=0.05, cost_bps=8, leverage_cap=3)
    result["period"] = {"start": str(df.index.min()), "end": str(df.index.max())}
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "trade_log"}, indent=2))


if __name__ == "__main__":
    main()
