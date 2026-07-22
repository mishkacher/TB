class StrategyValidationGate:
    """Prevent unvalidated strategies from producing live bot recommendations."""

    def __init__(
        self,
        min_trades=50,
        min_profit_factor=1.2,
        min_average_r_multiple=0.1,
        max_drawdown_percent=15.0,
    ):
        self.min_trades = min_trades
        self.min_profit_factor = min_profit_factor
        self.min_average_r_multiple = min_average_r_multiple
        self.max_drawdown_percent = max_drawdown_percent

    def validate(self, report):
        reasons = []

        if report["trades"] < self.min_trades:
            reasons.append("insufficient_trade_count")
        if (
            report["profit_factor"] is None
            or report["profit_factor"] < self.min_profit_factor
        ):
            reasons.append("profit_factor_below_threshold")
        if (
            report["average_r_multiple"] is None
            or report["average_r_multiple"] < self.min_average_r_multiple
        ):
            reasons.append("average_r_below_threshold")
        if report["max_drawdown_percent"] > self.max_drawdown_percent:
            reasons.append("drawdown_above_threshold")

        return {
            "approved": not reasons,
            "reasons": reasons,
        }
