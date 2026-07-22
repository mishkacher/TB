import unittest

from probability.confidence import ConfidenceIndex
from probability.engine import ProbabilityEngine


class ProbabilityEngineTests(unittest.TestCase):
    def test_rejects_unvalidated_strategy(self):
        result = ProbabilityEngine().estimate(
            "LONG",
            [True] * 150,
            {"approved": False},
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "strategy_not_validated")

    def test_returns_smoothed_probability_for_valid_history(self):
        result = ProbabilityEngine(minimum_samples=10).estimate(
            "LONG",
            [True] * 8 + [False] * 2,
            {"approved": True},
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["probability_percent"], 75.0)
        self.assertEqual(result["sample_size"], 10)


class ConfidenceIndexTests(unittest.TestCase):
    def test_combines_sample_size_and_confluence(self):
        result = ConfidenceIndex(target_samples=100).calculate(
            {"available": True, "sample_size": 100},
            75,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["confidence_percent"], 90.0)

    def test_unavailable_probability_stays_unavailable(self):
        result = ConfidenceIndex().calculate(
            {"available": False, "reason": "strategy_not_validated"},
            100,
        )

        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
