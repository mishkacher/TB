#!/usr/bin/env python3
"""Local Backtrader launcher.  It does not contact Telegram or an AI service."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import backtrader as bt


class SmaCross(bt.Strategy):
    """A transparent starter strategy used to verify the Backtrader installation."""

    params = (('fast', 20), ('slow', 50), ('risk_percent', 0.02))

    def __init__(self):
        self.fast_sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.fast)
        self.slow_sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.slow)
        self.cross = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)

    def next(self):
        if not self.position and self.cross > 0:
            cash_to_use = self.broker.getcash() * self.p.risk_percent
            self.buy(size=cash_to_use / self.data.close[0])
        elif self.position and self.cross < 0:
            self.close()


def parse_date(value: str | None) -> datetime | None:
    return datetime.strptime(value, '%Y-%m-%d') if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description='Run a local Backtrader SMA test on OHLCV CSV data.')
    parser.add_argument('--data-file', default='data/historical/btcusdt_15m.csv')
    parser.add_argument('--from-date', help='YYYY-MM-DD, inclusive')
    parser.add_argument('--to-date', help='YYYY-MM-DD, inclusive')
    parser.add_argument('--fast', type=int, default=20)
    parser.add_argument('--slow', type=int, default=50)
    parser.add_argument('--cash', type=float, default=10_000)
    parser.add_argument('--commission', type=float, default=0.0006, help='0.0006 = 0.06%% per side')
    args = parser.parse_args()

    if args.fast >= args.slow:
        parser.error('--fast must be smaller than --slow')
    data_path = Path(args.data_file)
    if not data_path.is_file():
        parser.error(f'CSV file was not found: {data_path}')

    feed = bt.feeds.GenericCSVData(
        dataname=str(data_path),
        dtformat='%Y-%m-%d %H:%M:%S',
        datetime=0, open=1, high=2, low=3, close=4, volume=5,
        openinterest=-1, headers=True,
        fromdate=parse_date(args.from_date), todate=parse_date(args.to_date),
        timeframe=bt.TimeFrame.Minutes, compression=15,
    )
    engine = bt.Cerebro(stdstats=False)
    engine.adddata(feed, name='BTCUSDT')
    engine.addstrategy(SmaCross, fast=args.fast, slow=args.slow)
    engine.broker.setcash(args.cash)
    engine.broker.setcommission(commission=args.commission)
    engine.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    engine.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    result = engine.run()[0]
    trades = result.analyzers.trades.get_analysis()
    drawdown = result.analyzers.drawdown.get_analysis()
    closed = getattr(getattr(trades, 'total', {}), 'closed', 0)
    won = getattr(getattr(trades, 'won', {}), 'total', 0)
    win_rate = won / closed * 100 if closed else 0.0
    final_value = engine.broker.getvalue()

    print('Backtrader local test complete')
    print(f'Data: {data_path} | 15m | SMA {args.fast}/{args.slow}')
    print(f'Start capital: {args.cash:,.2f} USDT')
    print(f'Final capital: {final_value:,.2f} USDT')
    print(f'Net PnL: {final_value - args.cash:,.2f} USDT')
    print(f'Closed trades: {closed} | Wins: {won} | Win rate: {win_rate:.2f}%')
    print(f'Max drawdown: {getattr(getattr(drawdown, "max", {}), "drawdown", 0):.2f}%')


if __name__ == '__main__':
    main()
