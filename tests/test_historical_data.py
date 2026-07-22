import unittest
from tempfile import TemporaryDirectory

import pandas as pd

from exchanges.bitunix import BitunixClient
from strategy_lab.historical_data import HistoricalDataLoader
from strategy_lab.historical_store import HistoricalDataStore
from strategy_lab.history_repair import HistoricalDataRepair


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse({"data": []})


class HistoricalBitunixClient(BitunixClient):
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def get_candles(self, **kwargs):
        self.calls.append(kwargs)
        return {"data": next(self.pages, [])}


class BitunixClientTests(unittest.TestCase):
    def test_forwards_historical_time_bounds(self):
        session = FakeSession()
        client = BitunixClient(session=session)

        client.get_candles(
            "BTCUSDT",
            "1h",
            10,
            start_time=100,
            end_time=200,
        )

        self.assertEqual(session.calls[0]["params"]["startTime"], 100)
        self.assertEqual(session.calls[0]["params"]["endTime"], 200)

    def test_returns_first_ticker_for_symbol(self):
        class TickerSession:
            def get(self, url, params, timeout):
                return FakeResponse(
                    {"data": [{"symbol": "BTCUSDT", "lastPrice": "100"}]}
                )

        ticker = BitunixClient(session=TickerSession()).get_ticker("BTCUSDT")

        self.assertEqual(ticker["symbol"], "BTCUSDT")

    def test_returns_current_funding_rate(self):
        class FundingSession:
            def get(self, url, params, timeout):
                return FakeResponse(
                    {
                        "data": [
                            {
                                "symbol": "BTCUSDT",
                                "fundingRate": "0.0005",
                                "fundingInterval": 8,
                                "nextFundingTime": "1",
                            }
                        ]
                    }
                )

        rate = BitunixClient(session=FundingSession()).get_funding_rate("BTCUSDT")

        self.assertEqual(rate["fundingRate"], "0.0005")

    def test_accepts_object_funding_rate_format(self):
        class FundingSession:
            def get(self, url, params, timeout):
                return FakeResponse(
                    {
                        "data": {
                            "symbol": "BTCUSDT",
                            "fundingRate": "0.0005",
                        }
                    }
                )

        rate = BitunixClient(session=FundingSession()).get_funding_rate("BTCUSDT")

        self.assertEqual(rate["symbol"], "BTCUSDT")

    def test_paginates_backward_and_returns_chronological_unique_candles(self):
        client = HistoricalBitunixClient(
            [
                [{"time": "300"}, {"time": "200"}],
                [{"time": "200"}, {"time": "100"}],
            ]
        )

        candles = client.get_historical_candles(
            "BTCUSDT", "1h", 100, 350, limit=2
        )

        self.assertEqual([candle["time"] for candle in candles], ["100", "200", "300"])
        self.assertEqual(client.calls[0]["end_time"], 350)
        self.assertEqual(client.calls[1]["end_time"], 199)


class HistoricalDataLoaderTests(unittest.TestCase):
    def test_converts_exchange_candles_to_chronological_dataframe(self):
        candles = [
            {
                "time": "2000",
                "open": "2",
                "high": "3",
                "low": "1",
                "close": "2.5",
                "quoteVol": "20",
            },
            {
                "time": "1000",
                "open": "1",
                "high": "2",
                "low": "0.5",
                "close": "1.5",
                "quoteVol": "10",
            },
        ]

        class FakeClient:
            def get_historical_candles(self, **kwargs):
                return candles

        dataframe = HistoricalDataLoader(FakeClient()).fetch(
            "BTCUSDT", "1h", 0, 3000
        )

        self.assertEqual(list(dataframe["close"]), [1.5, 2.5])
        self.assertEqual(list(dataframe["volume"]), [10.0, 20.0])


class HistoricalDataStoreTests(unittest.TestCase):
    def test_appends_and_deduplicates_candles_by_time(self):
        first = pd.DataFrame(
            {
                "time": pd.to_datetime(["2026-01-01", "2026-01-02"]),
                "close": [1.0, 2.0],
            }
        )
        second = pd.DataFrame(
            {
                "time": pd.to_datetime(["2026-01-02", "2026-01-03"]),
                "close": [2.0, 3.0],
            }
        )

        with TemporaryDirectory() as directory:
            path = f"{directory}/history.csv"
            store = HistoricalDataStore()
            store.append(first, path)
            result = store.append(second, path)

        self.assertEqual(list(result["close"]), [1.0, 2.0, 3.0])


class HistoricalDataRepairTests(unittest.TestCase):
    def test_recovers_missing_candle_from_exchange(self):
        dataframe = pd.DataFrame(
            {
                "time": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:30"]),
                "open": [1.0, 3.0],
                "high": [2.0, 4.0],
                "low": [0.5, 2.5],
                "close": [1.5, 3.5],
                "volume": [10.0, 30.0],
            }
        )

        class FakeClient:
            def get_candles(self, **kwargs):
                return {
                    "data": [
                        {
                            "time": "1767226500000",
                            "open": "2",
                            "high": "3",
                            "low": "1.5",
                            "close": "2.5",
                            "quoteVol": "20",
                        }
                    ]
                }

        repaired, unresolved = HistoricalDataRepair(FakeClient()).repair(
            dataframe,
            "BTCUSDT",
            "15min",
        )

        self.assertEqual(unresolved, [])
        self.assertEqual(len(repaired), 3)
        self.assertEqual(
            list(repaired["time"]),
            list(pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:15", "2026-01-01 00:30"])),
        )


if __name__ == "__main__":
    unittest.main()
