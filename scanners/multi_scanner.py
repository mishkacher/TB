from scanners.coins import SCANNER_COINS

from exchanges.bitunix import BitunixClient

from analysis.candles import candles_to_dataframe
from analysis.indicators import add_indicators

from scanner.market_scanner import MarketScanner
from scanners.ranking import RankingEngine
from scanners.rules import RulesEngine



class MultiScanner:


    def __init__(
        self,
        client=None,
        scanner=None,
        ranking=None,
        rules=None,
        symbols=None,
    ):

        self.client = client or BitunixClient()
        self.scanner = scanner or MarketScanner()
        self.ranking = ranking or RankingEngine()
        self.rules = rules or RulesEngine()
        self.symbols = symbols or SCANNER_COINS



    def scan(self):

        results = []


        for symbol in self.symbols:

            try:

                print(f"Scanning {symbol}...")


                response = self.client.get_candles(
                    symbol,
                    "15m",
                    300
                )


                candles = response["data"]


                df = candles_to_dataframe(
                    candles
                )


                df = add_indicators(
                    df
                )


                result = self.scanner.analyze(
                    df
                )


                ranking = self.ranking.calculate(
                    result
                )


                rules = self.rules.check(
                    result
                )


                results.append({

                    "symbol": symbol,

                    **result,

                    **ranking,

                    **rules

                })


            except Exception as e:

                print(
                    symbol,
                    "error:",
                    e
                )


        results.sort(
            key=lambda x: x["ranking_score"],
            reverse=True
        )


        return results[:5]
