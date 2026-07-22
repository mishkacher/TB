"""Native candle-by-candle test for the Fib limit-order target-cancel rule."""

from __future__ import annotations

import argparse

import pandas as pd

from strategy_lab.models import ClosedTrade
from strategy_lab.orderflow_fibonacci_strategy import OrderflowFibonacciStrategy
from strategy_lab.report import BacktestReport


def limit_fill(candle, signal):
    """Return a limit fill price, or None, using the same gap policy as before."""
    opening, low, high = map(float, (candle['open'], candle['low'], candle['high']))
    if signal.direction == 'LONG':
        if opening <= signal.entry_limit:
            return opening
        return signal.entry_limit if low <= signal.entry_limit <= high else None
    if opening >= signal.entry_limit:
        return opening
    return signal.entry_limit if low <= signal.entry_limit <= high else None


def target_hit_before_entry(candle, signal):
    return (
        float(candle['high']) >= signal.take_profit
        if signal.direction == 'LONG' else float(candle['low']) <= signal.take_profit
    )


def is_valid_entry(price, signal):
    if signal.direction == 'LONG':
        return signal.stop_loss < price < signal.take_profit
    return signal.take_profit < price < signal.stop_loss


def exit_price(candle, signal):
    """Conservative 15m rule: when stop and target share a candle, stop wins."""
    low, high = float(candle['low']), float(candle['high'])
    if signal.direction == 'LONG':
        if low <= signal.stop_loss:
            return signal.stop_loss, 'stop'
        if high >= signal.take_profit:
            return signal.take_profit, 'target'
    else:
        if high >= signal.stop_loss:
            return signal.stop_loss, 'stop'
        if low <= signal.take_profit:
            return signal.take_profit, 'target'
    return None


def main():
    parser = argparse.ArgumentParser(description='Native 15m Fibonacci test with target-cancelled limits.')
    parser.add_argument('--data-file', required=True)
    parser.add_argument('--month', required=True)
    parser.add_argument('--fee-bps-per-side', type=float, default=6.0)
    parser.add_argument('--initial-capital', type=float)
    parser.add_argument('--risk-percent', type=float, help='Capital risked at the stop in each trade')
    parser.add_argument('--hourly', action='store_true')
    parser.add_argument('--local-trend-filter', action='store_true')
    args = parser.parse_args()

    dataframe = pd.read_csv(args.data_file, parse_dates=['time']).sort_values('time')
    dataframe = dataframe[dataframe['time'].dt.to_period('M') == pd.Period(args.month, freq='M')].reset_index(drop=True)
    if args.hourly:
        dataframe = (
            dataframe.set_index('time')
            .resample('1h')
            .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'), volume=('volume', 'sum'))
            .dropna()
            .reset_index()
        )
    ema20 = dataframe['close'].ewm(span=20, adjust=False).mean()
    ema50 = dataframe['close'].ewm(span=50, adjust=False).mean()
    strategy = OrderflowFibonacciStrategy(
        interval='1h' if args.hourly else '15m',
        entry_retracement=0.5,
        take_profit_extension=0.18,
        partial_close_fraction=0,
    )
    strategy.prepare(dataframe)
    pending = None
    position = None
    trades = []
    setups = fills = cancelled_before_entry = invalid_gap_entries = 0
    fee_percent = args.fee_bps_per_side / 100

    for index in range(strategy.minimum_history - 1, len(dataframe)):
        candle = dataframe.iloc[index]
        # Orders generated on this close are eligible only from the next bar.
        if pending is not None and index > pending['signal_index']:
            signal = pending['signal']
            fill = limit_fill(candle, signal)
            if fill is not None:
                order = pending
                pending = None
                if is_valid_entry(fill, signal):
                    position = {**order, 'entry': fill, 'entry_index': index}
                    fills += 1
                else:
                    invalid_gap_entries += 1
            elif target_hit_before_entry(candle, pending['signal']):
                pending = None
                cancelled_before_entry += 1

        if position is not None and index > position['entry_index']:
            outcome = exit_price(candle, position['signal'])
            if outcome:
                price, reason = outcome
                signal = position['signal']
                trades.append(ClosedTrade(
                    symbol='BTCUSDT', direction=signal.direction,
                    entry_price=position['entry'], exit_price=price,
                    risk_per_unit=abs(position['entry'] - signal.stop_loss),
                    entry_fee_percent=fee_percent, exit_fee_percent=fee_percent,
                    exit_reason=reason,
                ))
                position = None

        if pending is None and position is None:
            signal = strategy.generate_at(index)
            if args.local_trend_filter and signal is not None:
                long_trend = dataframe.iloc[index]['close'] > ema20.iloc[index] > ema50.iloc[index]
                short_trend = dataframe.iloc[index]['close'] < ema20.iloc[index] < ema50.iloc[index]
                if index < 49 or (signal.direction == 'LONG' and not long_trend) or (signal.direction == 'SHORT' and not short_trend):
                    signal = None
            if signal is not None:
                pending = {'signal': signal, 'signal_index': index}
                setups += 1

    report = BacktestReport().generate(trades)
    print(f'Нативный тестер | базовая Fibonacci-стратегия | BTCUSDT {"1h" if args.hourly else "15m"}')
    print('Правила: limit 0.5, SL за импульсом, TP −0.18; заявка отменяется при достижении TP до входа')
    print(f'Период: {args.month}')
    print(f'Создано сетапов: {setups} | Исполнено входов: {fills} | Отменено по достижению цели: {cancelled_before_entry} | Отброшено за стопом: {invalid_gap_entries}')
    for key in ('trades', 'wins', 'losses', 'win_rate_percent', 'long_trades', 'long_win_rate_percent', 'short_trades', 'short_win_rate_percent', 'net_return_percent', 'max_drawdown_percent'):
        print(f'{key}: {report[key]}')
    if (args.initial_capital is None) != (args.risk_percent is None):
        parser.error('--initial-capital and --risk-percent must be used together')
    if args.initial_capital is not None:
        if args.initial_capital <= 0 or not 0 < args.risk_percent <= 100:
            parser.error('capital must be positive and risk-percent must be from 0 to 100')
        equity = peak = args.initial_capital
        max_drawdown = 0.0
        bankrupt_on_trade = None
        for trade_number, trade in enumerate(trades, start=1):
            # Risk includes both commission legs at the planned stop. Without
            # this, very tight stops could make fees exceed the stated risk.
            stop_price = (
                trade.entry_price - trade.risk_per_unit
                if trade.direction == 'LONG'
                else trade.entry_price + trade.risk_per_unit
            )
            stop_fees = (
                trade.entry_price * trade.entry_fee_percent / 100
                + stop_price * trade.exit_fee_percent / 100
            )
            worst_loss_per_unit = trade.risk_per_unit + stop_fees
            units = equity * (args.risk_percent / 100) / worst_loss_per_unit
            equity += trade.pnl_per_unit * units
            if equity <= 0:
                equity = 0.0
                bankrupt_on_trade = trade_number
                max_drawdown = 100.0
                break
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100)
        print(f'risk_model: {args.risk_percent:g}% of current capital at stop')
        print(f'initial_capital_usdt: {args.initial_capital:.2f}')
        print(f'final_capital_usdt: {equity:.2f}')
        print(f'profit_usdt: {equity - args.initial_capital:.2f}')
        print(f'portfolio_return_percent: {(equity / args.initial_capital - 1) * 100:.2f}')
        print(f'portfolio_max_drawdown_percent: {max_drawdown:.2f}')
        if bankrupt_on_trade is not None:
            print(f'account_depleted_on_closed_trade: {bankrupt_on_trade}')


if __name__ == '__main__':
    main()
