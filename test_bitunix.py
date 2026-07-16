from exchanges.bitunix import BitunixClient
from analysis.candles import candles_to_dataframe


client = BitunixClient()


response = client.get_candles(
    "BTCUSDT",
    "15m",
    10
)


candles = response["data"]


df = candles_to_dataframe(candles)


print(df)