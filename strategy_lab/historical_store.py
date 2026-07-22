from pathlib import Path

import pandas as pd


class HistoricalDataStore:
    """Append chronological historical data without duplicate candles."""

    def append(self, dataframe, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            existing = pd.read_csv(path, parse_dates=["time"])
            dataframe = pd.concat([existing, dataframe], ignore_index=True)

        result = (
            dataframe.drop_duplicates(subset=["time"])
            .sort_values("time")
            .reset_index(drop=True)
        )
        result.to_csv(path, index=False)
        return result
