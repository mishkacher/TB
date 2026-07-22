class FairValueGapDetector:
    """Find three-candle FVGs from two non-overlapping outer candles.

    The first and third candles define the gap; the middle candle is the
    displacement candle.  No BOS or size filter is imposed, so every such FVG
    is marked.  The zone becomes available at the close of candle three.
    """

    def find(self, df, lookback=None):
        window = (
            df if lookback is None else df.tail(lookback)
        ).reset_index(drop=True)
        window_start = len(df) - len(window)
        gaps = []

        for index in range(2, len(window)):
            first = window.iloc[index - 2]
            current = window.iloc[index]

            if current["low"] > first["high"]:
                gaps.append(
                    self._gap(
                        "BULLISH",
                        first["high"],
                        current["low"],
                        current,
                        window.iloc[index + 1:],
                        window_start + index,
                    )
                )
            elif current["high"] < first["low"]:
                gaps.append(
                    self._gap(
                        "BEARISH",
                        current["high"],
                        first["low"],
                        current,
                        window.iloc[index + 1:],
                        window_start + index,
                    )
                )

        return gaps

    @staticmethod
    def _gap(direction, lower, upper, candle, future_candles, formed_position):
        if direction == "BULLISH":
            is_filled = (future_candles["low"] <= lower).any()
        else:
            is_filled = (future_candles["high"] >= upper).any()

        result = {
            "direction": direction,
            "lower": round(float(lower), 8),
            "upper": round(float(upper), 8),
            "size": round(float(upper - lower), 8),
            "status": "FILLED" if is_filled else "OPEN",
            "formed_position": int(formed_position),
        }
        if "time" in candle.index:
            result["formed_at"] = candle["time"]
        return result
