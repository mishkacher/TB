class DecisionEngine:
    """Turn validated scores into an explicit approve, reject, or defer outcome."""

    def __init__(self, min_probability=60, min_confidence=70, min_confluence=65):
        self.min_probability = min_probability
        self.min_confidence = min_confidence
        self.min_confluence = min_confluence

    def decide(
        self,
        candidate,
        strategy_validation,
        probability=None,
        confidence=None,
    ):
        if not strategy_validation["approved"]:
            return self._result("REJECTED", ["strategy_not_validated"])

        if candidate["signal"] == "NEUTRAL":
            return self._result("REJECTED", ["neutral_scanner_signal"])

        if candidate.get("confluence_score", 0) < self.min_confluence:
            return self._result("REJECTED", ["confluence_below_threshold"])

        probability = self._value(probability, "probability_percent")
        confidence = self._value(confidence, "confidence_percent")

        if probability is None or confidence is None:
            return self._result(
                "DEFERRED",
                ["probability_or_confidence_unavailable"],
            )

        reasons = []
        if probability < self.min_probability:
            reasons.append("probability_below_threshold")
        if confidence < self.min_confidence:
            reasons.append("confidence_below_threshold")

        if reasons:
            return self._result("REJECTED", reasons)

        return self._result("APPROVED", [])

    @staticmethod
    def _result(status, reasons):
        return {"decision": status, "reasons": reasons}

    @staticmethod
    def _value(result, field):
        if result is None:
            return None
        if isinstance(result, dict):
            if not result.get("available", False):
                return None
            return result.get(field)
        return result
