class FibonacciEngine:
    """Draw a retracement from the latest confirmed impulse swing.

    Convention used by TradingView's retracement tool: for an up impulse we
    connect swing low → swing high and label the high as 0, the low as 1.  For
    a down impulse we connect swing high → swing low and label the low as 0,
    the high as 1.  This makes 0.382/0.5/0.618 actual pullback levels.
    """

    LEVELS = (
        -1.0,
        -0.618,
        -0.272,
        -0.27,
        -0.18,
        0.0,
        0.236,
        0.382,
        0.5,
        0.618,
        0.705,
        0.786,
        1.0,
        1.272,
        1.618,
    )

    def analyze(self, df, lookback=200, pivot_span=3):
        window = df.tail(lookback).reset_index(drop=True)
        window_start = len(df) - len(window)
        if len(window) < 2:
            raise ValueError("At least two candles are required for Fibonacci analysis")

        swing = self._latest_confirmed_swing(window, pivot_span)
        anchor_source = "confirmed_pivot"
        if swing is None:
            swing = self._fallback_extreme_swing(window)
            anchor_source = "lookback_extrema"

        swing_low_index = swing["low_position"]
        swing_high_index = swing["high_position"]
        swing_low = float(window.loc[swing_low_index, "low"])
        swing_high = float(window.loc[swing_high_index, "high"])
        price_range = swing_high - swing_low
        if price_range <= 0:
            raise ValueError("Fibonacci analysis requires a non-zero price range")

        direction = "BULLISH" if swing_low_index < swing_high_index else "BEARISH"
        # Retracement convention: level 0 is the end of the impulse, and level
        # 1 is its start. Negative levels are continuation targets beyond 0.
        if direction == "BULLISH":
            origin, multiplier = swing_high, -price_range
        else:
            origin, multiplier = swing_low, price_range
        values = {
            self._label(level): round(origin + multiplier * level, 8)
            for level in self.LEVELS
        }

        return {
            "direction": direction,
            "anchor_source": anchor_source,
            "swing_low": swing_low,
            "swing_high": swing_high,
            "swing_low_position": int(window_start + swing_low_index),
            "swing_high_position": int(window_start + swing_high_index),
            "range": price_range,
            "levels": values,
        }

    @staticmethod
    def _latest_confirmed_swing(window, span):
        if span < 1 or len(window) < span * 2 + 1:
            return None

        pivots = []
        # The last ``span`` candles cannot be confirmed yet; this prevents the
        # displayed swing from moving with every unfinished candle.
        for index in range(span, len(window) - span):
            lows = window["low"].iloc[index - span : index + span + 1]
            highs = window["high"].iloc[index - span : index + span + 1]
            if window.loc[index, "low"] == lows.min():
                pivots.append((index, "LOW"))
            if window.loc[index, "high"] == highs.max():
                pivots.append((index, "HIGH"))

        for position, kind in sorted(pivots, reverse=True):
            opposite = "LOW" if kind == "HIGH" else "HIGH"
            previous = [item for item in pivots if item[1] == opposite and item[0] < position]
            if not previous:
                continue
            prior_position = max(previous)[0]
            if kind == "HIGH":
                low_position, high_position = prior_position, position
            else:
                low_position, high_position = position, prior_position
            if float(window.loc[high_position, "high"]) > float(
                window.loc[low_position, "low"]
            ):
                return {
                    "low_position": low_position,
                    "high_position": high_position,
                }
        return None

    @staticmethod
    def _fallback_extreme_swing(window):
        return {
            "low_position": int(window["low"].idxmin()),
            "high_position": int(window["high"].idxmax()),
        }

    @staticmethod
    def _label(level):
        return f"{level:g}"
