from exchange.bitunix import BitunixExchange


class MarketData:

    def __init__(self):
        self.exchange = BitunixExchange()


    def get_price(self, symbol="BTCUSDT"):

        data = self.exchange.get_ticker(symbol)

        ticker = data["data"][0]

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