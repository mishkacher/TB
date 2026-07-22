from exchanges.bitunix import BitunixClient


class MarketData:

    def __init__(self):
        self.exchange = BitunixClient()


    def get_price(self, symbol="BTCUSDT"):

        ticker = self.exchange.get_ticker(symbol)

        return {
            "symbol": ticker["symbol"],
            "price": float(ticker["lastPrice"]),
            "high": float(ticker["high"]),
            "low": float(ticker["low"]),
            "volume": float(ticker["quoteVol"])
        }


if __name__ == "__main__":

    market = MarketData()

    btc = market.get_price()

    print(btc)
