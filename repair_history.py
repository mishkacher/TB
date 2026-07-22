import argparse

import pandas as pd

from exchanges.bitunix import BitunixClient
from strategy_lab.history_repair import HistoricalDataRepair
from strategy_lab.historical_store import HistoricalDataStore


def main():
    parser = argparse.ArgumentParser(
        description="Repair missing fixed-interval candles in a historical CSV."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--file", default="data/historical/btcusdt_15m.csv")
    parser.add_argument("--max-repairs", type=int, default=10)
    args = parser.parse_args()

    dataframe = pd.read_csv(args.file, parse_dates=["time"])
    repair = HistoricalDataRepair(BitunixClient())
    repaired, unresolved = repair.repair(
        dataframe,
        args.symbol,
        args.interval,
        max_repairs=args.max_repairs,
    )
    HistoricalDataStore().append(repaired, args.file)
    remaining = repair.missing_times(repaired, args.interval)

    print(f"Unresolved in this pass: {len(unresolved)}")
    print(f"Remaining gaps: {len(remaining)}")


if __name__ == "__main__":
    main()
