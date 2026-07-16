class RulesEngine:


    def check(self, data):

        rules = []


        direction = data["trend"]
        rsi = data["rsi"]
        volume = data["volume_ratio"]
        momentum = data["momentum"]



        # LONG правила

        if direction == "LONG":

            if rsi < 70:
                rules.append(
                    "RSI healthy"
                )

            if volume > 1.5:
                rules.append(
                    "Volume increased"
                )

            if momentum > 0:
                rules.append(
                    "Positive momentum"
                )



        # SHORT правила

        elif direction == "SHORT":

            if rsi > 30:
                rules.append(
                    "RSI not oversold"
                )

            if volume > 1.5:
                rules.append(
                    "Volume increased"
                )

            if momentum < 0:
                rules.append(
                    "Negative momentum"
                )



        # качество сетапа

        quality = "C"


        if len(rules) >= 3:
            quality = "A"

        elif len(rules) == 2:
            quality = "B"



        return {

            "quality": quality,

            "rules": rules

        }