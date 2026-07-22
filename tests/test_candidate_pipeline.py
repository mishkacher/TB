import unittest

from pipeline.candidate_pipeline import CandidatePipeline


class FakeMultiScanner:
    def scan(self):
        return [
            {
                "symbol": "BTCUSDT",
                "trend": "LONG",
                "quality": "A",
                "ranking_score": 60,
            },
            {
                "symbol": "ETHUSDT",
                "trend": "SHORT",
                "quality": "B",
                "ranking_score": 70,
            },
        ]


class FakeAnalysisEngine:
    def analyze(self, frame):
        return frame


class CandidatePipelineTests(unittest.TestCase):
    def test_enriches_and_orders_scanner_candidates(self):
        analysis_by_symbol = {
            "BTCUSDT": {
                "market_structure": "BULLISH",
                "fair_value_gaps": [{"direction": "BULLISH"}],
                "nearest_fibonacci_level": {"distance_percent": 0.2},
            },
            "ETHUSDT": {
                "market_structure": "BEARISH",
                "fair_value_gaps": [],
                "nearest_fibonacci_level": {"distance_percent": 1.2},
            },
        }

        pipeline = CandidatePipeline(
            multi_scanner=FakeMultiScanner(),
            candle_loader=lambda symbol: analysis_by_symbol[symbol],
            analysis_engine=FakeAnalysisEngine(),
        )

        result = pipeline.run()

        self.assertEqual([item["symbol"] for item in result], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(result[0]["confluence_score"], 100)
        self.assertEqual(result[1]["confluence_score"], 50)
        self.assertEqual(result[0]["analysis"], analysis_by_symbol["BTCUSDT"])


if __name__ == "__main__":
    unittest.main()
