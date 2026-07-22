from analysis.candles import candles_to_dataframe


class HistoricalDataLoader:
    """Convert raw exchange history into a chronological backtest data set."""

    def __init__(self, exchange_client):
        self.exchange_client = exchange_client

    def fetch(self, symbol, interval, start_time, end_time):
        candles = self.exchange_client.get_historical_candles(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )

        if not candles:
            raise ValueError("No historical candles were returned")

        return candles_to_dataframe(candles).sort_values("time").reset_index(
            drop=True
        )
