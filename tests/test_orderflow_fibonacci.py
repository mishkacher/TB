import unittest

import pandas as pd

from strategy_lab.orderflow_fibonacci_strategy import OrderflowFibonacciStrategy


class OrderflowFibonacciStrategyTests(unittest.TestCase):
    def test_long_uses_low_to_high_impulse_levels(self):
        dataframe = pd.DataFrame([
            {"high": 102.0, "low": 101.0},
            {"high": 102.0, "low": 100.0},
            {"high": 104.0, "low": 102.0},
            {"high": 105.0, "low": 103.0},
            {"high": 104.0, "low": 102.0},
        ])
        strategy = OrderflowFibonacciStrategy(
            pivot_left=1, pivot_right=1, min_impulse_percent=0.5,
            breakeven_level=0.382,
        )
        strategy.prepare(dataframe)

        signal = strategy.generate_at(4)

        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.entry_limit, 102.5)
        self.assertEqual(signal.stop_loss, 100.0)
        self.assertAlmostEqual(signal.take_profit, 106.15)
        self.assertAlmostEqual(signal.breakeven_trigger, 103.09)

    def test_short_uses_high_to_low_impulse_levels(self):
        dataframe = pd.DataFrame([
            {"high": 104.0, "low": 102.0},
            {"high": 105.0, "low": 103.0},
            {"high": 103.0, "low": 101.0},
            {"high": 102.0, "low": 100.0},
            {"high": 103.0, "low": 101.0},
        ])
        strategy = OrderflowFibonacciStrategy(
            pivot_left=1, pivot_right=1, min_impulse_percent=0.5
        )
        strategy.prepare(dataframe)

        signal = strategy.generate_at(4)

        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(signal.entry_limit, 102.5)
        self.assertEqual(signal.stop_loss, 105.0)
        self.assertAlmostEqual(signal.take_profit, 98.85)

    def test_long_only_mode_rejects_short_impulses(self):
        dataframe = pd.DataFrame([
            {"high": 104.0, "low": 102.0},
            {"high": 105.0, "low": 103.0},
            {"high": 103.0, "low": 101.0},
            {"high": 102.0, "low": 100.0},
            {"high": 103.0, "low": 101.0},
        ])
        strategy = OrderflowFibonacciStrategy(
            pivot_left=1, pivot_right=1, min_impulse_percent=0.5, direction="long"
        )
        strategy.prepare(dataframe)

        self.assertIsNone(strategy.generate_at(4))
