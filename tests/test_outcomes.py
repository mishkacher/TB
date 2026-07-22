import unittest
from tempfile import TemporaryDirectory

from strategy_lab.outcomes import ReportOutcomeProvider, StrategyReportRegistry
from strategy_lab.report_store import ReportStore


class ReportOutcomeProviderTests(unittest.TestCase):
    def test_registry_keeps_reports_separated_by_symbol(self):
        registry = StrategyReportRegistry("reports", "0_1_0")

        self.assertEqual(
            registry.path_for("BTCUSDT"),
            "reports/btcusdt_15m_365d_v0_1_0.json",
        )
        self.assertEqual(
            registry.path_for("ETHUSDT", "4h", 180),
            "reports/ethusdt_4h_180d_v0_1_0.json",
        )

    def test_returns_only_the_matching_direction(self):
        with TemporaryDirectory() as directory:
            path = ReportStore().save(
                {
                    "symbol": "BTCUSDT",
                    "outcomes_by_direction": {"LONG": [True, False], "SHORT": [False]},
                },
                f"{directory}/report.json",
            )
            provider = ReportOutcomeProvider(path)

            self.assertEqual(
                provider({"symbol": "BTCUSDT", "signal": "LONG BIAS"}), [True, False]
            )
            self.assertEqual(
                provider({"symbol": "BTCUSDT", "signal": "SHORT BIAS"}), [False]
            )
            self.assertEqual(
                provider({"symbol": "ETHUSDT", "signal": "LONG BIAS"}), []
            )

    def test_returns_no_outcomes_for_missing_or_old_report(self):
        provider = ReportOutcomeProvider("missing.json")

        self.assertEqual(provider({"signal": "LONG BIAS"}), [])


if __name__ == "__main__":
    unittest.main()
