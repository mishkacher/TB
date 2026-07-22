import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from exchanges.bitunix import BitunixClient
from strategy_lab.historical_data import HistoricalDataLoader
from strategy_lab.historical_store import HistoricalDataStore


def main():
    parser = argparse.ArgumentParser(
        description="Download one historical Bitunix slice into a reusable CSV dataset."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--end-days-ago", type=int, default=0)
    parser.add_argument("--output")
    args = parser.parse_args()

    end = datetime.now(timezone.utc) - timedelta(days=args.end_days_ago)
    start = end - timedelta(days=args.days)
    dataframe = HistoricalDataLoader(BitunixClient()).fetch(
        args.symbol,
        args.interval,
        int(start.timestamp() * 1000),
        int(end.timestamp() * 1000),
    )
    output = args.output or (
        Path("data/historical") / f"{args.symbol.lower()}_{args.interval}.csv"
    )
    result = HistoricalDataStore().append(dataframe, output)

    print(f"Saved {len(dataframe)} candles; dataset now contains {len(result)} candles")
    print(f"Range: {result.iloc[0]['time']} — {result.iloc[-1]['time']}")
    print(f"File: {output}")


if __name__ == "__main__":
    main()
