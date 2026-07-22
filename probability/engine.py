class ProbabilityEngine:
    """Estimate scenario probability only from validated historical outcomes."""

    def __init__(self, minimum_samples=100):
        self.minimum_samples = minimum_samples

    def estimate(self, direction, outcomes, strategy_validation):
        outcomes = list(outcomes)

        if not strategy_validation["approved"]:
            return self._unavailable("strategy_not_validated")
        if direction not in {"LONG", "SHORT"}:
            return self._unavailable("unsupported_direction")
        if len(outcomes) < self.minimum_samples:
            return self._unavailable("insufficient_historical_samples")

        successes = sum(bool(outcome) for outcome in outcomes)
        # Laplace smoothing prevents a misleading 0% or 100% estimate.
        probability = (successes + 1) / (len(outcomes) + 2) * 100

        return {
            "available": True,
            "direction": direction,
            "probability_percent": round(probability, 2),
            "sample_size": len(outcomes),
            "wins": successes,
        }

    @staticmethod
    def _unavailable(reason):
        return {"available": False, "reason": reason}
