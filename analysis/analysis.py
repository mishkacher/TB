from analysis.fibonacci import FibonacciEngine
from analysis.fvg import FairValueGapDetector
from analysis.market_structure import MarketStructureEngine


class AnalysisEngine:
    """Combine independent chart observations for later scoring modules."""

    VERSION = "0.1.0"

    def __init__(self, fibonacci=None, fvg_detector=None, market_structure=None):
        self.fibonacci = fibonacci or FibonacciEngine()
        self.fvg_detector = fvg_detector or FairValueGapDetector()
        self.market_structure = market_structure or MarketStructureEngine()

    def analyze(self, df):
        fibonacci = self.fibonacci.analyze(df)
        fair_value_gaps = self.fvg_detector.find(df)
        market_structure = self.market_structure.analyze(df)
        current_price = float(df.iloc[-1]["close"])
        active_fair_value_gaps = [
            gap for gap in fair_value_gaps if gap["status"] == "OPEN"
        ]
        nearest_level, nearest_price = min(
            fibonacci["levels"].items(),
            key=lambda item: abs(current_price - item[1]),
        )

        return {
            "analysis_version": self.VERSION,
            "market_structure": (
                market_structure["structure"]
                if market_structure["structure"] != "RANGE"
                else fibonacci["direction"]
            ),
            "structure_details": market_structure,
            "current_price": current_price,
            "fibonacci": fibonacci,
            "fair_value_gaps": fair_value_gaps,
            "active_fair_value_gaps": active_fair_value_gaps,
            "nearest_fair_value_gap": self._nearest_gap(
                current_price,
                active_fair_value_gaps,
            ),
            "nearest_fibonacci_level": {
                "level": nearest_level,
                "price": nearest_price,
                "distance_percent": round(
                    abs(current_price - nearest_price) / current_price * 100,
                    4,
                ),
            },
        }

    @staticmethod
    def _nearest_gap(current_price, gaps):
        if not gaps:
            return None

        def distance(gap):
            if gap["lower"] <= current_price <= gap["upper"]:
                return 0.0
            return min(
                abs(current_price - gap["lower"]),
                abs(current_price - gap["upper"]),
            )

        gap = min(gaps, key=distance)
        return {
            **gap,
            "distance_percent": round(distance(gap) / current_price * 100, 4),
        }
