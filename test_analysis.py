from analysis.analysis import AnalysisEngine
from analysis.candles import candles_to_dataframe
from exchanges.bitunix import BitunixClient


client = BitunixClient()
response = client.get_candles("BTCUSDT", "15m", 300)
df = candles_to_dataframe(response["data"])

result = AnalysisEngine().analyze(df)

print("BTCUSDT Analysis")
print("----------------")
print("Structure:", result["market_structure"])
print("Current price:", result["current_price"])
print("Nearest Fibonacci:", result["nearest_fibonacci_level"])
print("FVG count:", len(result["fair_value_gaps"]))
