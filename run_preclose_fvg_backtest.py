"""Backtest the BTC 15m FVG idea entered one minute before candle close.

The signal is evaluated after the first 14 one-minute candles of the third
15-minute candle.  It therefore does not use the final minute to decide entry.
"""

import argparse
from pathlib import Path

import pandas as pd

from strategy_lab.backtester import Backtester
from strategy_lab.models import TradeSignal
from strategy_lab.report import BacktestReport
from strategy_lab.report_store import ReportStore
from strategy_lab.validation import StrategyValidationGate


def _fifteen_minute_candles(minutes):
    frame = minutes.copy()
    frame["bucket"] = frame["time"].dt.floor("15min")
    return frame.groupby("bucket", sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
    ).reset_index(names="time")


class PrecloseFvgStrategy:
    """One-minute execution for a forming 15m three-candle FVG."""

    VERSION = "fvg-preclose-0.1.0"
    enter_on_signal_close = True

    def __init__(self, reward_to_risk, volume_lookback=20, volume_multiplier=1.5):
        self.reward_to_risk = reward_to_risk
        self.volume_lookback = volume_lookback
        self.volume_multiplier = volume_multiplier
        self.dataframe = None

    def prepare(self, dataframe):
        self.dataframe = dataframe.reset_index(drop=True)
        self.fifteen = _fifteen_minute_candles(self.dataframe)

    def generate_at(self, index):
        # Evaluate strictly at 14:00 of each 15m candle: index minute is 13.
        row = self.dataframe.iloc[index]
        if row["time"].minute % 15 != 13:
            return None
        bucket = row["time"].floor("15min")
        positions = self.fifteen.index[self.fifteen["time"] == bucket]
        if len(positions) != 1:
            return None
        third_position = int(positions[0])
        if third_position < self.volume_lookback + 2:
            return None

        first = self.fifteen.iloc[third_position - 2]
        # Only the first 14 completed minutes of the third candle are visible.
        partial = self.dataframe[
            (self.dataframe["time"] >= bucket)
            & (self.dataframe["time"] <= row["time"])
        ]
        if len(partial) != 14:
            return None
        partial_high = float(partial["high"].max())
        partial_low = float(partial["low"].min())
        partial_volume = float(partial["volume"].sum())
        average_volume = float(
            self.fifteen.iloc[
                third_position - self.volume_lookback:third_position
            ]["volume"].mean()
        )
        required_volume = (
            average_volume * self.volume_multiplier * 14 / 15
        )
        if partial_volume < required_volume:
            return None

        if partial_low > float(first["high"]):
            return TradeSignal(
                "LONG", stop_loss=float(first["high"]),
                reward_to_risk=self.reward_to_risk,
            )
        if partial_high < float(first["low"]):
            return TradeSignal(
                "SHORT", stop_loss=float(first["low"]),
                reward_to_risk=self.reward_to_risk,
            )
        return None


def main():
    parser = argparse.ArgumentParser(description="Backtest 15m FVG one minute before close.")
    parser.add_argument("--data-file", required=True)
    parser.add_argument("--month", action="append", required=True, help="YYYY-MM; repeat for each month")
    parser.add_argument("--reward-to-risk", type=float, choices=(1.0, 2.0), required=True)
    parser.add_argument("--volume-lookback", type=int, default=20)
    parser.add_argument("--volume-multiplier", type=float, default=1.5)
    parser.add_argument("--fee-bps-per-side", type=float, default=6.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=2.0)
    parser.add_argument("--report-file")
    args = parser.parse_args()

    frame = pd.read_csv(args.data_file, parse_dates=["time"]).sort_values("time")
    selected = frame[frame["time"].dt.to_period("M").isin(pd.Period(m, "M") for m in args.month)].reset_index(drop=True)
    strategy = PrecloseFvgStrategy(args.reward_to_risk, args.volume_lookback, args.volume_multiplier)
    trades = Backtester(args.fee_bps_per_side / 100, args.slippage_bps_per_side / 100).run(
        selected, strategy, "BTCUSDT", warmup=1
    )
    report = BacktestReport().generate(trades)
    result = {
        "strategy_version": strategy.VERSION, "symbol": "BTCUSDT", "signal_interval": "15m",
        "execution_interval": "1m", "months": args.month, "reward_to_risk": args.reward_to_risk,
        "entry_rule": "At 14:00 of the forming 15m candle, enter at its current 1m close if outer candles already do not overlap.",
        "volume_rule": f"First 14 minutes volume >= {args.volume_multiplier:g}x average prior {args.volume_lookback} completed 15m candle volumes scaled by 14/15.",
        "execution_assumptions": {"fee_bps_per_side": args.fee_bps_per_side, "slippage_bps_per_side": args.slippage_bps_per_side},
        "report": report, "validation": StrategyValidationGate().validate(report),
    }
    if args.report_file:
        ReportStore().save(result, Path(args.report_file))
    print(f"BTCUSDT | 15m FVG, entry at 14th minute | {', '.join(args.month)} | {args.reward_to_risk:g}R")
    for key, value in report.items(): print(f"{key}: {value}")
    print(f"approved_for_signals: {result['validation']['approved']}")


if __name__ == "__main__":
    main()
