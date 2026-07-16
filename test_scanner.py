from exchanges.bitunix import BitunixClient
from analysis.candles import candles_to_dataframe
from scanner.market_scanner import MarketScanner
from analysis.indicators import add_indicators

# получаем свечи
client = BitunixClient()

response = client.get_candles(
    "BTCUSDT",
    "15m",
    300
)


candles = response["data"]


# переводим в DataFrame
df = candles_to_dataframe(candles)
df = add_indicators(df)

# запускаем сканер
scanner = MarketScanner()


result = scanner.analyze(df)


print("BTCUSDT Market Scanner")
print("----------------------")

for key, value in result.items():
    print(key, ":", value)