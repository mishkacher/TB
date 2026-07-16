import requests


class BitunixClient:

    BASE_URL = "https://fapi.bitunix.com"

    def __init__(self):
        pass


    def get_candles(self, symbol="BTCUSDT", interval="15m", limit=100):

        url = f"{self.BASE_URL}/api/v1/futures/market/kline"

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }

        response = requests.get(
            url,
            params=params
        )

        data = response.json()

        return data