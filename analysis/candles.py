import pandas as pd


def candles_to_dataframe(candles):

    df = pd.DataFrame(candles)

    # переводим timestamp в число
    df["time"] = df["time"].astype("int64")

    # переводим миллисекунды в дату
    df["time"] = pd.to_datetime(
        df["time"],
        unit="ms"
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "quoteVol"
    ]

    for col in numeric_columns:
        df[col] = df[col].astype(float)

    df = df.rename(
        columns={
            "quoteVol": "volume"
        }
    )

    df = df[
        [
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]
    ]

    return df