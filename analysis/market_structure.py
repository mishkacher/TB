class MarketStructureEngine:
    """Detect confirmed higher-high/lower-low market structure."""

    def analyze(self, df, lookback=100, pivot_window=2):
        window = df.tail(lookback).reset_index(drop=True)
        highs = self._pivots(window["high"], pivot_window, "high")
        lows = self._pivots(window["low"], pivot_window, "low")

        structure = "RANGE"
        if len(highs) >= 2 and len(lows) >= 2:
            higher_high = highs[-1]["price"] > highs[-2]["price"]
            higher_low = lows[-1]["price"] > lows[-2]["price"]
            lower_high = highs[-1]["price"] < highs[-2]["price"]
            lower_low = lows[-1]["price"] < lows[-2]["price"]

            if higher_high and higher_low:
                structure = "BULLISH"
            elif lower_high and lower_low:
                structure = "BEARISH"

        return {
            "structure": structure,
            "swing_highs": highs,
            "swing_lows": lows,
        }

    @staticmethod
    def _pivots(values, pivot_window, kind):
        pivots = []
        for index in range(pivot_window, len(values) - pivot_window):
            current = values.iloc[index]
            neighbors = values.iloc[index - pivot_window:index + pivot_window + 1]
            if kind == "high" and current == neighbors.max():
                pivots.append({"index": index, "price": float(current)})
            elif kind == "low" and current == neighbors.min():
                pivots.append({"index": index, "price": float(current)})
        return pivots
