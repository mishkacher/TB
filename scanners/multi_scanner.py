from scanners.coins import SCANNER_COINS

from exchanges.bitunix import BitunixClient

from analysis.candles import candles_to_dataframe
from analysis.indicators import add_indicators

from scanner.market_scanner import MarketScanner
from scanners.ranking import RankingEngine
from scanners.rules import RulesEngine



class MultiScanner:


    def __init__(self):

        self.client = BitunixClient()
        self.scanner = MarketScanner()
        self.ranking = RankingEngine()
        self.rules = RulesEngine()



    def scan(self):

        results = []


        for symbol in SCANNER_COINS:

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