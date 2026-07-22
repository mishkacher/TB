import argparse
import json
from pathlib import Path

from strategy_lab.monthly_report_aggregate import MonthlyReportAggregator


def main():
    parser = argparse.ArgumentParser(
        description="Combine previously saved one-month backtest reports."
    )
    parser.add_argument("reports", nargs="+", help="paths to monthly JSON reports")
    parser.add_argument("--output")
    args = parser.parse_args()

    result = MonthlyReportAggregator().aggregate(args.reports)
    if args.output:
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
