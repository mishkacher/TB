class DerivativesContext:
    """Normalise public perpetual-futures derivatives data for analysis."""

    def __init__(self, exchange_client, crowded_threshold=0.05):
        self.exchange_client = exchange_client
        self.crowded_threshold = crowded_threshold

    def analyze(self, symbol):
        data = self.exchange_client.get_funding_rate(symbol)
        funding_rate = float(data["fundingRate"])

        if funding_rate >= self.crowded_threshold:
            sentiment = "LONGS_PAYING"
        elif funding_rate <= -self.crowded_threshold:
            sentiment = "SHORTS_PAYING"
        else:
            sentiment = "NEUTRAL"

        return {
            "funding_rate": funding_rate,
            # Bitunix returns fundingRate already in percentage points:
            # 0.005038 means 0.005038%, not 0.5038%.
            "funding_rate_percent": round(funding_rate, 6),
            "funding_sentiment": sentiment,
            "funding_interval_hours": int(data["fundingInterval"]),
            "next_funding_time": int(data["nextFundingTime"]),
        }
