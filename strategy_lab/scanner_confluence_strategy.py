from analysis.analysis import AnalysisEngine
from analysis.indicators import add_indicators
from scanner.market_scanner import MarketScanner
from scanners.rules import RulesEngine
from score.confluence import ConfluenceScore
from strategy_lab.models import TradeSignal


class ScannerConfluenceStrategy:
    """Initial, test-only strategy assembled from the current analysis modules."""

    VERSION = "0.1.0"
    DEFAULT_REWARD_TO_RISK = 2.0

    def __init__(
        self,
        scanner=None,
        rules=None,
        analysis_engine=None,
        confluence_score=None,
        min_confluence=65,
        stop_atr_multiplier=1.5,
        reward_to_risk=DEFAULT_REWARD_TO_RISK,
    ):
        self.scanner = scanner or MarketScanner()
        self.rules = rules or RulesEngine()
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.confluence_score = confluence_score or ConfluenceScore()
        self.min_confluence = min_confluence
        self.stop_atr_multiplier = stop_atr_multiplier
        self.reward_to_risk = reward_to_risk
        self.indicators = None

    def prepare(self, df):
        """Precompute causal indicators once for efficient historical evaluation."""
        self.indicators = add_indicators(df)

    def generate_at(self, index):
        if self.indicators is None:
            raise RuntimeError("prepare must be called before generate_at")
        if index < 199:
            return None

        history = self.indicators.iloc[index - 199: index + 1]
        return self._generate_from_indicators(history)

    def generate(self, history):
        if len(history) < 200:
            return None

        indicators = add_indicators(history)
        return self._generate_from_indicators(indicators)

    def _generate_from_indicators(self, indicators):
        scanner_result = self.scanner.analyze(indicators)

        if scanner_result["signal"] == "NEUTRAL":
            return None

        rules_result = self.rules.check(scanner_result)
        analysis_result = self.analysis_engine.analyze(indicators)
        confluence_result = self.confluence_score.calculate(
            scanner_result,
            rules_result,
            analysis_result,
        )

        if confluence_result["confluence_score"] < self.min_confluence:
            return None

        close = float(indicators.iloc[-1]["close"])
        risk = float(indicators.iloc[-1]["atr"]) * self.stop_atr_multiplier

        if risk <= 0:
            return None

        if scanner_result["trend"] == "LONG":
            return TradeSignal(
                "LONG",
                stop_loss=close - risk,
                take_profit=close + risk * self.reward_to_risk,
            )

        return TradeSignal(
            "SHORT",
            stop_loss=close + risk,
            take_profit=close - risk * self.reward_to_risk,
        )
