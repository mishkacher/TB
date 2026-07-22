import pandas as pd


REQUIRED_CANDLE_COLUMNS = ("time", "open", "high", "low", "close", "quoteVol")
PRICE_COLUMNS = ("open", "high", "low", "close")


def candles_to_dataframe(candles):
    """Normalize exchange klines into validated, chronological UTC OHLCV data."""
    dataframe = pd.DataFrame(candles)
    if dataframe.empty:
        raise ValueError("No candle data was returned by the exchange")

    missing = [column for column in REQUIRED_CANDLE_COLUMNS if column not in dataframe]
    if missing:
        raise ValueError(f"Candle data is missing columns: {', '.join(missing)}")

    dataframe = dataframe.loc[:, REQUIRED_CANDLE_COLUMNS].copy()
    timestamp = pd.to_numeric(dataframe["time"], errors="coerce")
    # Store UTC as timezone-naive for compatibility with historical CSV files;
    # the chart localizes it explicitly before formatting the axis.
    dataframe["time"] = pd.to_datetime(
        timestamp, unit="ms", utc=True, errors="coerce"
    ).dt.tz_localize(None)

    for column in (*PRICE_COLUMNS, "quoteVol"):
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    invalid_rows = dataframe[["time", *PRICE_COLUMNS, "quoteVol"]].isna().any(axis=1)
    if invalid_rows.any():
        raise ValueError(f"Exchange returned {int(invalid_rows.sum())} malformed candle(s)")

    invalid_values = (
        (dataframe[list(PRICE_COLUMNS)] <= 0).any(axis=1)
        | (dataframe["quoteVol"] < 0)
    )
    if invalid_values.any():
        raise ValueError(f"Exchange returned {int(invalid_values.sum())} invalid candle(s)")

    # Bitunix occasionally reports a high a fraction below the candle open (or
    # a low above it). Preserve open/close and repair the wick so every candle
    # still satisfies the OHLC envelope instead of rejecting the whole chart.
    dataframe["high"] = dataframe[["open", "high", "close"]].max(axis=1)
    dataframe["low"] = dataframe[["open", "low", "close"]].min(axis=1)

    return (
        dataframe.rename(columns={"quoteVol": "volume"})
        .sort_values("time", kind="stable")
        .drop_duplicates(subset="time", keep="last")
        .reset_index(drop=True)
    )
