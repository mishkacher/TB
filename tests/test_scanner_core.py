import unittest

import pandas as pd

from scanner.market_scanner import MarketScanner
from scanners.ranking import RankingEngine
from scanners.rules import RulesEngine


def market_frame(**last_values):
    rows = [
        {
            "open": 100.0,
            "close": 100.0,
            "volume": 100.0,
            "ema50": 100.0,
            "ema200": 100.0,
            "rsi": 50.0,
            "atr": 1.0,
        }
        for _ in range(20)
    ]
    rows[-1].update(last_values)
    return pd.DataFrame(rows)


class MarketScannerTests(unittest.TestCase):
    def setUp(self):
        self.scanner = MarketScanner()

    def test_long_bias_when_trend_and_momentum_confirm(self):
        data = self.scanner.analyze(
            market_frame(
                open=100.0,
                close=102.0,
                volume=200.0,
                ema50=110.0,
                ema200=100.0,
            )
        )

        self.assertEqual(data["trend"], "LONG")
        self.assertEqual(data["signal"], "LONG BIAS")
        self.assertGreaterEqual(data["score"], 65)

    def test_short_trend_without_confirmation_is_neutral(self):
        data = self.scanner.analyze(
            market_frame(
                open=100.0,
                close=98.0,
                ema50=90.0,
                ema200=100.0,
            )
        )

        self.assertEqual(data["trend"], "SHORT")
        self.assertEqual(data["signal"], "NEUTRAL")


class RankingEngineTests(unittest.TestCase):
    def setUp(self):
        self.ranking = RankingEngine()
        self.strong_data = {
            "trend": "LONG",
            "momentum": 2.0,
            "volume_ratio": 4.0,
            "rsi": 25.0,
            "atr": 1.0,
        }

    def test_neutral_signal_is_capped(self):
        result = self.ranking.calculate(
            {**self.strong_data, "signal": "NEUTRAL"}
        )

        self.assertEqual(result["ranking_score"], 35)

    def test_directional_signal_keeps_full_ranking(self):
        result = self.ranking.calculate(
            {**self.strong_data, "signal": "LONG BIAS"}
        )

        self.assertGreater(result["ranking_score"], 35)


class RulesEngineTests(unittest.TestCase):
    def test_long_setup_with_three_confirmations_is_quality_a(self):
        result = RulesEngine().check(
            {
                "trend": "LONG",
                "rsi": 50.0,
                "volume_ratio": 2.0,
                "momentum": 0.5,
            }
        )

        self.assertEqual(result["quality"], "A")
        self.assertEqual(
            result["rules"],
            ["RSI healthy", "Volume increased", "Positive momentum"],
        )

    def test_neutral_signal_has_no_setup_quality(self):
        result = RulesEngine().check(
            {
                "signal": "NEUTRAL",
                "trend": "SHORT",
                "rsi": 50.0,
                "volume_ratio": 2.0,
                "momentum": -0.5,
            }
        )

        self.assertEqual(result, {"quality": "C", "rules": []})


if __name__ == "__main__":
    unittest.main()
