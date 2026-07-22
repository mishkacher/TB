"""Walk-forward backtest for the live high-volume FVG alert rule."""

from dataclasses import dataclass
from itertools import product

import pandas as pd


@dataclass(frozen=True)
class Variant:
    entry_depth: float
    reward_to_risk: float
    expiry_bars: int
    min_risk_percent: float


def signals(dataframe):
    dataframe = dataframe.sort_values("time").reset_index(drop=True)
    result = []
    for index in range(6, len(dataframe)):
        window = dataframe.iloc[index - 6:index + 1]
        if not window["time"].diff().dropna().eq(pd.Timedelta(minutes=15)).all():
            continue
        current = dataframe.iloc[index]
        first = dataframe.iloc[index - 2]
        if float(current["volume"]) <= float(window.iloc[:-2]["volume"].max()):
            continue
        direction = None
        if float(current["low"]) > float(first["high"]):
            direction = "LONG"
            lower, upper = float(first["high"]), float(current["low"])
            stop = float(dataframe.iloc[index - 2:index + 1]["low"].min())
        elif float(current["high"]) < float(first["low"]):
            direction = "SHORT"
            lower, upper = float(current["high"]), float(first["low"])
            stop = float(dataframe.iloc[index - 2:index + 1]["high"].max())
        if direction:
            result.append((index, direction, lower, upper, stop))
    return result


def run(dataframe, variant, fee_bps=6.0, slippage_bps=2.0, signal_list=None):
    fee = fee_bps / 10_000
    slip = slippage_bps / 10_000
    trades = []
    for signal_index, direction, lower, upper, stop in (
        signal_list if signal_list is not None else signals(dataframe)
    ):
        height = upper - lower
        entry = upper - height * variant.entry_depth if direction == "LONG" else lower + height * variant.entry_depth
        risk = entry - stop if direction == "LONG" else stop - entry
        if risk <= 0 or risk / entry * 100 < variant.min_risk_percent:
            continue
        target = entry + risk * variant.reward_to_risk if direction == "LONG" else entry - risk * variant.reward_to_risk
        entered = False
        entry_time = None
        for index in range(signal_index + 1, min(len(dataframe), signal_index + 1 + variant.expiry_bars)):
            candle = dataframe.iloc[index]
            if direction == "LONG":
                if not entered and float(candle["low"]) <= entry:
                    entered, entry_time = True, candle["time"]
                if not entered:
                    continue
                stopped = float(candle["low"]) <= stop
                won = float(candle["high"]) >= target
                exit_price = stop * (1 - slip) if stopped else target * (1 - slip) if won else None
                entry_price = entry * (1 + slip)
                gross = None if exit_price is None else (exit_price - entry_price) / risk
            else:
                if not entered and float(candle["high"]) >= entry:
                    entered, entry_time = True, candle["time"]
                if not entered:
                    continue
                stopped = float(candle["high"]) >= stop
                won = float(candle["low"]) <= target
                exit_price = stop * (1 + slip) if stopped else target * (1 + slip) if won else None
                entry_price = entry * (1 - slip)
                gross = None if exit_price is None else (entry_price - exit_price) / risk
            if exit_price is not None:
                cost_r = (entry_price + exit_price) * fee / risk
                trades.append({
                    "signal_time": dataframe.iloc[signal_index]["time"],
                    "entry_time": entry_time,
                    "exit_time": candle["time"],
                    "direction": direction,
                    "won": not stopped,
                    "net_r": gross - cost_r,
                })
                break
    return pd.DataFrame(trades)


def metrics(trades):
    if trades.empty:
        return {"trades": 0, "win_rate": 0.0, "net_r": 0.0, "avg_r": 0.0, "profit_factor": 0.0, "max_drawdown_r": 0.0}
    ordered = trades.sort_values("exit_time")
    equity = ordered["net_r"].cumsum()
    drawdown = equity - equity.cummax().clip(lower=0)
    wins = ordered.loc[ordered["net_r"] > 0, "net_r"].sum()
    losses = -ordered.loc[ordered["net_r"] < 0, "net_r"].sum()
    return {
        "trades": len(ordered),
        "win_rate": float((ordered["net_r"] > 0).mean() * 100),
        "net_r": float(ordered["net_r"].sum()),
        "avg_r": float(ordered["net_r"].mean()),
        "profit_factor": float(wins / losses) if losses else float("inf"),
        "max_drawdown_r": float(-drawdown.min()),
    }


def sweep(train, variants):
    rows = []
    signal_list = signals(train)
    for variant in variants:
        row = metrics(run(train, variant, signal_list=signal_list))
        row.update({"entry_depth": variant.entry_depth, "reward_to_risk": variant.reward_to_risk, "expiry_bars": variant.expiry_bars, "min_risk_percent": variant.min_risk_percent})
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["avg_r", "profit_factor"], ascending=False)


if __name__ == "__main__":
    source = pd.read_csv("data/historical/btcusdt_15m.csv", parse_dates=["time"])
    train = source[source["time"] < "2026-05-01"].reset_index(drop=True)
    validation = source[(source["time"] >= "2026-05-01") & (source["time"] < "2026-06-01")].reset_index(drop=True)
    test = source[(source["time"] >= "2026-06-01") & (source["time"] < "2026-07-01")].reset_index(drop=True)
    # A notification is actionable for four hours (16 x 15m candles) only.
    variants = [Variant(*values) for values in product((0.0, 0.5, 1.0), (1.0, 1.5, 2.0, 3.0), (16,), (0.25, 0.5, 0.75, 1.0))]
    ranking = sweep(train, variants)
    validation_ranking = sweep(validation, variants)
    combined = ranking.merge(
        validation_ranking,
        on=["entry_depth", "reward_to_risk", "expiry_bars", "min_risk_percent"],
        suffixes=("_train", "_validation"),
    )
    eligible = combined[
        (combined["trades_train"] >= 50)
        & (combined["trades_validation"] >= 5)
        & (combined["avg_r_train"] > 0)
        & (combined["avg_r_validation"] > 0)
    ].copy()
    if eligible.empty:
        eligible = combined[
            (combined["trades_train"] >= 50)
            & (combined["trades_validation"] >= 5)
        ].copy()
    eligible["robust_score"] = eligible[["avg_r_train", "avg_r_validation"]].min(axis=1)
    best_row = eligible.sort_values("robust_score", ascending=False).iloc[0]
    best = Variant(float(best_row.entry_depth), float(best_row.reward_to_risk), int(best_row.expiry_bars), float(best_row.min_risk_percent))
    print("TOP_TRAIN")
    print(ranking.head(10).to_string(index=False))
    print("SELECTED", best)
    print("TRAIN", metrics(run(train, best)))
    print("VALIDATION", metrics(run(validation, best)))
    print("TEST", metrics(run(test, best)))
