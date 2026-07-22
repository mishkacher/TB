"""Benchmark reproducible internet-sourced strategy families on local BTC data.

Signals are formed on an hourly close and applied from the next hourly open.
The first 70% of observations select one parameter set per family; the last
30% is a strictly untouched out-of-sample ranking period.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd


SOURCE_URLS = {
    "sma_cross": "https://doi.org/10.1111/j.1540-6261.1992.tb04681.x",
    "donchian": "https://doi.org/10.1111/j.1540-6261.1992.tb04681.x",
    "time_series_momentum": "https://doi.org/10.1016/j.jfineco.2011.11.003",
    "bollinger_reversion": "https://www.bollingerbands.com/bollinger-bands",
    "rsi_reversion": "https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI",
    "macd": "https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd",
    "bollinger_breakout": "https://www.bollingerbands.com/bollinger-bands",
}


def resample_hourly(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.copy()
    raw["time"] = pd.to_datetime(raw["time"], utc=True)
    return (
        raw.set_index("time")
        .resample("1h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )


def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def positions(df: pd.DataFrame, family: str, params: tuple) -> pd.Series:
    c = df["close"]
    if family == "sma_cross":
        fast, slow = params
        return np.sign(c.rolling(fast).mean() - c.rolling(slow).mean()).fillna(0)
    if family == "donchian":
        entry, exit_ = params
        upper = df["high"].rolling(entry).max().shift(1)
        lower = df["low"].rolling(entry).min().shift(1)
        exit_hi = df["high"].rolling(exit_).max().shift(1)
        exit_lo = df["low"].rolling(exit_).min().shift(1)
        out, state = [], 0
        for i in range(len(df)):
            if c.iloc[i] > upper.iloc[i]: state = 1
            elif c.iloc[i] < lower.iloc[i]: state = -1
            elif state == 1 and c.iloc[i] < exit_lo.iloc[i]: state = 0
            elif state == -1 and c.iloc[i] > exit_hi.iloc[i]: state = 0
            out.append(state)
        return pd.Series(out, index=df.index, dtype=float)
    if family == "time_series_momentum":
        lookback, vol_window = params
        direction = np.sign(c.pct_change(lookback))
        active = c.pct_change().rolling(vol_window).std().notna()
        return direction.where(active, 0).fillna(0)
    if family in {"bollinger_reversion", "bollinger_breakout"}:
        window, width = params
        mid = c.rolling(window).mean()
        std = c.rolling(window).std()
        z = (c - mid) / std
        if family == "bollinger_breakout":
            return pd.Series(np.where(z > width, 1, np.where(z < -width, -1, 0)), index=df.index)
        out, state = [], 0
        for value in z:
            if value < -width: state = 1
            elif value > width: state = -1
            elif (state == 1 and value >= 0) or (state == -1 and value <= 0): state = 0
            out.append(state)
        return pd.Series(out, index=df.index, dtype=float)
    if family == "rsi_reversion":
        period, threshold = params
        indicator = rsi(c, period)
        out, state = [], 0
        for value in indicator:
            if value < threshold: state = 1
            elif value > 100 - threshold: state = -1
            elif (state == 1 and value >= 50) or (state == -1 and value <= 50): state = 0
            out.append(state)
        return pd.Series(out, index=df.index, dtype=float)
    if family == "macd":
        fast, slow, signal = params
        line = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
        return np.sign(line - line.ewm(span=signal, adjust=False).mean()).fillna(0)
    raise ValueError(family)


def evaluate(df: pd.DataFrame, signal: pd.Series, cost_bps: float) -> dict:
    # Signal at close[t] controls the position entered at open[t+1].
    open_return = df["open"].shift(-1) / df["open"] - 1
    held = signal.shift(1).fillna(0)
    turnover = held.diff().abs().fillna(held.abs())
    returns = (held * open_return - turnover * cost_bps / 10_000).dropna()
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1
    trade_returns = returns.groupby((turnover > 0).cumsum()).sum()
    wins = trade_returns[trade_returns > 0].sum()
    losses = -trade_returns[trade_returns < 0].sum()
    years = len(returns) / (24 * 365.25)
    total = equity.iloc[-1] - 1 if len(equity) else 0
    sharpe = np.sqrt(24 * 365.25) * returns.mean() / returns.std() if returns.std() else 0
    return {
        "return_pct": round(total * 100, 2),
        "cagr_pct": round(((1 + total) ** (1 / years) - 1) * 100, 2) if years and total > -1 else -100,
        "max_drawdown_pct": round(-drawdown.min() * 100, 2),
        "sharpe": round(float(sharpe), 3),
        "profit_factor": round(float(wins / losses), 3) if losses else None,
        "trades": int((turnover > 0).sum()),
        "exposure_pct": round((held != 0).mean() * 100, 2),
    }


def train_score(metrics: dict) -> float:
    if metrics["trades"] < 20 or metrics["max_drawdown_pct"] <= 0:
        return -1e9
    return metrics["sharpe"] + metrics["cagr_pct"] / metrics["max_drawdown_pct"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/historical/btcusdt_5m_bitunix_2y.csv")
    parser.add_argument("--output", default="data/reports/internet_strategy_top5.json")
    parser.add_argument("--cost-bps-per-side", type=float, default=8.0)
    args = parser.parse_args()

    df = resample_hourly(pd.read_csv(args.data))
    split = int(len(df) * 0.70)
    train, test = df.iloc[:split], df.iloc[split:]
    grids = {
        "sma_cross": [(f, s) for f, s in itertools.product([12, 24, 48, 72], [96, 168, 240, 336]) if f < s],
        "donchian": list(itertools.product([24, 48, 96, 168, 240], [12, 24, 48])),
        "time_series_momentum": list(itertools.product([24, 72, 168, 336, 720], [24, 72, 168])),
        "bollinger_reversion": list(itertools.product([12, 20, 48, 72], [1.5, 2.0, 2.5])),
        "rsi_reversion": list(itertools.product([7, 14, 21, 28], [20, 25, 30, 35])),
        "macd": [(f, s, sig) for f, s, sig in itertools.product([6, 12, 24], [26, 48, 72], [5, 9, 18]) if f < s],
        "bollinger_breakout": list(itertools.product([12, 20, 48, 72], [1.0, 1.5, 2.0])),
    }
    rows = []
    for family, grid in grids.items():
        scored = []
        for params in grid:
            metrics = evaluate(train, positions(train, family, params), args.cost_bps_per_side)
            scored.append((train_score(metrics), params, metrics))
        _, best, train_metrics = max(scored, key=lambda item: item[0])
        # Compute indicators on full history, then slice, preserving warm-up context.
        full_signal = positions(df, family, best)
        test_metrics = evaluate(test, full_signal.iloc[split:], args.cost_bps_per_side)
        rows.append({"family": family, "parameters": list(best), "source": SOURCE_URLS[family], "train": train_metrics, "test": test_metrics})

    eligible = [r for r in rows if r["test"]["trades"] >= 10]
    ranked = sorted(eligible, key=lambda r: (r["test"]["sharpe"], r["test"]["return_pct"]), reverse=True)
    for rank, row in enumerate(ranked, 1): row["rank"] = rank
    payload = {
        "method": "70/30 chronological holdout; one winner per family; next-open execution",
        "data": {"symbol": "BTCUSDT", "bar": "1h", "start": str(df.index.min()), "end": str(df.index.max()), "train_end": str(train.index.max()), "test_start": str(test.index.min())},
        "cost_bps_per_side": args.cost_bps_per_side,
        "top5": ranked[:5],
        "all_families": ranked,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
