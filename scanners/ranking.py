class RankingEngine:


    def calculate(self, data):

        score = 0

        details = {}


        # Trend Score (0-25)

        trend_score = 0

        if data["trend"] == "LONG":
            trend_score = 25

        elif data["trend"] == "SHORT":
            trend_score = 25

        details["trend"] = trend_score

        score += trend_score



        # Momentum Score (0-20)

        momentum_score = 0

        momentum = data["momentum"]


        if abs(momentum) > 1:
            momentum_score = 20

        elif abs(momentum) > 0.5:
            momentum_score = 15

        elif abs(momentum) > 0:
            momentum_score = 10


        details["momentum"] = momentum_score

        score += momentum_score



        # Volume Score (0-20)

        volume_score = 0

        volume = data["volume_ratio"]


        if volume > 3:
            volume_score = 20

        elif volume > 2:
            volume_score = 15

        elif volume > 1.5:
            volume_score = 10


        details["volume"] = volume_score

        score += volume_score



        # RSI Score (0-15)

        rsi_score = 0

        rsi = data["rsi"]


        if rsi < 30:
            rsi_score = 15

        elif rsi < 40:
            rsi_score = 10

        elif rsi > 70:
            rsi_score = 0

        else:
            rsi_score = 5


        details["rsi"] = rsi_score

        score += rsi_score



        # Volatility Score (0-10)

        volatility_score = 0

        if data["atr"] > 0:
            volatility_score = 10


        details["volatility"] = volatility_score

        score += volatility_score



        # ограничение

        score = min(score, 100)


        # Без торгового сигнала монета не должна попадать в топ

        if data["signal"] == "NEUTRAL":
            score = min(score, 35)


        return {

            "ranking_score": score,

            "ranking_details": details

        }
