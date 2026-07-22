import argparse
from datetime import datetime, timedelta, timezone

import pandas as pd

from exchanges.bitunix import BitunixClient
from strategy_lab.backtester import Backtester
from strategy_lab.historical_data import HistoricalDataLoader
from strategy_lab.report import BacktestReport
from strategy_lab.report_store import ReportStore
from strategy_lab.scanner_confluence_strategy import ScannerConfluenceStrategy
from strategy_lab.validation import StrategyValidationGate
from strategy_lab.walk_forward_validation import WalkForwardValidator
from strategy_lab.monthly_backtest import MonthlyBacktestRunner


def main():
    parser = argparse.ArgumentParser(
        description="Run the initial Scanner + Confluence strategy on historical data."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--report-file")
    parser.add_argument("--data-file")
    parser.add_argument(
        "--month",
        help="run one calendar month only, in YYYY-MM form",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--walk-forward",
        action="store_true",
        help="evaluate consecutive out-of-sample windows instead of one full run",
    )
    mode.add_argument(
        "--monthly",
        action="store_true",
        help="run independent calendar-month backtests and aggregate their metrics",
    )
    parser.add_argument("--train-candles", type=int, default=8640)
    parser.add_argument("--test-candles", type=int, default=2880)
    parser.add_argument(
        "--fee-bps-per-side",
        type=float,
        default=6.0,
        help="commission per entry or exit in basis points (default: 6)",
    )
    parser.add_argument(
        "--slippage-bps-per-side",
        type=float,
        default=2.0,
        help="adverse slippage per entry or exit in basis points (default: 2)",
    )
    args = parser.parse_args()

    if args.data_file:
        dataframe = pd.read_csv(args.data_file, parse_dates=["time"])
    else:
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int(
            (datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000
        )
        dataframe = HistoricalDataLoader(BitunixClient()).fetch(
            args.symbol,
            args.interval,
            start_time,
            end_time,
        )
    if args.month:
        try:
            requested_month = pd.Period(args.month, freq="M")
        except ValueError:
            parser.error("--month must use YYYY-MM, for example 2026-03")
        dataframe = dataframe[
            dataframe["time"].dt.to_period("M") == requested_month
        ].reset_index(drop=True)
        if dataframe.empty:
            parser.error(f"no candles found for {requested_month}")
    strategy = ScannerConfluenceStrategy()
    backtester = Backtester(
        fee_percent_per_side=args.fee_bps_per_side / 100,
        slippage_percent_per_side=args.slippage_bps_per_side / 100,
    )
    monthly_reports = None
    if args.walk_forward:
        result = WalkForwardValidator(
            ScannerConfluenceStrategy,
            backtester=backtester,
        ).run(
            dataframe,
            args.symbol,
            train_size=args.train_candles,
            test_size=args.test_candles,
        )
        report = result["aggregate_report"]
        validation = result["validation"]
        walk_forward_windows = result["windows"]
        outcomes_by_direction = result["outcomes_by_direction"]
    elif args.monthly:
        result = MonthlyBacktestRunner(
            ScannerConfluenceStrategy,
            backtester=backtester,
        ).run(dataframe, args.symbol)
        report = result["aggregate_report"]
        validation = result["validation"]
        walk_forward_windows = None
        monthly_reports = result["months"]
        outcomes_by_direction = result["outcomes_by_direction"]
    else:
        walk_forward_windows = None
        trades = backtester.run(
            dataframe,
            strategy,
            symbol=args.symbol,
        )
        report = BacktestReport().generate(trades)
        validation = StrategyValidationGate().validate(report)
        outcomes_by_direction = {
            "LONG": [trade.return_percent > 0 for trade in trades if trade.direction == "LONG"],
            "SHORT": [trade.return_percent > 0 for trade in trades if trade.direction == "SHORT"],
        }

    if args.report_file:
        ReportStore().save(
            {
                "strategy_version": strategy.VERSION,
                "symbol": args.symbol,
                "interval": args.interval,
                "days": args.days,
                "month": args.month,
                "report": report,
                "validation": validation,
                "walk_forward_windows": walk_forward_windows,
                "monthly_reports": monthly_reports,
                "outcomes_by_direction": outcomes_by_direction,
                "execution_assumptions": {
                    "fee_bps_per_side": args.fee_bps_per_side,
                    "slippage_bps_per_side": args.slippage_bps_per_side,
                },
            },
            args.report_file,
        )

    period = f"monthly ({len(monthly_reports)} months)" if monthly_reports is not None else (
        f"walk-forward ({len(walk_forward_windows)} windows)"
        if walk_forward_windows is not None
        else (args.month or f"{args.days} days")
    )
    print(f"{args.symbol} | {args.interval} | {period}")
    print(f"Strategy: ScannerConfluence v{strategy.VERSION}")
    if monthly_reports is not None:
        print("Month | Trades | Win rate | Profit factor | Net return")
        for item in monthly_reports:
            month_report = item["report"]
            print(
                f"{item['month']} | {month_report['trades']} | "
                f"{month_report['win_rate_percent']:.2f}% | "
                f"{month_report['profit_factor']} | "
                f"{month_report['net_return_percent']:.2f}%"
            )
    for metric, value in report.items():
        print(f"{metric}: {value}")
    print(f"approved_for_signals: {validation['approved']}")
    if validation["reasons"]:
        print("rejection_reasons:", ", ".join(validation["reasons"]))


if __name__ == "__main__":
    main()
