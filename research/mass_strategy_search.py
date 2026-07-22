"""Search hundreds of rule configurations without ranking on the final holdout."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

from internet_strategy_benchmark import SOURCE_URLS, evaluate, positions, resample_hourly


def grids() -> dict[str, list[tuple]]:
    return {
        "sma_cross": [(f, s) for f, s in itertools.product([6, 12, 18, 24, 36, 48, 72, 96], [72, 96, 120, 168, 240, 336, 480, 720]) if f < s],
        "donchian": [(e, x) for e, x in itertools.product([12, 18, 24, 36, 48, 72, 96, 120, 168, 240, 336, 480], [6, 12, 18, 24, 36, 48, 72]) if x < e],
        "time_series_momentum": list(itertools.product([6, 12, 24, 48, 72, 120, 168, 240, 336, 480, 720, 1440], [12, 24, 72, 168])),
        "bollinger_reversion": list(itertools.product([10, 12, 16, 20, 24, 36, 48, 72, 96], [1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0])),
        "rsi_reversion": list(itertools.product([5, 7, 10, 14, 21, 28, 42], [15, 20, 25, 30, 35, 40])),
        "macd": [(f, s, sig) for f, s, sig in itertools.product([4, 6, 8, 12, 18, 24, 36], [18, 26, 36, 48, 72, 96, 144], [3, 5, 9, 12, 18, 24]) if f < s],
        "bollinger_breakout": list(itertools.product([10, 12, 16, 20, 24, 36, 48, 72, 96], [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5])),
    }


def directional(signal: pd.Series, mode: str) -> pd.Series:
    if mode == "long_only":
        return signal.clip(lower=0)
    if mode == "short_only":
        return signal.clip(upper=0)
    return signal


def score(m: dict) -> float:
    if m["trades"] < 12 or m["max_drawdown_pct"] <= 0:
        return -1e9
    calmar = m["cagr_pct"] / m["max_drawdown_pct"]
    return m["sharpe"] + 0.35 * calmar


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/historical/btcusdt_5m_bitunix_2y.csv")
    parser.add_argument("--output", default="data/reports/mass_strategy_top5.json")
    parser.add_argument("--cost-bps-per-side", type=float, default=8.0)
    args = parser.parse_args()

    df = resample_hourly(pd.read_csv(args.data))
    first, second = int(len(df) * 0.50), int(len(df) * 0.75)
    train, validation, test = df.iloc[:first], df.iloc[first:second], df.iloc[second:]
    candidates = []
    family_grids = grids()
    raw_count = sum(len(values) for values in family_grids.values()) * 3

    # Stage 1: parameters may see only the first half.
    for family, variants in family_grids.items():
        for params in variants:
            base = positions(train, family, params)
            for mode in ("long_short", "long_only", "short_only"):
                metrics = evaluate(train, directional(base, mode), args.cost_bps_per_side)
                candidates.append({"family": family, "parameters": list(params), "mode": mode, "train": metrics, "train_score": score(metrics)})

    # Only a fixed train-selected fraction reaches validation.
    candidates.sort(key=lambda row: row["train_score"], reverse=True)
    validation_pool = candidates[: max(100, len(candidates) // 5)]
    for row in validation_pool:
        signal = directional(positions(df.iloc[:second], row["family"], tuple(row["parameters"])), row["mode"])
        row["validation"] = evaluate(validation, signal.iloc[first:], args.cost_bps_per_side)
        row["validation_score"] = score(row["validation"])

    # Rank without looking at test. Require positive results in both development segments.
    qualified = [r for r in validation_pool if r["train"]["return_pct"] > 0 and r["validation"]["return_pct"] > 0]
    qualified.sort(key=lambda r: (min(r["train_score"], r["validation_score"]), r["validation_score"]), reverse=True)

    # Keep at most two variants from a family, preventing a cosmetically duplicated top five.
    selected, family_counts = [], {}
    for row in qualified:
        if family_counts.get(row["family"], 0) >= 2:
            continue
        selected.append(row)
        family_counts[row["family"]] = family_counts.get(row["family"], 0) + 1
        if len(selected) == 5:
            break

    # Stage 3: the selected five are evaluated once on the untouched final quarter.
    for selection_rank, row in enumerate(selected, 1):
        full_signal = directional(positions(df, row["family"], tuple(row["parameters"])), row["mode"])
        row["test"] = evaluate(test, full_signal.iloc[second:], args.cost_bps_per_side)
        row["development_rank"] = selection_rank
        row["source"] = SOURCE_URLS[row["family"]]
        row.pop("train_score", None)
        row.pop("validation_score", None)

    # Ordering the already frozen set by test performance does not alter selection.
    selected.sort(key=lambda row: (row["test"]["sharpe"], row["test"]["return_pct"]), reverse=True)
    for rank, row in enumerate(selected, 1):
        row["rank"] = rank

    payload = {
        "method": "50% train / 25% validation / 25% untouched test; test never used for selection",
        "searched_configurations": raw_count,
        "validation_pool": len(validation_pool),
        "qualified_on_train_and_validation": len(qualified),
        "cost_bps_per_side": args.cost_bps_per_side,
        "data": {"symbol": "BTCUSDT", "bar": "1h", "start": str(df.index.min()), "end": str(df.index.max()), "train_end": str(train.index.max()), "validation_end": str(validation.index.max()), "test_start": str(test.index.min())},
        "top5": selected,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
