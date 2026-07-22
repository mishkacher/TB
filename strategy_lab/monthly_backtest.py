from strategy_lab.backtester import Backtester
from strategy_lab.report import BacktestReport
from strategy_lab.validation import StrategyValidationGate


class MonthlyBacktestRunner:
    """Run one fresh strategy instance per calendar month and aggregate facts."""

    def __init__(
        self,
        strategy_factory,
        backtester=None,
        report_generator=None,
        validation_gate=None,
    ):
        self.strategy_factory = strategy_factory
        self.backtester = backtester or Backtester()
        self.report_generator = report_generator or BacktestReport()
        self.validation_gate = validation_gate or StrategyValidationGate()

    def run(self, dataframe, symbol, warmup=200):
        if "time" not in dataframe:
            raise ValueError("Monthly backtest requires a time column")

        months = []
        all_trades = []
        ordered = dataframe.sort_values("time").reset_index(drop=True)
        for period, month_data in ordered.groupby(ordered["time"].dt.to_period("M")):
            month_data = month_data.reset_index(drop=True)
            if len(month_data) <= warmup:
                continue
            trades = self.backtester.run(
                month_data,
                self.strategy_factory(),
                symbol,
                warmup=warmup,
            )
            all_trades.extend(trades)
            months.append(
                {
                    "month": str(period),
                    "candles": len(month_data),
                    "report": self.report_generator.generate(trades),
                }
            )

        if not months:
            raise ValueError("No month has enough candles for the selected warmup")

        aggregate_report = self.report_generator.generate(all_trades)
        base_validation = self.validation_gate.validate(aggregate_report)
        # Independent calendar buckets are useful resource-efficient research,
        # but are not a substitute for chronological out-of-sample validation.
        validation = {
            "approved": False,
            "reasons": [
                "monthly_backtests_require_walk_forward_validation",
                *base_validation["reasons"],
            ],
        }
        return {
            "months": months,
            "aggregate_report": aggregate_report,
            "validation": validation,
            "outcomes_by_direction": {
                "LONG": [trade.return_percent > 0 for trade in all_trades if trade.direction == "LONG"],
                "SHORT": [trade.return_percent > 0 for trade in all_trades if trade.direction == "SHORT"],
            },
        }
