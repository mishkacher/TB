class ConfidenceIndex:
    """Express how much evidence supports an available probability estimate."""

    def __init__(self, target_samples=300):
        self.target_samples = target_samples

    def calculate(self, probability_result, confluence_score):
        if not probability_result["available"]:
            return {
                "available": False,
                "reason": probability_result["reason"],
            }

        sample_component = min(
            probability_result["sample_size"] / self.target_samples,
            1,
        )
        confluence_component = max(0, min(confluence_score / 100, 1))
        confidence = sample_component * 60 + confluence_component * 40

        return {
            "available": True,
            "confidence_percent": round(confidence, 2),
            "sample_size": probability_result["sample_size"],
        }
