import pandas as pd

from analysis.candles import candles_to_dataframe
from strategy_lab.historical_store import HistoricalDataStore


class HistoricalDataRepair:
    """Restore missing fixed-interval candles in an existing historical dataset."""

    def __init__(self, exchange_client, store=None):
        self.exchange_client = exchange_client
        self.store = store or HistoricalDataStore()

    def missing_times(self, dataframe, interval):
        interval_delta = pd.Timedelta(interval)
        times = pd.to_datetime(dataframe["time"]).sort_values().reset_index(
            drop=True
        )
        missing = []

        for previous, current in zip(times, times.iloc[1:]):
            next_expected = previous + interval_delta
            while next_expected < current:
                missing.append(next_expected)
                next_expected += interval_delta

        return missing

    def repair(self, dataframe, symbol, interval, max_repairs=None):
        missing = self.missing_times(dataframe, interval)
        if max_repairs is not None:
            missing = missing[:max_repairs]

        recovered = []
        unresolved = []
        interval_delta = pd.Timedelta(interval)

        for missing_time in missing:
            end_time = int((missing_time + interval_delta).value // 1_000_000)
            response = self.exchange_client.get_candles(
                symbol=symbol,
                interval=interval,
                limit=10,
                end_time=end_time,
            )
            target_time = int(missing_time.value // 1_000_000)
            candles = [
                candle
                for candle in response.get("data", [])
                if int(candle["time"]) == target_time
            ]

            if candles:
                recovered.extend(candles)
            else:
                unresolved.append(missing_time)

        if recovered:
            repaired = pd.concat(
                [dataframe, candles_to_dataframe(recovered)],
                ignore_index=True,
            )
            repaired = (
                repaired.drop_duplicates(subset=["time"])
                .sort_values("time")
                .reset_index(drop=True)
            )
        else:
            repaired = dataframe.copy()

        return repaired, unresolved
