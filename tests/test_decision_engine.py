import unittest

from decision.engine import DecisionEngine


class DecisionEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine()
        self.candidate = {"signal": "LONG BIAS", "confluence_score": 80}

    def test_rejects_unvalidated_strategy_before_other_scores(self):
        result = self.engine.decide(
            self.candidate,
            {"approved": False},
            probability=99,
            confidence=99,
        )

        self.assertEqual(result["decision"], "REJECTED")
        self.assertEqual(result["reasons"], ["strategy_not_validated"])

    def test_defers_when_probability_and_confidence_do_not_exist(self):
        result = self.engine.decide(self.candidate, {"approved": True})

        self.assertEqual(result["decision"], "DEFERRED")

    def test_approves_only_when_all_gates_pass(self):
        result = self.engine.decide(
            self.candidate,
            {"approved": True},
            probability=75,
            confidence=80,
        )

        self.assertEqual(result["decision"], "APPROVED")

    def test_rejects_candidate_with_weak_confluence(self):
        result = self.engine.decide(
            {"signal": "LONG BIAS", "confluence_score": 64},
            {"approved": True},
            probability=90,
            confidence=90,
        )

        self.assertEqual(result["decision"], "REJECTED")
        self.assertEqual(result["reasons"], ["confluence_below_threshold"])

    def test_defers_for_structured_unavailable_probability(self):
        result = self.engine.decide(
            self.candidate,
            {"approved": True},
            probability={"available": False, "reason": "insufficient_samples"},
            confidence={"available": False, "reason": "insufficient_samples"},
        )

        self.assertEqual(result["decision"], "DEFERRED")

    def test_accepts_structured_probability_and_confidence(self):
        result = self.engine.decide(
            self.candidate,
            {"approved": True},
            probability={"available": True, "probability_percent": 70},
            confidence={"available": True, "confidence_percent": 80},
        )

        self.assertEqual(result["decision"], "APPROVED")


if __name__ == "__main__":
    unittest.main()
