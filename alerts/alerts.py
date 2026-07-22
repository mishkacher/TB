"""Safe delivery of scheduled trade setups.

This module deliberately has no exchange execution capability.  It only sends a
Telegram notification after every decision gate has approved a candidate.
"""

from decision.engine import DecisionEngine
from probability.confidence import ConfidenceIndex
from probability.engine import ProbabilityEngine


class AlertService:
    """Evaluate scanner candidates and keep only approved, non-duplicate setups."""

    def __init__(
        self,
        probability_engine=None,
        confidence_index=None,
        decision_engine=None,
        outcome_provider=None,
    ):
        self.probability_engine = probability_engine or ProbabilityEngine()
        self.confidence_index = confidence_index or ConfidenceIndex()
        self.decision_engine = decision_engine or DecisionEngine()
        self.outcome_provider = outcome_provider or (lambda candidate: [])
        self._sent_fingerprints = set()

    def evaluate(self, candidates, strategy_validation, outcome_provider=None):
        evaluations = []
        outcome_provider = outcome_provider or self.outcome_provider
        for candidate in candidates:
            direction = self._direction(candidate["signal"])
            probability = self.probability_engine.estimate(
                direction,
                outcome_provider(candidate),
                strategy_validation,
            )
            confidence = self.confidence_index.calculate(
                probability,
                candidate["confluence_score"],
            )
            decision = self.decision_engine.decide(
                candidate,
                strategy_validation,
                probability,
                confidence,
            )
            evaluations.append(
                {
                    "candidate": candidate,
                    "probability": probability,
                    "confidence": confidence,
                    **decision,
                }
            )
        return evaluations

    def approved_once(self, candidates, strategy_validation, outcome_provider=None):
        approved = []
        for evaluation in self.evaluate(
            candidates, strategy_validation, outcome_provider
        ):
            if evaluation["decision"] != "APPROVED":
                continue
            fingerprint = self._fingerprint(evaluation["candidate"])
            if fingerprint in self._sent_fingerprints:
                continue
            self._sent_fingerprints.add(fingerprint)
            approved.append(evaluation)
        return approved

    @staticmethod
    def _direction(signal):
        if signal == "LONG BIAS":
            return "LONG"
        if signal == "SHORT BIAS":
            return "SHORT"
        return None

    @staticmethod
    def _fingerprint(candidate):
        return (
            candidate["symbol"],
            candidate["signal"],
            candidate["analysis"].get("current_price"),
        )
