import unittest
from tempfile import TemporaryDirectory

import pandas as pd

from analysis.analysis import AnalysisEngine
from analysis.candles import candles_to_dataframe
from charts.candlestick import CandlestickChart
from handlers.chart import parse_chart_arguments


class CandlestickChartTests(unittest.TestCase):
    def test_rising_candle_is_green_and_falling_candle_is_red(self):
        self.assertEqual(CandlestickChart._candle_color(100, 110), "#22c55e")
        self.assertEqual(CandlestickChart._candle_color(110, 100), "#ef4444")

    def test_sorts_candles_chronologically_before_rendering(self):
        dataframe = pd.DataFrame(
            {
                "time": pd.to_datetime(["2026-01-01 00:30", "2026-01-01 00:00", "2026-01-01 00:15"]),
                "open": [3.0, 1.0, 2.0],
                "high": [3.5, 1.5, 2.5],
                "low": [2.5, 0.5, 1.5],
                "close": [3.1, 1.1, 2.1],
            }
        )

        data, _ = CandlestickChart._prepare_data(dataframe, "15m")

        self.assertEqual(list(data["open"]), [1.0, 2.0, 3.0])
        self.assertEqual(str(data.iloc[0]["time"].tz), "UTC")

    def test_renders_png_with_analysis_overlays(self):
        dataframe = pd.DataFrame(
            [
                {
                    "time": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=15 * index),
                    "open": 100 + index,
                    "high": 102 + index,
                    "low": 99 + index,
                    "close": 101 + index,
                    "volume": 1000,
                    "ema50": 100 + index,
                    "ema200": 99 + index,
                }
                for index in range(20)
            ]
        )
        analysis = AnalysisEngine().analyze(dataframe)

        with TemporaryDirectory() as directory:
            path = CandlestickChart().render(
                dataframe,
                "BTCUSDT",
                analysis,
                f"{directory}/chart.png",
            )

            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)

    def test_accepts_explicit_supported_timeframe(self):
        self.assertEqual(parse_chart_arguments(["ethusdt", "4h"]), ("ETHUSDT", "4h"))

    def test_rejects_unsupported_timeframe(self):
        with self.assertRaisesRegex(ValueError, "15m, 1h, 4h"):
            parse_chart_arguments(["BTCUSDT", "5m"])

    def test_uses_hundred_dollar_ticks_for_a_narrow_btc_range(self):
        self.assertEqual(CandlestickChart._price_tick_step(100_000, 900), 100.0)

    def test_widens_btc_ticks_on_a_large_range_to_avoid_overlap(self):
        self.assertEqual(CandlestickChart._price_tick_step(100_000, 6_000), 500.0)


class CandleNormalizationTests(unittest.TestCase):
    def test_normalizes_reverse_exchange_response_to_utc_chronological_ohlcv(self):
        dataframe = candles_to_dataframe(
            [
                {"time": "1767226500000", "open": "110", "high": "112", "low": "99", "close": "100", "quoteVol": "20"},
                {"time": "1767225600000", "open": "100", "high": "111", "low": "98", "close": "110", "quoteVol": "10"},
            ]
        )

        self.assertEqual(list(dataframe["open"]), [100.0, 110.0])
        self.assertEqual(list(dataframe["close"]), [110.0, 100.0])
        self.assertEqual(str(dataframe.iloc[0]["time"]), "2026-01-01 00:00:00")

    def test_repairs_exchange_wick_that_does_not_enclose_open_and_close(self):
        dataframe = candles_to_dataframe(
            [{"time": "1767225600000", "open": "100", "high": "99", "low": "98", "close": "110", "quoteVol": "10"}]
        )

        self.assertEqual(dataframe.iloc[0]["high"], 110.0)
        self.assertEqual(dataframe.iloc[0]["low"], 98.0)


if __name__ == "__main__":
    unittest.main()
