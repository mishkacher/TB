class ConfluenceScore:
    """Measure agreement between Scanner and Analysis Engine observations.

    This score is not a trade recommendation and does not estimate probability.
    """

    WEIGHTS = {
        "structure": 35,
        "setup_quality": 25,
        "fair_value_gap": 20,
        "fibonacci_proximity": 20,
    }

    def calculate(
        self,
        scanner_result,
        rules_result,
        analysis_result,
        derivatives=None,
    ):
        if scanner_result.get("signal") == "NEUTRAL":
            return {
                "confluence_score": 0,
                "confluence_factors": {"eligible": False},
                "derivatives_context": self._derivatives_context(
                    scanner_result["signal"],
                    scanner_result["trend"],
                    derivatives,
                ),
            }

        direction = scanner_result["trend"]
        expected_structure = {
            "LONG": "BULLISH",
            "SHORT": "BEARISH",
        }.get(direction)
        expected_gap = expected_structure

        factors = {
            "structure": self._structure_factor(
                expected_structure,
                analysis_result["market_structure"],
            ),
            "setup_quality": self._quality_factor(rules_result["quality"]),
            "fair_value_gap": self._fvg_factor(
                expected_gap,
                analysis_result.get(
                    "active_fair_value_gaps",
                    analysis_result["fair_value_gaps"],
                ),
                analysis_result.get("current_price"),
            ),
            "fibonacci_proximity": self._fibonacci_factor(
                analysis_result["nearest_fibonacci_level"]["distance_percent"],
            ),
        }
        score = sum(item["score"] for item in factors.values())

        return {
            "confluence_score": score,
            "confluence_factors": factors,
            "derivatives_context": self._derivatives_context(
                scanner_result.get("signal"),
                scanner_result["trend"],
                derivatives,
            ),
        }

    @staticmethod
    def _derivatives_context(signal, trend, derivatives):
        if derivatives is None:
            return {"funding_interpretation": "UNAVAILABLE"}

        if signal == "NEUTRAL":
            return {
                "funding_interpretation": "NO_TRADE_DIRECTION",
                **derivatives,
            }

        sentiment = derivatives["funding_sentiment"]
        if trend == "LONG" and sentiment == "SHORTS_PAYING":
            interpretation = "SUPPORTS_LONG_SQUEEZE"
        elif trend == "SHORT" and sentiment == "LONGS_PAYING":
            interpretation = "SUPPORTS_SHORT_SQUEEZE"
        elif sentiment == "NEUTRAL":
            interpretation = "NEUTRAL"
        else:
            interpretation = "COUNTERTREND_FUNDING"

        return {
            "funding_interpretation": interpretation,
            **derivatives,
        }

    def _structure_factor(self, expected_structure, actual_structure):
        matched = expected_structure is not None and actual_structure == expected_structure
        return {
            "matched": matched,
            "score": self.WEIGHTS["structure"] if matched else 0,
        }

    def _quality_factor(self, quality):
        score = {"A": 25, "B": 15, "C": 5}.get(quality, 0)
        return {"quality": quality, "score": score}

    def _fvg_factor(self, expected_gap, gaps, current_price):
        matching_gaps = [
            gap
            for gap in gaps
            if gap["direction"] == expected_gap
            and gap.get("status", "OPEN") == "OPEN"
        ]
        if not matching_gaps:
            return {"matched": False, "score": 0}

        if current_price is None:
            return {
                "matched": True,
                "score": self.WEIGHTS["fair_value_gap"],
            }

        def distance_percent(gap):
            if gap["lower"] <= current_price <= gap["upper"]:
                return 0.0
            distance = min(
                abs(current_price - gap["lower"]),
                abs(current_price - gap["upper"]),
            )
            return distance / current_price * 100

        nearest = min(matching_gaps, key=distance_percent)
        distance = distance_percent(nearest)
        if distance <= 0.5:
            score = self.WEIGHTS["fair_value_gap"]
        elif distance <= 1:
            score = 10
        else:
            score = 0

        return {
            "matched": score > 0,
            "score": score,
            "gap": nearest,
            "distance_percent": round(distance, 4),
        }

    def _fibonacci_factor(self, distance_percent):
        if distance_percent <= 0.5:
            score = self.WEIGHTS["fibonacci_proximity"]
        elif distance_percent <= 1:
            score = 10
        else:
            score = 0

        return {
            "distance_percent": distance_percent,
            "score": score,
        }
