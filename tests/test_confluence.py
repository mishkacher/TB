import unittest

from score.confluence import ConfluenceScore


class ConfluenceScoreTests(unittest.TestCase):
    def setUp(self):
        self.score = ConfluenceScore()
        self.scanner_result = {"trend": "LONG"}
        self.rules_result = {"quality": "A"}
        self.analysis_result = {
            "market_structure": "BULLISH",
            "current_price": 100.0,
            "fair_value_gaps": [
                {"direction": "BULLISH", "lower": 99.0, "upper": 101.0}
            ],
            "nearest_fibonacci_level": {"distance_percent": 0.2},
        }

    def test_all_independent_factors_agree(self):
        result = self.score.calculate(
            self.scanner_result,
            self.rules_result,
            self.analysis_result,
        )

        self.assertEqual(result["confluence_score"], 100)
        self.assertTrue(result["confluence_factors"]["structure"]["matched"])
        self.assertTrue(result["confluence_factors"]["fair_value_gap"]["matched"])

    def test_conflicting_structure_and_gap_are_not_awarded(self):
        result = self.score.calculate(
            self.scanner_result,
            {"quality": "C"},
            {
                "market_structure": "BEARISH",
                "current_price": 100.0,
                "fair_value_gaps": [
                    {"direction": "BEARISH", "lower": 99.0, "upper": 101.0}
                ],
                "nearest_fibonacci_level": {"distance_percent": 1.2},
            },
        )

        self.assertEqual(result["confluence_score"], 5)
        self.assertFalse(result["confluence_factors"]["structure"]["matched"])
        self.assertFalse(result["confluence_factors"]["fair_value_gap"]["matched"])

    def test_filled_gap_is_not_counted_as_confirmation(self):
        result = self.score.calculate(
            self.scanner_result,
            self.rules_result,
            {
                "market_structure": "BULLISH",
                "fair_value_gaps": [
                    {"direction": "BULLISH", "status": "FILLED"}
                ],
                "nearest_fibonacci_level": {"distance_percent": 0.2},
            },
        )

        self.assertEqual(result["confluence_score"], 80)
        self.assertFalse(result["confluence_factors"]["fair_value_gap"]["matched"])

    def test_funding_is_explained_without_changing_score(self):
        result = self.score.calculate(
            self.scanner_result,
            self.rules_result,
            self.analysis_result,
            {
                "funding_sentiment": "SHORTS_PAYING",
                "funding_rate": -0.1,
            },
        )

        self.assertEqual(result["confluence_score"], 100)
        self.assertEqual(
            result["derivatives_context"]["funding_interpretation"],
            "SUPPORTS_LONG_SQUEEZE",
        )

    def test_far_open_fvg_does_not_receive_points(self):
        result = self.score.calculate(
            self.scanner_result,
            self.rules_result,
            {
                "market_structure": "BULLISH",
                "current_price": 100.0,
                "fair_value_gaps": [
                    {"direction": "BULLISH", "lower": 80.0, "upper": 81.0}
                ],
                "nearest_fibonacci_level": {"distance_percent": 0.2},
            },
        )

        self.assertEqual(result["confluence_score"], 80)
        self.assertFalse(result["confluence_factors"]["fair_value_gap"]["matched"])

    def test_neutral_signal_cannot_receive_confluence(self):
        result = self.score.calculate(
            {"trend": "SHORT", "signal": "NEUTRAL"},
            self.rules_result,
            self.analysis_result,
        )

        self.assertEqual(result["confluence_score"], 0)
        self.assertFalse(result["confluence_factors"]["eligible"])
        self.assertEqual(
            result["derivatives_context"]["funding_interpretation"],
            "UNAVAILABLE",
        )

    def test_neutral_signal_has_no_funding_direction(self):
        result = self.score.calculate(
            {"trend": "SHORT", "signal": "NEUTRAL"},
            self.rules_result,
            self.analysis_result,
            {"funding_sentiment": "LONGS_PAYING"},
        )

        self.assertEqual(
            result["derivatives_context"]["funding_interpretation"],
            "NO_TRADE_DIRECTION",
        )


if __name__ == "__main__":
    unittest.main()
