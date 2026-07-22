import unittest
from tempfile import TemporaryDirectory

import pandas as pd

from strategy_lab.backtester import Backtester
from strategy_lab.models import ClosedTrade, TradeSignal
from strategy_lab.report import BacktestReport
from strategy_lab.report_store import ReportStore
from strategy_lab.scanner_confluence_strategy import ScannerConfluenceStrategy
from strategy_lab.walk_forward import WalkForwardSplitter
from strategy_lab.validation import StrategyValidationGate
from strategy_lab.walk_forward_validation import WalkForwardValidator
from strategy_lab.monthly_backtest import MonthlyBacktestRunner
from strategy_lab.monthly_report_aggregate import MonthlyReportAggregator
from strategy_lab.fvg_entry_strategy import FvgEntryStrategy


class ClosedTradeTests(unittest.TestCase):
    def test_short_profit_is_calculated_when_price_falls(self):
        trade = ClosedTrade("BTCUSDT", "SHORT", 100.0, 90.0, 5.0)

        self.assertEqual(trade.pnl_per_unit, 10.0)
        self.assertEqual(trade.return_percent, 10.0)
        self.assertEqual(trade.r_multiple, 2.0)

    def test_deducts_entry_and_exit_fees_from_return(self):
        trade = ClosedTrade(
            "BTCUSDT",
            "LONG",
            100.0,
            110.0,
            5.0,
            entry_fee_percent=0.1,
            exit_fee_percent=0.1,
        )

        self.assertEqual(trade.pnl_per_unit, 9.79)
        self.assertEqual(trade.return_percent, 9.79)


class BacktestReportTests(unittest.TestCase):
    def test_calculates_metrics_for_winning_and_losing_trades(self):
        trades = [
            ClosedTrade("BTCUSDT", "LONG", 100.0, 110.0, 5.0),
            ClosedTrade("ETHUSDT", "LONG", 100.0, 95.0, 5.0),
            ClosedTrade("SOLUSDT", "SHORT", 100.0, 90.0, 5.0),
        ]

        report = BacktestReport().generate(trades)

        self.assertEqual(report["trades"], 3)
        self.assertEqual(report["long_trades"], 2)
        self.assertEqual(report["short_trades"], 1)
        self.assertEqual(report["long_win_rate_percent"], 50.0)
        self.assertEqual(report["short_win_rate_percent"], 100.0)
        self.assertEqual(report["win_rate_percent"], 66.6667)
        self.assertEqual(report["net_return_percent"], 15.0)
        self.assertEqual(report["profit_factor"], 4.0)
        self.assertEqual(report["max_drawdown_percent"], 5.0)
        self.assertEqual(report["average_r_multiple"], 1.0)

    def test_empty_backtest_has_no_division_by_zero(self):
        report = BacktestReport().generate([])

        self.assertEqual(report["trades"], 0)
        self.assertEqual(report["win_rate_percent"], 0.0)
        self.assertIsNone(report["profit_factor"])
        self.assertIsNone(report["average_r_multiple"])


class BacktesterTests(unittest.TestCase):
    class LongStrategy:
        def generate(self, history):
            if len(history) == 2:
                return TradeSignal("LONG", stop_loss=95.0, take_profit=110.0)
            return None

    def test_enters_on_next_open_and_closes_at_target(self):
        df = pd.DataFrame(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 101.0, "high": 111.0, "low": 100.0, "close": 110.0},
            ]
        )

        trades = Backtester().run(df, self.LongStrategy(), "BTCUSDT", warmup=2)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].entry_price, 101.0)
        self.assertEqual(trades[0].exit_price, 110.0)

    def test_moves_stop_to_breakeven_after_trigger(self):
        dataframe = pd.DataFrame([
            {"open": 100.0, "high": 104.0, "low": 99.0, "close": 103.0},
            {"open": 103.0, "high": 106.0, "low": 101.0, "close": 104.0},
            {"open": 104.0, "high": 104.0, "low": 99.0, "close": 100.0},
        ])
        signal = TradeSignal(
            "LONG", stop_loss=95.0, take_profit=110.0, breakeven_trigger=105.0
        )

        index, price, reason, partial = Backtester._find_exit(dataframe, 0, signal, 100.0)

        self.assertEqual(index, 2)
        self.assertEqual(price, 100.0)
        self.assertEqual(reason, "breakeven")
        self.assertIsNone(partial)

    def test_closes_partial_position_then_stops_runner(self):
        dataframe = pd.DataFrame([
            {"open": 100.0, "high": 106.0, "low": 101.0, "close": 105.0},
            {"open": 105.0, "high": 105.0, "low": 94.0, "close": 95.0},
        ])
        signal = TradeSignal(
            "LONG", stop_loss=95.0, take_profit=105.0,
            runner_take_profit=110.0, partial_close_fraction=0.8,
        )

        index, price, reason, partial = Backtester._find_exit(dataframe, 0, signal, 100.0)

        self.assertEqual(index, 1)
        self.assertEqual(price, 95.0)
        self.assertEqual(partial, 105.0)
        self.assertEqual(reason, "stop")

    def test_uses_conservative_stop_when_one_candle_hits_both_levels(self):
        df = pd.DataFrame(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 100.0, "high": 111.0, "low": 94.0, "close": 100.0},
            ]
        )

        trades = Backtester().run(df, self.LongStrategy(), "BTCUSDT", warmup=2)

        self.assertEqual(trades[0].exit_price, 95.0)

    def test_skips_signal_when_next_open_is_outside_stop_and_target(self):
        df = pd.DataFrame(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 120.0, "high": 121.0, "low": 119.0, "close": 120.0},
            ]
        )

        trades = Backtester().run(df, self.LongStrategy(), "BTCUSDT", warmup=2)

        self.assertEqual(trades, [])

    def test_applies_adverse_slippage_and_fees(self):
        df = pd.DataFrame(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 100.0, "high": 111.0, "low": 99.0, "close": 110.0},
            ]
        )

        trades = Backtester(
            fee_percent_per_side=0.1,
            slippage_percent_per_side=0.1,
        ).run(df, self.LongStrategy(), "BTCUSDT", warmup=2)

        self.assertAlmostEqual(trades[0].entry_price, 100.1)
        self.assertAlmostEqual(trades[0].exit_price, 109.89)
        self.assertLess(trades[0].return_percent, 9.79)

    def test_derives_take_profit_from_actual_next_open(self):
        class DynamicTargetStrategy:
            def generate(self, history):
                return TradeSignal("LONG", stop_loss=95.0, reward_to_risk=2.0)

        df = pd.DataFrame(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                {"open": 102.0, "high": 117.0, "low": 101.0, "close": 116.0},
            ]
        )

        trades = Backtester().run(df, DynamicTargetStrategy(), "BTCUSDT", warmup=2)

        self.assertEqual(trades[0].entry_price, 102.0)
        self.assertEqual(trades[0].exit_price, 116.0)

    def test_fills_long_limit_on_retest_of_limit_price(self):
        class LimitStrategy:
            def generate(self, history):
                return TradeSignal(
                    "LONG", stop_loss=95.0, reward_to_risk=2.0, entry_limit=100.0
                )

        df = pd.DataFrame(
            [
                {"open": 105.0, "high": 106.0, "low": 104.0, "close": 105.0},
                {"open": 105.0, "high": 106.0, "low": 104.0, "close": 105.0},
                {"open": 103.0, "high": 111.0, "low": 100.0, "close": 110.0},
            ]
        )

        trades = Backtester().run(df, LimitStrategy(), "BTCUSDT", warmup=2)

        self.assertEqual(trades[0].entry_price, 100.0)
        self.assertEqual(trades[0].exit_price, 110.0)


class WalkForwardSplitterTests(unittest.TestCase):
    def test_generates_chronological_non_overlapping_train_and_test_windows(self):
        df = pd.DataFrame({"value": range(10)})

        windows = WalkForwardSplitter().split(
            df,
            train_size=4,
            test_size=2,
            step=2,
        )

        self.assertEqual(len(windows), 3)
        self.assertEqual(list(windows[0]["train"]["value"]), [0, 1, 2, 3])
        self.assertEqual(list(windows[0]["test"]["value"]), [4, 5])
        self.assertEqual(list(windows[1]["train"]["value"]), [2, 3, 4, 5])
        self.assertEqual(list(windows[1]["test"]["value"]), [6, 7])


class WalkForwardValidatorTests(unittest.TestCase):
    class TestOnlyStrategy:
        def generate(self, history):
            return TradeSignal("LONG", stop_loss=95.0, take_profit=110.0)

    @staticmethod
    def candles(count):
        return pd.DataFrame(
            [
                {"open": 100.0, "high": 111.0, "low": 99.0, "close": 100.0}
                for _ in range(count)
            ]
        )

    def test_opens_trades_only_in_each_test_window(self):
        result = WalkForwardValidator(
            self.TestOnlyStrategy,
            validation_gate=StrategyValidationGate(min_trades=1),
        ).run(
            self.candles(10),
            "BTCUSDT",
            train_size=4,
            test_size=2,
            step=2,
        )

        self.assertEqual(len(result["windows"]), 3)
        self.assertEqual(result["aggregate_report"]["trades"], 6)
        self.assertEqual(len(result["outcomes_by_direction"]["LONG"]), 6)
        self.assertEqual(result["outcomes_by_direction"]["SHORT"], [])
        self.assertFalse(result["validation"]["approved"])
        self.assertIn("profit_factor_below_threshold", result["validation"]["reasons"])

    def test_requires_at_least_one_complete_window(self):
        with self.assertRaisesRegex(ValueError, "walk-forward window"):
            WalkForwardValidator(self.TestOnlyStrategy).run(
                self.candles(5), "BTCUSDT", train_size=4, test_size=2
            )


class MonthlyBacktestRunnerTests(unittest.TestCase):
    class TestOnlyStrategy:
        def generate(self, history):
            return TradeSignal("LONG", stop_loss=95.0, take_profit=110.0)

    @staticmethod
    def candles():
        times = list(pd.date_range("2026-01-31", periods=3, freq="15min"))
        times += list(pd.date_range("2026-02-01", periods=3, freq="15min"))
        return pd.DataFrame(
            [
                {"time": time, "open": 100.0, "high": 111.0, "low": 99.0, "close": 100.0}
                for time in times
            ]
        )

    def test_aggregates_independent_calendar_months(self):
        result = MonthlyBacktestRunner(self.TestOnlyStrategy).run(
            self.candles(), "BTCUSDT", warmup=2
        )

        self.assertEqual([item["month"] for item in result["months"]], ["2026-01", "2026-02"])
        self.assertEqual(result["aggregate_report"]["trades"], 2)
        self.assertFalse(result["validation"]["approved"])
        self.assertIn(
            "monthly_backtests_require_walk_forward_validation",
            result["validation"]["reasons"],
        )


class MonthlyReportAggregatorTests(unittest.TestCase):
    def test_combines_win_rate_from_saved_months(self):
        with TemporaryDirectory() as directory:
            first = ReportStore().save(
                {
                    "symbol": "BTCUSDT", "interval": "15m", "month": "2026-01",
                    "report": {"trades": 10, "long_trades": 6, "short_trades": 4, "long_wins": 2, "short_wins": 2, "wins": 4, "losses": 6, "net_return_percent": -2, "compounded_return_percent": -2},
                }, f"{directory}/jan.json")
            second = ReportStore().save(
                {
                    "symbol": "BTCUSDT", "interval": "15m", "month": "2026-02",
                    "report": {"trades": 20, "long_trades": 11, "short_trades": 9, "long_wins": 5, "short_wins": 5, "wins": 10, "losses": 10, "net_return_percent": 3, "compounded_return_percent": 3},
                }, f"{directory}/feb.json")

            result = MonthlyReportAggregator().aggregate([second, first])

        self.assertEqual(result["months"], ["2026-01", "2026-02"])
        self.assertEqual(result["trades"], 30)
        self.assertEqual(result["long_trades"], 17)
        self.assertEqual(result["short_trades"], 13)
        self.assertEqual(result["long_win_rate_percent"], 41.1765)
        self.assertEqual(result["short_win_rate_percent"], 53.8462)
        self.assertEqual(result["win_rate_percent"], 46.6667)
        self.assertEqual(result["compounded_return_percent"], 0.94)


class ScannerConfluenceStrategyTests(unittest.TestCase):
    class FakeScanner:
        def __init__(self, result):
            self.result = result

        def analyze(self, df):
            return self.result

    class FakeRules:
        def check(self, result):
            return {"quality": "A"}

    class FakeAnalysis:
        def analyze(self, df):
            return {
                "market_structure": "BULLISH",
                "fair_value_gaps": [{"direction": "BULLISH"}],
                "nearest_fibonacci_level": {"distance_percent": 0.1},
            }

    class FakeConfluence:
        def __init__(self, score):
            self.score = score

        def calculate(self, *args):
            return {"confluence_score": self.score}

    @staticmethod
    def history():
        return pd.DataFrame(
            [
                {
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 100.0,
                }
                for _ in range(200)
            ]
        )

    def test_generates_atr_based_long_signal_for_valid_confluence(self):
        strategy = ScannerConfluenceStrategy(
            scanner=self.FakeScanner(
                {"trend": "LONG", "signal": "LONG BIAS"}
            ),
            rules=self.FakeRules(),
            analysis_engine=self.FakeAnalysis(),
            confluence_score=self.FakeConfluence(80),
        )

        signal = strategy.generate(self.history())

        self.assertEqual(signal.direction, "LONG")
        self.assertLess(signal.stop_loss, 100.0)
        self.assertGreater(signal.take_profit, 100.0)

    def test_default_take_profit_is_two_risk_units(self):
        strategy = ScannerConfluenceStrategy(
            scanner=self.FakeScanner({"trend": "LONG", "signal": "LONG BIAS"}),
            rules=self.FakeRules(),
            analysis_engine=self.FakeAnalysis(),
            confluence_score=self.FakeConfluence(80),
        )

        self.assertEqual(strategy.reward_to_risk, 2.0)

    def test_does_not_generate_signal_below_confluence_threshold(self):
        strategy = ScannerConfluenceStrategy(
            scanner=self.FakeScanner(
                {"trend": "LONG", "signal": "LONG BIAS"}
            ),
            rules=self.FakeRules(),
            analysis_engine=self.FakeAnalysis(),
            confluence_score=self.FakeConfluence(50),
        )

        self.assertIsNone(strategy.generate(self.history()))

    def test_prepared_history_generates_the_same_signal(self):
        strategy = ScannerConfluenceStrategy(
            scanner=self.FakeScanner(
                {"trend": "LONG", "signal": "LONG BIAS"}
            ),
            rules=self.FakeRules(),
            analysis_engine=self.FakeAnalysis(),
            confluence_score=self.FakeConfluence(80),
        )
        history = self.history()

        strategy.prepare(history)
        signal = strategy.generate_at(199)

        self.assertEqual(signal.direction, "LONG")


class FvgEntryStrategyTests(unittest.TestCase):
    @staticmethod
    def context_then_bullish_fvg(impulse_gain=3.0):
        rows = [
            {
                "high": 100.0 + impulse_gain * (index + 1) / 16,
                "low": 99.8 + impulse_gain * index / 16,
                "close": 100.0 + impulse_gain * index / 16,
                "volume": 100.0,
            }
            for index in range(16)
        ]
        rows += [
            {"high": 102.45, "low": 102.0, "close": 102.2, "volume": 100.0},
            {"high": 102.40, "low": 102.05, "close": 102.2, "volume": 100.0},
            {"high": 102.42, "low": 102.08, "close": 102.25, "volume": 100.0},
            {"high": 102.44, "low": 102.1, "close": 102.25, "volume": 100.0},
            {"high": 102.5, "low": 102.2, "close": 102.4, "volume": 100.0},
            {"high": 103.1, "low": 102.3, "close": 103.0, "volume": 200.0},
            {"high": 104.0, "low": 103.2, "close": 103.8, "volume": 100.0},
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def context_then_bearish_fvg():
        rows = [
            {
                "high": 103.2 - 3.0 * index / 16,
                "low": 102.8 - 3.0 * index / 16,
                "close": 103.0 - 3.0 * index / 16,
                "volume": 100.0,
            }
            for index in range(16)
        ]
        rows += [
            {"high": 100.6, "low": 100.3, "close": 100.45, "volume": 100.0},
            {"high": 100.55, "low": 100.28, "close": 100.4, "volume": 100.0},
            {"high": 100.58, "low": 100.3, "close": 100.42, "volume": 100.0},
            {"high": 100.56, "low": 100.29, "close": 100.4, "volume": 100.0},
            {"high": 100.5, "low": 100.2, "close": 100.3, "volume": 100.0},
            {"high": 100.1, "low": 99.5, "close": 99.7, "volume": 200.0},
            {"high": 99.8, "low": 99.1, "close": 99.3, "volume": 100.0},
        ]
        return pd.DataFrame(rows)

    def test_opens_long_with_stop_below_bullish_fvg(self):
        signal = FvgEntryStrategy(2.0).generate(self.context_then_bullish_fvg())

        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.stop_loss, 102.5)
        self.assertEqual(signal.reward_to_risk, 2.0)

    def test_places_limit_at_upper_bullish_fvg_boundary(self):
        signal = FvgEntryStrategy(2.0, entry_mode="limit").generate(
            self.context_then_bullish_fvg()
        )

        self.assertEqual(signal.entry_limit, 103.2)

    def test_opens_short_with_stop_above_bearish_fvg(self):
        signal = FvgEntryStrategy(1.0).generate(self.context_then_bearish_fvg())

        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(signal.stop_loss, 100.2)
        self.assertEqual(signal.reward_to_risk, 1.0)

    def test_places_limit_at_lower_bearish_fvg_boundary(self):
        signal = FvgEntryStrategy(1.0, entry_mode="limit").generate(
            self.context_then_bearish_fvg()
        )

        self.assertEqual(signal.entry_limit, 99.8)

    def test_requires_two_percent_up_impulse_and_consolidation_before_long(self):
        strategy = FvgEntryStrategy(
            2.0,
            impulse_lookback=16,
            consolidation_candles=4,
        )

        signal = strategy.generate(self.context_then_bullish_fvg())

        self.assertEqual(signal.direction, "LONG")

    def test_rejects_fvg_after_an_insufficient_impulse(self):
        strategy = FvgEntryStrategy(
            2.0,
            impulse_lookback=16,
            consolidation_candles=4,
        )

        signal = strategy.generate(self.context_then_bullish_fvg(impulse_gain=1.5))

        self.assertIsNone(signal)

    def test_rejects_non_fifteen_minute_entries(self):
        with self.assertRaisesRegex(ValueError, "15m candles only"):
            FvgEntryStrategy(interval="1h")

    def test_rejects_fvg_without_above_average_impulse_volume(self):
        dataframe = self.context_then_bullish_fvg()
        dataframe.loc[dataframe.index[-2], "volume"] = 120.0

        signal = FvgEntryStrategy(2.0, volume_multiplier=1.5).generate(dataframe)

        self.assertIsNone(signal)


class StrategyValidationGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = StrategyValidationGate()

    def test_approves_report_that_meets_all_thresholds(self):
        result = self.gate.validate(
            {
                "trades": 100,
                "profit_factor": 1.5,
                "average_r_multiple": 0.2,
                "max_drawdown_percent": 10.0,
            }
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["reasons"], [])

    def test_rejects_current_negative_backtest_result(self):
        result = self.gate.validate(
            {
                "trades": 161,
                "profit_factor": 0.717,
                "average_r_multiple": -0.1738,
                "max_drawdown_percent": 16.1584,
            }
        )

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["reasons"],
            [
                "profit_factor_below_threshold",
                "average_r_below_threshold",
                "drawdown_above_threshold",
            ],
        )


class ReportStoreTests(unittest.TestCase):
    def test_saves_json_report_for_later_comparison(self):
        with TemporaryDirectory() as directory:
            path = ReportStore().save(
                {"profit_factor": 1.5},
                f"{directory}/reports/test.json",
            )

            self.assertTrue(path.exists())
            self.assertIn('"profit_factor": 1.5', path.read_text())

    def test_loads_persisted_report(self):
        with TemporaryDirectory() as directory:
            path = ReportStore().save(
                {"validation": {"approved": True}},
                f"{directory}/report.json",
            )

            self.assertTrue(ReportStore.load(path)["validation"]["approved"])


if __name__ == "__main__":
    unittest.main()
