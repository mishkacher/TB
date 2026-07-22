import argparse

import pandas as pd

from strategy_lab.backtester import Backtester
from strategy_lab.orderflow_fibonacci_strategy import OrderflowFibonacciStrategy
from strategy_lab.report import BacktestReport
from strategy_lab.report_store import ReportStore
from strategy_lab.validation import StrategyValidationGate


def main():
    parser = argparse.ArgumentParser(description="Backtest 15m order-flow Fibonacci strategy.")
    parser.add_argument("--data-file", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--pivot-left", type=int, default=4)
    parser.add_argument("--pivot-right", type=int, default=4)
    parser.add_argument("--min-impulse-percent", type=float, default=1.0)
    parser.add_argument("--take-profit-extension", type=float, default=0.23)
    parser.add_argument("--entry-retracement", type=float, default=0.5)
    parser.add_argument("--direction", choices=("both", "long", "short"), default="both")
    parser.add_argument("--monthly-trend-filter", action="store_true")
    parser.add_argument("--breakeven-level", type=float)
    parser.add_argument("--runner-take-profit-extension", type=float, default=0.5)
    parser.add_argument("--partial-close-fraction", type=float, default=0.8)
    parser.add_argument("--fee-bps-per-side", type=float, default=6.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=2.0)
    parser.add_argument("--report-file")
    args = parser.parse_args()

    dataframe = pd.read_csv(args.data_file, parse_dates=["time"]).sort_values("time")
    month = pd.Period(args.month, freq="M")
    if args.monthly_trend_filter:
        test_start = month.start_time
        dataframe = dataframe[dataframe["time"] < month.end_time].reset_index(drop=True)
        start_index = int(dataframe.index[dataframe["time"] >= test_start][0])
    else:
        dataframe = dataframe[dataframe["time"].dt.to_period("M") == month].reset_index(drop=True)
        start_index = None
    strategy = OrderflowFibonacciStrategy(
        pivot_left=args.pivot_left,
        pivot_right=args.pivot_right,
        min_impulse_percent=args.min_impulse_percent,
        take_profit_extension=args.take_profit_extension,
        entry_retracement=args.entry_retracement,
        direction=args.direction,
        monthly_trend_filter=args.monthly_trend_filter,
        breakeven_level=args.breakeven_level,
        runner_take_profit_extension=args.runner_take_profit_extension,
        partial_close_fraction=args.partial_close_fraction,
    )
    trades = Backtester(
        fee_percent_per_side=args.fee_bps_per_side / 100,
        slippage_percent_per_side=args.slippage_bps_per_side / 100,
    ).run(
        dataframe, strategy, "BTCUSDT", warmup=strategy.minimum_history,
        start_index=(start_index + 1) if start_index is not None else None,
    )
    report = BacktestReport().generate(trades)
    result = {
        "strategy_version": strategy.VERSION,
        "symbol": "BTCUSDT",
        "interval": "15m",
        "month": str(month),
        "rules": {
            "impulse": "confirmed 15m swing low-to-high or high-to-low",
            "entry": f"{args.entry_retracement:g} Fibonacci retracement limit",
            "direction": args.direction,
            "monthly_trend_filter": args.monthly_trend_filter,
            "monthly_trend": strategy.monthly_directions.get(str(month)),
            "breakeven_trigger": (
                f"{args.breakeven_level:g} Fibonacci level"
                if args.breakeven_level is not None else None
            ),
            "partial_take_profit": f"{args.partial_close_fraction * 100:g}% at -{args.take_profit_extension:g}; remainder at -{args.runner_take_profit_extension:g}",
            "take_profit": f"-{args.take_profit_extension:g} Fibonacci extension",
            "stop_loss": "impulse low/high without buffer",
            "limit_order_expiry_candles": strategy.limit_order_expiry_candles,
            "pivot_left": args.pivot_left,
            "pivot_right": args.pivot_right,
            "min_impulse_percent": args.min_impulse_percent,
        },
        "execution_assumptions": {
            "fee_bps_per_side": args.fee_bps_per_side,
            "slippage_bps_per_side": args.slippage_bps_per_side,
        },
        "report": report,
        "validation": StrategyValidationGate().validate(report),
    }
    if args.report_file:
        ReportStore().save(result, args.report_file)
    print(f"BTCUSDT | 15m order-flow Fibonacci | {month}")
    for key, value in report.items():
        print(f"{key}: {value}")
    print(f"approved_for_signals: {result['validation']['approved']}")


if __name__ == "__main__":
    main()
