import pandas as pd

from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange



def add_indicators(df):

    df = df.copy()


    # EMA
    df["ema50"] = EMAIndicator(
        close=df["close"],
        window=50
    ).ema_indicator()


    df["ema200"] = EMAIndicator(
        close=df["close"],
        window=200
    ).ema_indicator()


    # RSI
    df["rsi"] = RSIIndicator(
        close=df["close"],
        window=14
    ).rsi()


    # ATR
    atr = AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["atr"] = atr.average_true_range()


    return df