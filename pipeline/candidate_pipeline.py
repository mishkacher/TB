from analysis.analysis import AnalysisEngine
from score.confluence import ConfluenceScore


class CandidatePipeline:
    """Enrich Scanner candidates with chart analysis and confluence data.

    The pipeline deliberately returns candidates, not trade decisions. Probability
    and Decision Engine are introduced only after Strategy Lab validation.
    """

    def __init__(
        self,
        multi_scanner,
        candle_loader,
        analysis_engine=None,
        confluence_score=None,
        derivatives_context=None,
    ):
        self.multi_scanner = multi_scanner
        self.candle_loader = candle_loader
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.confluence_score = confluence_score or ConfluenceScore()
        self.derivatives_context = derivatives_context

    def run(self):
        candidates = []

        for scanner_result in self.multi_scanner.scan():
            symbol = scanner_result["symbol"]
            analysis_result = self.analysis_engine.analyze(
                self.candle_loader(symbol)
            )
            derivatives = (
                self.derivatives_context.analyze(symbol)
                if self.derivatives_context
                else None
            )
            confluence_result = self.confluence_score.calculate(
                scanner_result,
                scanner_result,
                analysis_result,
                derivatives,
            )
            candidates.append(
                {
                    **scanner_result,
                    "analysis": analysis_result,
                    "derivatives": derivatives,
                    **confluence_result,
                }
            )

        return sorted(
            candidates,
            key=lambda candidate: (
                candidate["confluence_score"],
                candidate["ranking_score"],
            ),
            reverse=True,
        )
