import unittest

from config import parse_telegram_ids
from handlers.scan import format_scan_results
from handlers.status import format_system_status


class TelegramLayerTests(unittest.TestCase):
    def test_parses_access_list(self):
        self.assertEqual(parse_telegram_ids("1, 2,3"), frozenset({1, 2, 3}))

    def test_scan_message_shows_explanations_without_calling_it_a_signal(self):
        message = format_scan_results(
            [
                {
                    "symbol": "BTCUSDT",
                    "signal": "LONG BIAS",
                    "score": 70,
                    "ranking_score": 75,
                    "quality": "A",
                    "rules": ["RSI healthy", "Positive momentum"],
                    "confluence_score": 80,
                    "confluence_factors": {
                        "fibonacci_proximity": {"score": 20},
                        "fair_value_gap": {
                            "score": 20,
                            "gap": {"direction": "BULLISH"},
                            "distance_percent": 0.1,
                        },
                    },
                    "analysis": {
                        "market_structure": "BULLISH",
                        "nearest_fibonacci_level": {
                            "level": "0.618",
                            "distance_percent": 0.2,
                        },
                    },
                    "derivatives_context": {
                        "funding_interpretation": "SUPPORTS_LONG_SQUEEZE",
                        "funding_rate_percent": -0.01,
                        "funding_interval_hours": 8,
                    },
                }
            ]
        )

        self.assertIn("BTCUSDT | ПРЕИМУЩЕСТВО LONG", message)
        self.assertIn("RSI в норме", message)
        self.assertIn("Совпадение: 80", message)
        self.assertIn("Фандинг: -0.0100% / 8ч", message)
        self.assertIn("Поддержка LONG-сценария", message)
        self.assertIn("Фибоначчи 0.618 (0.20%)", message)
        self.assertIn("FVG БЫЧИЙ (0.10%)", message)
        self.assertIn("не торговая рекомендация", message)

    def test_status_explains_why_auto_alerts_are_blocked(self):
        message = format_system_status(
            {"approved": False, "reasons": ["profit_factor_below_threshold"]},
            auto_alerts_enabled=True,
            interval_minutes=15,
        )

        self.assertIn("автосетапы заблокированы", message)
        self.assertIn("profit_factor_below_threshold", message)
        self.assertIn("каждые 15 мин.", message)


if __name__ == "__main__":
    unittest.main()
