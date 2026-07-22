"""Backtrader implementation of the project's baseline 15-minute Fib strategy."""

from __future__ import annotations

import backtrader as bt


class OrderflowFibonacci(bt.Strategy):
    """Confirmed pivot impulse -> 0.5 retracement limit -> -0.18 extension TP.

    The pivot is confirmed only four completed candles after it forms.  This
    avoids future-data leakage: at bar ``n`` we only evaluate the candidate at
    ``n - 4`` using bars that are already closed.
    """

    params = (
        ('pivot_left', 4),
        ('pivot_right', 4),
        ('min_impulse_percent', 1.0),
        ('entry_retracement', 0.5),
        ('take_profit_extension', 0.18),
        ('stake', 1.0),
        ('risk_percent', None),
        ('local_trend_filter', False),
    )

    def __init__(self):
        # Only the parent limit order blocks a new setup.  Once it is filled,
        # ``self.position`` performs that role while its stop/target children
        # remain active in the broker.
        self.entry_order: bt.Order | None = None
        self.last_pivot_low: float | None = None
        self.last_pivot_high: float | None = None
        self.setups_created = 0
        self.entries_filled = 0
        self.entries_expired = 0
        self.ema20 = bt.indicators.ExponentialMovingAverage(self.data.close, period=20)
        self.ema50 = bt.indicators.ExponentialMovingAverage(self.data.close, period=50)

    def notify_order(self, order):
        is_parent = self.entry_order is not None and order.ref == self.entry_order.ref
        if is_parent and order.status == order.Completed:
            self.entries_filled += 1
        if is_parent and order.status in (order.Canceled, order.Expired, order.Margin, order.Rejected):
            self.entries_expired += 1
        if order.status in (order.Completed, order.Canceled, order.Expired, order.Margin, order.Rejected):
            if is_parent:
                self.entry_order = None

    def next(self):
        if len(self.data) < max(self.p.pivot_left + self.p.pivot_right + 1, 50):
            return
        candidate = -self.p.pivot_right
        highs = [self.data.high[i] for i in range(-(self.p.pivot_left + self.p.pivot_right), 1)]
        lows = [self.data.low[i] for i in range(-(self.p.pivot_left + self.p.pivot_right), 1)]
        candidate_high = self.data.high[candidate]
        candidate_low = self.data.low[candidate]
        is_high = candidate_high == max(highs)
        is_low = candidate_low == min(lows)

        # Retain pivots while a position/order is active. The native strategy
        # searches this historical structure when it becomes free again.
        if self.entry_order is not None:
            self._remember_pivots(is_high, is_low, candidate_high, candidate_low)
            # A setup ceases to exist once price reaches its intended target
            # before the retracement limit is filled. Broker execution happens
            # before ``next``: if the same candle touched entry and target, an
            # entry has precedence because the parent order is already filled.
            target = self.entry_order.info.cancel_on_target
            hit_target = (
                self.data.high[0] >= target
                if self.entry_order.isbuy() else self.data.low[0] <= target
            )
            if hit_target:
                self.cancel(self.entry_order)
            return
        if self.position:
            self._remember_pivots(is_high, is_low, candidate_high, candidate_low)
            return

        # Match the original strategy: generate a signal before saving the
        # newly confirmed pivot as a possible anchor for the next signal.
        if is_high and self.last_pivot_low is not None:
            self._open_long(low=self.last_pivot_low, high=candidate_high)
        elif is_low and self.last_pivot_high is not None:
            self._open_short(high=self.last_pivot_high, low=candidate_low)

        self._remember_pivots(is_high, is_low, candidate_high, candidate_low)

    def _remember_pivots(self, is_high, is_low, candidate_high, candidate_low):
        if is_high:
            self.last_pivot_high = candidate_high
        if is_low:
            self.last_pivot_low = candidate_low

    def _open_long(self, low: float, high: float):
        if self.p.local_trend_filter and not (self.data.close[0] > self.ema20[0] > self.ema50[0]):
            return
        if (high - low) / low * 100 < self.p.min_impulse_percent:
            return
        impulse = high - low
        entry = high - impulse * self.p.entry_retracement
        target = high + impulse * self.p.take_profit_extension
        size = self._position_size(entry, low)
        orders = self.buy_bracket(
            size=size, price=entry, exectype=bt.Order.Limit,
            stopprice=low, limitprice=target,
        )
        self.entry_order = orders[0]
        self.entry_order.addinfo(cancel_on_target=target)
        self.setups_created += 1

    def _open_short(self, high: float, low: float):
        if self.p.local_trend_filter and not (self.data.close[0] < self.ema20[0] < self.ema50[0]):
            return
        if (high - low) / high * 100 < self.p.min_impulse_percent:
            return
        impulse = high - low
        entry = low + impulse * self.p.entry_retracement
        target = low - impulse * self.p.take_profit_extension
        size = self._position_size(entry, high)
        orders = self.sell_bracket(
            size=size, price=entry, exectype=bt.Order.Limit,
            stopprice=high, limitprice=target,
        )
        self.entry_order = orders[0]
        self.entry_order.addinfo(cancel_on_target=target)
        self.setups_created += 1

    def _position_size(self, entry, stop):
        if self.p.risk_percent is None:
            return self.p.stake
        return self.broker.getvalue() * self.p.risk_percent / 100 / abs(entry - stop)
