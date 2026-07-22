#!/usr/bin/env python3
"""Run the baseline order-flow Fibonacci strategy in local Backtrader."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

import backtrader as bt

from orderflow_fibonacci import OrderflowFibonacci


def date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    parsed = datetime.strptime(value, '%Y-%m-%d') if value else None
    return parsed + timedelta(days=1) if parsed and end_of_day else parsed


def value(mapping, *path, default=0):
    for key in path:
        mapping = getattr(mapping, key, None)
        if mapping is None:
            return default
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description='Backtrader baseline 15m order-flow Fibonacci test.')
    parser.add_argument('--data-file', default='data/historical/btcusdt_15m.csv')
    parser.add_argument('--from-date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--to-date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--cash', type=float, default=100_000)
    parser.add_argument('--stake', type=float, default=0.01, help='BTC per trade')
    parser.add_argument('--commission', type=float, default=0.0006)
    args = parser.parse_args()

    path = Path(args.data_file)
    if not path.is_file():
        parser.error(f'CSV file was not found: {path}')
    feed = bt.feeds.GenericCSVData(
        dataname=str(path), dtformat='%Y-%m-%d %H:%M:%S',
        datetime=0, open=1, high=2, low=3, close=4, volume=5,
        openinterest=-1, headers=True, fromdate=date(args.from_date), todate=date(args.to_date, end_of_day=True),
        timeframe=bt.TimeFrame.Minutes, compression=15,
    )
    engine = bt.Cerebro(stdstats=False)
    engine.adddata(feed, name='BTCUSDT')
    engine.addstrategy(OrderflowFibonacci, stake=args.stake)
    engine.broker.setcash(args.cash)
    engine.broker.setcommission(commission=args.commission)
    engine.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    engine.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    started = perf_counter()
    result = engine.run()[0]
    elapsed = perf_counter() - started
    report = result.analyzers.trades.get_analysis()
    drawdown = result.analyzers.drawdown.get_analysis()
    closed = value(report, 'total', 'closed')
    won = value(report, 'won', 'total')
    lost = value(report, 'lost', 'total')
    long_closed = value(report, 'long', 'total')
    long_won = value(report, 'long', 'won')
    short_closed = value(report, 'short', 'total')
    short_won = value(report, 'short', 'won')
    pct = lambda wins, total: wins / total * 100 if total else 0.0

    print('Backtrader | базовая Fibonacci-стратегия | BTCUSDT 15m')
    print('Правила: подтверждённый импульс, limit 0.5, SL за импульсом, TP −0.18; заявка отменяется при достижении TP до входа')
    print(f'Период: {args.from_date} — {args.to_date}')
    print(f'Время расчёта: {elapsed:.3f} с')
    print(f'Создано сетапов: {result.setups_created}')
    print(f'Исполнено входов: {result.entries_filled} | Отменено при достижении цели: {result.entries_expired}')
    print(f'Сделки: {closed} | Победы: {won} | Убытки: {lost} | Win rate: {pct(won, closed):.2f}%')
    print(f'Long: {long_closed} ({pct(long_won, long_closed):.2f}%) | Short: {short_closed} ({pct(short_won, short_closed):.2f}%)')
    print(f'Старт: {args.cash:,.2f} USDT | Финал: {engine.broker.getvalue():,.2f} USDT | PnL: {engine.broker.getvalue() - args.cash:,.2f} USDT')
    print(f'Максимальная просадка: {value(drawdown, "max", "drawdown"):.2f}%')


if __name__ == '__main__':
    main()
