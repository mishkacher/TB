#!/usr/bin/env python3
"""Resampled Fib test: 0.5 limit, -0.18 target, EMA20/50 trend filter."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

import backtrader as bt
from orderflow_fibonacci import OrderflowFibonacci


def date(value, end=False):
    parsed = datetime.strptime(value, '%Y-%m-%d')
    return parsed + timedelta(days=1) if end else parsed


def get(item, *keys):
    for key in keys:
        item = getattr(item, key, None)
        if item is None:
            return 0
    return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-file', default='data/historical/btcusdt_15m.csv')
    parser.add_argument('--from-date', required=True)
    parser.add_argument('--to-date', required=True)
    parser.add_argument('--cash', type=float, default=100)
    parser.add_argument('--risk-percent', type=float, default=5)
    parser.add_argument('--minutes', type=int, default=60, choices=(5, 60))
    args = parser.parse_args()
    if not Path(args.data_file).is_file():
        parser.error('CSV file was not found')

    feed = bt.feeds.GenericCSVData(
        dataname=args.data_file, dtformat='%Y-%m-%d %H:%M:%S', datetime=0,
        open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
        headers=True, fromdate=date(args.from_date), todate=date(args.to_date, end=True),
        timeframe=bt.TimeFrame.Minutes, compression=15,
    )
    engine = bt.Cerebro(stdstats=False)
    engine.resampledata(feed, timeframe=bt.TimeFrame.Minutes, compression=args.minutes)
    engine.addstrategy(OrderflowFibonacci, risk_percent=args.risk_percent, local_trend_filter=True)
    engine.broker.setcash(args.cash)
    engine.broker.setcommission(commission=0.0, leverage=20)  # model only; no commissions
    engine.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    engine.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    began = perf_counter()
    result = engine.run()[0]
    seconds = perf_counter() - began
    report = result.analyzers.trades.get_analysis()
    closed, wins = get(report, 'total', 'closed'), get(report, 'won', 'total')
    long_total, long_wins = get(report, 'long', 'total'), get(report, 'long', 'won')
    short_total, short_wins = get(report, 'short', 'total'), get(report, 'short', 'won')
    pct = lambda a, b: a / b * 100 if b else 0
    print(f'Backtrader | BTCUSDT {args.minutes}m | Fib 0.5 -> -0.18 | local EMA20/50 trend')
    print(f'Period: {args.from_date} — {args.to_date} | risk: {args.risk_percent:g}% | commission: 0')
    print(f'Run time: {seconds:.3f}s | Setups: {result.setups_created} | Filled: {result.entries_filled} | Cancelled at target: {result.entries_expired}')
    print(f'Closed: {closed} | Win rate: {pct(wins, closed):.2f}%')
    print(f'Long: {long_total} ({pct(long_wins, long_total):.2f}%) | Short: {short_total} ({pct(short_wins, short_total):.2f}%)')
    print(f'Capital: {args.cash:.2f} -> {engine.broker.getvalue():.2f} USDT | PnL: {engine.broker.getvalue() - args.cash:.2f} USDT')
    print(f'Max drawdown: {get(result.analyzers.drawdown.get_analysis(), "max", "drawdown"):.2f}%')


if __name__ == '__main__':
    main()
