import unittest

import pandas as pd

from analysis.analysis import AnalysisEngine
from analysis.fibonacci import FibonacciEngine
from analysis.fvg import FairValueGapDetector
from analysis.market_structure import MarketStructureEngine


class FibonacciEngineTests(unittest.TestCase):
    def test_bullish_swing_uses_retracement_convention_and_full_levels(self):
        df = pd.DataFrame(
            [
                {"high": 110.0, "low": 100.0, "close": 105.0},
                {"high": 120.0, "low": 105.0, "close": 115.0},
            ]
        )

        result = FibonacciEngine().analyze(df)

        self.assertEqual(result["direction"], "BULLISH")
        self.assertEqual(result["levels"]["0"], 120.0)
        self.assertEqual(result["levels"]["1"], 100.0)
        self.assertEqual(result["levels"]["0.618"], 107.64)
        self.assertEqual(result["levels"]["-0.618"], 132.36)
        self.assertEqual(result["anchor_source"], "lookback_extrema")

    def test_bearish_swing_is_measured_from_the_high(self):
        df = pd.DataFrame(
            [
                {"high": 120.0, "low": 110.0, "close": 115.0},
                {"high": 115.0, "low": 100.0, "close": 105.0},
            ]
        )

        result = FibonacciEngine().analyze(df)

        self.assertEqual(result["direction"], "BEARISH")
        self.assertEqual(result["levels"]["0"], 100.0)
        self.assertEqual(result["levels"]["1"], 120.0)
        self.assertEqual(result["levels"]["-0.18"], 96.4)

    def test_prefers_the_latest_confirmed_pivot_swing(self):
        df = pd.DataFrame(
            {
                "high": [10, 12, 11, 13, 12, 15, 14, 16, 15, 14, 13],
                "low": [8, 9, 9, 10, 10, 11, 11, 12, 12, 11, 10],
                "close": [9] * 11,
            }
        )

        result = FibonacciEngine().analyze(df, pivot_span=1)

        self.assertEqual(result["anchor_source"], "confirmed_pivot")
        self.assertEqual(result["direction"], "BULLISH")
        self.assertEqual(result["swing_low_position"], 6)
        self.assertEqual(result["swing_high_position"], 7)

    def test_skips_flat_confirmed_pivot_pairs(self):
        df = pd.DataFrame(
            {
                "high": [10, 11, 11, 10, 12, 11, 10],
                "low": [9, 10, 10, 9, 10, 10, 9],
                "close": [10] * 7,
            }
        )

        result = FibonacciEngine().analyze(df, pivot_span=1)

        self.assertGreater(result["range"], 0)


class FairValueGapDetectorTests(unittest.TestCase):
    def test_detects_three_candle_bullish_and_bearish_gaps(self):
        df = pd.DataFrame(
            [
                {"high": 100.0, "low": 90.0},
                {"high": 105.0, "low": 95.0},
                {"high": 112.0, "low": 106.0},
                {"high": 94.0, "low": 85.0},
            ]
        )

        gaps = FairValueGapDetector().find(df)

        self.assertEqual(gaps[0]["direction"], "BULLISH")
        self.assertEqual(gaps[0]["lower"], 100.0)
        self.assertEqual(gaps[0]["upper"], 106.0)
        self.assertEqual(gaps[0]["status"], "FILLED")
        self.assertEqual(gaps[0]["formed_position"], 2)
        self.assertEqual(gaps[1]["direction"], "BEARISH")
        self.assertEqual(gaps[1]["lower"], 94.0)
        self.assertEqual(gaps[1]["upper"], 95.0)
        self.assertEqual(gaps[1]["status"], "OPEN")


class MarketStructureEngineTests(unittest.TestCase):
    def test_detects_bullish_higher_highs_and_higher_lows(self):
        df = pd.DataFrame(
            {
                "high": [10, 12, 11, 13, 12, 14, 13],
                "low": [8, 9, 9, 10, 10, 11, 11],
            }
        )

        result = MarketStructureEngine().analyze(df, pivot_window=1)

        self.assertEqual(result["structure"], "BULLISH")


class AnalysisEngineTests(unittest.TestCase):
    def test_returns_observations_without_creating_a_trade_signal(self):
        df = pd.DataFrame(
            [
                {"high": 110.0, "low": 100.0, "close": 105.0},
                {"high": 120.0, "low": 105.0, "close": 118.0},
                {"high": 125.0, "low": 115.0, "close": 120.0},
            ]
        )

        result = AnalysisEngine().analyze(df)

        self.assertEqual(result["analysis_version"], "0.1.0")
        self.assertEqual(result["market_structure"], "BULLISH")
        self.assertNotIn("signal", result)
        self.assertIn("nearest_fibonacci_level", result)
        self.assertIn("active_fair_value_gaps", result)

    def test_nearest_gap_is_zero_distance_when_price_is_inside_zone(self):
        result = AnalysisEngine._nearest_gap(
            105.0,
            [{"direction": "BULLISH", "lower": 100.0, "upper": 110.0}],
        )

        self.assertEqual(result["distance_percent"], 0.0)


if __name__ == "__main__":
    unittest.main()
