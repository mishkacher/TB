import math
from pathlib import Path
from tempfile import NamedTemporaryFile

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MultipleLocator


class CandlestickChart:
    """Render chronological OHLC candles, EMA lines and open FVG zones."""

    UP_COLOR = "#22c55e"
    DOWN_COLOR = "#ef4444"
    FLAT_COLOR = "#9ca3af"
    DISPLAY_TIMEZONE = "UTC"
    CANDLE_COUNTS = {"15m": 200, "1h": 200, "4h": 180}

    def render(self, dataframe, symbol, analysis, output_path=None, interval="15m"):
        data, source_start = self._prepare_data(dataframe, interval)
        figure, axis = plt.subplots(figsize=(14, 8), facecolor="#111827")
        axis.set_facecolor("#111827")

        for index, candle in data.iterrows():
            color = self._candle_color(candle["open"], candle["close"])
            axis.vlines(index, candle["low"], candle["high"], color=color, linewidth=1)
            body_low = min(candle["open"], candle["close"])
            body_height = max(abs(candle["close"] - candle["open"]), 1e-8)
            axis.add_patch(
                Rectangle(
                    (index - 0.32, body_low),
                    0.64,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                )
            )

        for column, color, label in (
            ("ema50", "#facc15", "EMA 50"),
            ("ema200", "#60a5fa", "EMA 200"),
        ):
            if column in data and data[column].notna().any():
                axis.plot(data.index, data[column], color=color, linewidth=1, label=label)

        for gap in analysis.get("fair_value_gaps", []):
            if gap["status"] != "OPEN":
                continue
            formed_position = gap.get("formed_position", 0) - source_start
            if formed_position >= len(data):
                continue
            start = max(0, formed_position)
            color = "#14532d" if gap["direction"] == "BULLISH" else "#7f1d1d"
            axis.add_patch(
                Rectangle(
                    (start, gap["lower"]),
                    len(data) - start,
                    gap["upper"] - gap["lower"],
                    color=color,
                    alpha=0.35,
                    zorder=0,
                )
            )

        current_price = float(data.iloc[-1]["close"])
        axis.axhline(current_price, color="#2dd4bf", linewidth=1.2)
        axis.annotate(
            f" CURRENT {current_price:,.4f}",
            (len(data) - 1, current_price),
            color="#111827",
            fontsize=9,
            fontweight="bold",
            va="center",
            ha="right",
            bbox={"boxstyle": "round,pad=0.25", "fc": "#2dd4bf", "ec": "none"},
        )

        axis.set_title(
            f"{symbol} · {interval} · {analysis['market_structure']} · Current {current_price:,.4f}",
            color="white",
            loc="left",
            fontweight="bold",
        )
        tick_count = max(2, min(8, math.ceil(len(data) / 20)))
        tick_positions = sorted(set(round(value) for value in np.linspace(0, len(data) - 1, tick_count)))
        axis.set_xticks(tick_positions)
        axis.set_xticklabels(
            [data.iloc[position]["time"].strftime("%d %b\n%H:%M") for position in tick_positions],
            fontsize=8,
        )
        axis.set_xlabel(self.DISPLAY_TIMEZONE, color="#9ca3af")
        axis.set_xlim(-1, len(data))
        axis.yaxis.tick_right()
        axis.yaxis.set_label_position("right")
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.4f}"))
        visible_range = float(data["high"].max() - data["low"].min())
        axis.yaxis.set_major_locator(MultipleLocator(self._price_tick_step(current_price, visible_range)))
        axis.tick_params(colors="#9ca3af")
        for spine in axis.spines.values():
            spine.set_color("#374151")
        axis.grid(color="#374151", alpha=0.3)
        handles, _ = axis.get_legend_handles_labels()
        if handles:
            axis.legend(facecolor="#1f2937", labelcolor="white", loc="upper left")
        figure.tight_layout()

        if output_path is None:
            temporary = NamedTemporaryFile(suffix=".png", delete=False)
            output_path = temporary.name
            temporary.close()

        figure.savefig(output_path, dpi=150, facecolor=figure.get_facecolor())
        plt.close(figure)
        return Path(output_path)

    @classmethod
    def _prepare_data(cls, dataframe, interval):
        required = {"time", "open", "high", "low", "close"}
        missing = required.difference(dataframe.columns)
        if missing:
            raise ValueError(f"Chart data is missing columns: {', '.join(sorted(missing))}")
        if dataframe.empty:
            raise ValueError("Cannot render an empty candle chart")

        data = dataframe.copy()
        data["time"] = pd.to_datetime(data["time"], utc=True, errors="coerce")
        if data["time"].isna().any():
            raise ValueError("Chart contains invalid candle timestamps")
        data = data.sort_values("time", kind="stable").drop_duplicates("time", keep="last")

        invalid = (
            (data["high"] < data[["open", "close", "low"]].max(axis=1))
            | (data["low"] > data[["open", "close", "high"]].min(axis=1))
        )
        if invalid.any():
            raise ValueError("Chart contains invalid OHLC prices")

        candle_count = cls.CANDLE_COUNTS.get(interval, 200)
        source_start = max(0, len(data) - candle_count)
        return data.iloc[source_start:].reset_index(drop=True), source_start

    @classmethod
    def _candle_color(cls, opening, closing):
        if closing > opening:
            return cls.UP_COLOR
        if closing < opening:
            return cls.DOWN_COLOR
        return cls.FLAT_COLOR

    @staticmethod
    def _price_tick_step(current_price, visible_range, max_labels=12):
        """Prefer fine readable price ticks, widening only when labels crowd."""
        minimum_step = (
            100.0 if current_price >= 10_000 else
            10.0 if current_price >= 1_000 else
            1.0 if current_price >= 100 else
            0.1
        )
        if visible_range <= 0:
            return minimum_step
        step = minimum_step
        while visible_range / step > max_labels:
            magnitude = 10 ** int(math.floor(math.log10(step)))
            normalized = round(step / magnitude, 6)
            step = 2 * magnitude if normalized == 1 else 5 * magnitude if normalized == 2 else 10 * magnitude
        return step
