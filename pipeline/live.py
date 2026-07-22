from analysis.candles import candles_to_dataframe
from analysis.derivatives import DerivativesContext
from exchanges.bitunix import BitunixClient
from pipeline.candidate_pipeline import CandidatePipeline
from scanners.multi_scanner import MultiScanner


def run_live_candidate_pipeline():
    client = BitunixClient()
    scanner = MultiScanner(client=client)

    def candle_loader(symbol):
        response = client.get_candles(symbol, "15m", 300)
        return candles_to_dataframe(response["data"])

    return CandidatePipeline(
        multi_scanner=scanner,
        candle_loader=candle_loader,
        derivatives_context=DerivativesContext(client),
    ).run()
