import pandas as pd

from strategy_lab.backtester import Backtester
from strategy_lab.report import BacktestReport
from strategy_lab.validation import StrategyValidationGate
from strategy_lab.walk_forward import WalkForwardSplitter


class WalkForwardValidator:
    """Evaluate a fresh strategy over consecutive, out-of-sample windows."""

    def __init__(
        self,
        strategy_factory,
        backtester=None,
        report_generator=None,
        validation_gate=None,
        splitter=None,
    ):
        self.strategy_factory = strategy_factory
        self.backtester = backtester or Backtester()
        self.report_generator = report_generator or BacktestReport()
        self.validation_gate = validation_gate or StrategyValidationGate()
        self.splitter = splitter or WalkForwardSplitter()

    def run(self, dataframe, symbol, train_size, test_size, step=None):
        windows = self.splitter.split(dataframe, train_size, test_size, step)
        if not windows:
            raise ValueError("Not enough candles for one walk-forward window")

        all_trades = []
        window_reports = []
        for number, window in enumerate(windows, start=1):
            train = window["train"]
            test = window["test"]
            combined = pd.concat([train, test], ignore_index=True)
            trades = self.backtester.run(
                combined,
                self.strategy_factory(),
                symbol,
                warmup=min(200, len(train)),
                start_index=len(train),
            )
            all_trades.extend(trades)
            window_reports.append(
                {
                    "window": number,
                    "train_candles": len(train),
                    "test_candles": len(test),
                    "report": self.report_generator.generate(trades),
                }
            )

        aggregate_report = self.report_generator.generate(all_trades)
        return {
            "windows": window_reports,
            "aggregate_report": aggregate_report,
            "validation": self.validation_gate.validate(aggregate_report),
            "outcomes_by_direction": {
                "LONG": [trade.return_percent > 0 for trade in all_trades if trade.direction == "LONG"],
                "SHORT": [trade.return_percent > 0 for trade in all_trades if trade.direction == "SHORT"],
            },
        }
