import unittest

from alerts.alerts import AlertService
from alerts.scheduler import load_strategy_validation
from probability.confidence import ConfidenceIndex
from probability.engine import ProbabilityEngine


class AlertServiceTests(unittest.TestCase):
    @staticmethod
    def candidate(signal="LONG BIAS", price=100.0):
        return {
            "symbol": "BTCUSDT",
            "signal": signal,
            "confluence_score": 90,
            "analysis": {"current_price": price},
        }

    def test_rejects_alert_when_strategy_is_not_validated(self):
        service = AlertService(outcome_provider=lambda candidate: [True] * 200)

        result = service.approved_once([self.candidate()], {"approved": False})

        self.assertEqual(result, [])

    def test_sends_approved_candidate_only_once_at_same_price(self):
        service = AlertService(
            probability_engine=ProbabilityEngine(minimum_samples=10),
            confidence_index=ConfidenceIndex(target_samples=100),
            outcome_provider=lambda candidate: [True] * 100,
        )
        validation = {"approved": True}

        first = service.approved_once([self.candidate()], validation)
        repeated = service.approved_once([self.candidate()], validation)

        self.assertEqual(len(first), 1)
        self.assertEqual(repeated, [])
        self.assertEqual(first[0]["decision"], "APPROVED")

    def test_per_call_outcome_provider_overrides_default_provider(self):
        service = AlertService(
            probability_engine=ProbabilityEngine(minimum_samples=10),
            confidence_index=ConfidenceIndex(target_samples=100),
            outcome_provider=lambda candidate: [],
        )

        result = service.approved_once(
            [self.candidate()],
            {"approved": True},
            outcome_provider=lambda candidate: [True] * 100,
        )

        self.assertEqual(len(result), 1)

    def test_missing_report_is_not_approved(self):
        validation = load_strategy_validation("does-not-exist.json")

        self.assertFalse(validation["approved"])
        self.assertEqual(validation["reasons"], ["strategy_report_missing"])


if __name__ == "__main__":
    unittest.main()
