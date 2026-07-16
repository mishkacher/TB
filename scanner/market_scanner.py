from ta.trend import EMAIndicator


class MarketScanner:


    def analyze(self, df):

        last = df.iloc[-1]


        # Momentum
        momentum = (
            (last["close"] - last["open"])
            /
            last["open"]
            * 100
        )


        # Volume
        avg_volume = (
            df["volume"]
            .rolling(20)
            .mean()
            .iloc[-1]
        )


        volume_ratio = (
            last["volume"]
            /
            avg_volume
        )


        # Trend
        trend = "NEUTRAL"


        if last["ema50"] > last["ema200"]:
            trend = "LONG"

        elif last["ema50"] < last["ema200"]:
            trend = "SHORT"


        # RSI
        rsi = last["rsi"]


        # ATR
        atr = last["atr"]


        # Score
        score = 50


        # Momentum
        if momentum > 0:
            score += 10
        else:
            score -= 5


        # Volume
        if volume_ratio > 1.5:
            score += 15


        # Trend
        if trend == "LONG":
            score += 15

        elif trend == "SHORT":
            score -= 10


        # RSI
        if rsi < 30:
            score += 10

        elif rsi > 70:
            score -= 10


        # ограничение
        score = max(0, min(score, 100))

        # Signal

        if score >= 65 and trend == "LONG":
            signal = "LONG BIAS"

        elif score >= 65 and trend == "SHORT":
            signal = "SHORT BIAS"

        else:
            signal = "NEUTRAL"



        confidence = score



        return {

            "trend": trend,

            "signal": signal,

            "confidence":
                confidence,

            "momentum":
                round(momentum, 2),

            "volume_ratio":
                round(volume_ratio, 2),

            "rsi":
                round(rsi, 2),

            "atr":
                round(atr, 2),

            "score":
                score
        }