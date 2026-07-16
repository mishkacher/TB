import requests


class BitunixExchange:

    BASE_URL = "https://fapi.bitunix.com"

    def get_ticker(self, symbol="BTCUSDT"):

        url = f"{self.BASE_URL}/api/v1/futures/market/tickers"

        params = {
            "symbols": symbol
        }

        response = requests.get(
            url,
            params=params
        )

        response.raise_for_status()

        return response.json()


if __name__ == "__main__":

    bitunix = BitunixExchange()

    ticker = bitunix.get_ticker()

    print(ticker)