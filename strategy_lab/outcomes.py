from strategy_lab.report_store import ReportStore


class StrategyReportRegistry:
    """Resolve the persisted validation report for one symbol and timeframe."""

    def __init__(self, reports_directory="data/reports", version="0_1_0"):
        self.reports_directory = reports_directory
        self.version = version

    def path_for(self, symbol, interval="15m", days=365):
        filename = f"{symbol.lower()}_{interval}_{days}d_v{self.version}.json"
        return f"{self.reports_directory}/{filename}"

    def validation_for(self, symbol, interval="15m", days=365):
        return ReportStore.load_validation(self.path_for(symbol, interval, days))


class ReportOutcomeProvider:
    """Expose persisted out-of-sample trade outcomes to Probability Engine."""

    def __init__(self, report_path):
        self.report_path = report_path

    def outcomes_for(self, direction):
        try:
            report = ReportStore.load(self.report_path)
            outcomes = report["outcomes_by_direction"][direction]
        except (FileNotFoundError, KeyError, ValueError):
            return []
        return [bool(outcome) for outcome in outcomes]

    def __call__(self, candidate):
        try:
            report = ReportStore.load(self.report_path)
        except (FileNotFoundError, ValueError):
            return []
        # A BTC walk-forward result says nothing about the distribution of a
        # SOL or ETH setup.  Refuse cross-symbol probability reuse.
        if report.get("symbol") != candidate.get("symbol"):
            return []
        signal = candidate.get("signal")
        direction = "LONG" if signal == "LONG BIAS" else "SHORT"
        return [
            bool(outcome)
            for outcome in report.get("outcomes_by_direction", {}).get(direction, [])
        ]
