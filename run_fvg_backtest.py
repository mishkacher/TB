import argparse

import pandas as pd

from strategy_lab.backtester import Backtester
from strategy_lab.fvg_entry_strategy import FvgEntryStrategy
from strategy_lab.report import BacktestReport
from strategy_lab.report_store import ReportStore
from strategy_lab.validation import StrategyValidationGate


def main():
    parser = argparse.ArgumentParser(description="Backtest the BTC 15m FVG-entry strategy.")
    parser.add_argument("--data-file", required=True)
    parser.add_argument("--month", required=True, help="calendar month in YYYY-MM form")
    parser.add_argument("--reward-to-risk", type=float, choices=(1.0, 2.0), required=True)
    parser.add_argument("--entry-mode", choices=("market", "limit"), default="limit")
    parser.add_argument("--min-impulse-percent", type=float, default=2.0)
    parser.add_argument("--impulse-lookback", type=int, default=16)
    parser.add_argument("--consolidation-candles", type=int, default=4)
    parser.add_argument("--max-consolidation-range-percent", type=float, default=0.75)
    parser.add_argument("--volume-lookback", type=int, default=5)
    parser.add_argument("--volume-multiplier", type=float, default=0.6)
    parser.add_argument("--confirmed-close-entry", action="store_true")
    parser.add_argument("--volume-only", action="store_true")
    parser.add_argument("--fee-bps-per-side", type=float, default=6.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=2.0)
    parser.add_argument("--report-file")
    args = parser.parse_args()

    dataframe = pd.read_csv(args.data_file, parse_dates=["time"])
    month = pd.Period(args.month, freq="M")
    dataframe = dataframe[dataframe["time"].dt.to_period("M") == month].reset_index(drop=True)
    if len(dataframe) < 4:
        parser.error(f"not enough candles for {month}")

    strategy = FvgEntryStrategy(
        args.reward_to_risk,
        min_impulse_percent=args.min_impulse_percent,
        impulse_lookback=args.impulse_lookback,
        consolidation_candles=args.consolidation_candles,
        max_consolidation_range_percent=args.max_consolidation_range_percent,
        entry_mode=args.entry_mode,
        volume_lookback=args.volume_lookback,
        volume_multiplier=args.volume_multiplier,
        require_context=not args.volume_only,
        enter_on_signal_close=args.confirmed_close_entry,
    )
    backtester = Backtester(
        fee_percent_per_side=args.fee_bps_per_side / 100,
        slippage_percent_per_side=args.slippage_bps_per_side / 100,
    )
    trades = backtester.run(dataframe, strategy, "BTCUSDT", warmup=3)
    report = BacktestReport().generate(trades)
    validation = StrategyValidationGate().validate(report)
    result = {
        "strategy_version": strategy.VERSION,
        "symbol": "BTCUSDT",
        "interval": "15m",
        "month": str(month),
        "reward_to_risk": args.reward_to_risk,
        "entry_mode": args.entry_mode,
        "entry_filter": {
            "min_impulse_percent": args.min_impulse_percent,
            "impulse_lookback_candles": args.impulse_lookback,
            "consolidation_candles": args.consolidation_candles,
            "max_consolidation_range_percent": args.max_consolidation_range_percent,
            "volume_lookback_candles": args.volume_lookback,
            "volume_multiplier": args.volume_multiplier,
            "volume_only": args.volume_only,
        },
        "execution_assumptions": {
            "fee_bps_per_side": args.fee_bps_per_side,
            "slippage_bps_per_side": args.slippage_bps_per_side,
            "guaranteed_stop_loss": args.slippage_bps_per_side == 0,
            "confirmed_close_entry": args.confirmed_close_entry,
        },
        "report": report,
        "validation": validation,
    }
    if args.report_file:
        ReportStore().save(result, args.report_file)

    print(f"BTCUSDT | 15m | {month} | FVG {args.entry_mode} entry | {args.reward_to_risk:g}R")
    for key, value in report.items():
        print(f"{key}: {value}")
    print(f"approved_for_signals: {validation['approved']}")


if __name__ == "__main__":
    main()
