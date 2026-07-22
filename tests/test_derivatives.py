import unittest

from analysis.derivatives import DerivativesContext


class DerivativesContextTests(unittest.TestCase):
    class FakeExchange:
        def __init__(self, funding_rate):
            self.funding_rate = funding_rate

        def get_funding_rate(self, symbol):
            return {
                "fundingRate": str(self.funding_rate),
                "fundingInterval": 8,
                "nextFundingTime": "123",
            }

    def test_identifies_crowded_longs(self):
        result = DerivativesContext(self.FakeExchange(0.06)).analyze("BTCUSDT")

        self.assertEqual(result["funding_sentiment"], "LONGS_PAYING")
        self.assertEqual(result["funding_rate_percent"], 0.06)

    def test_identifies_neutral_funding(self):
        result = DerivativesContext(self.FakeExchange(0.01)).analyze("BTCUSDT")

        self.assertEqual(result["funding_sentiment"], "NEUTRAL")
