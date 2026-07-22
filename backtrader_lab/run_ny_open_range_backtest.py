#!/usr/bin/env python3
"""Monthly Backtrader report for the New York first-4H opening-range strategy."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

import backtrader as bt


def in_fibonacci_zone(close, low, high, direction, fib_low=0.5, fib_high=0.618):
    width = high - low
    if direction == "LONG":
        lower, upper = low + width * fib_low, low + width * fib_high
    else:
        lower, upper = low + width * (1 - fib_high), low + width * (1 - fib_low)
    return lower <= close <= upper


NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


class NewYorkOpeningRange(bt.Strategy):
    """Fade a confirmed 5m break/reclaim of the first New York 4H range."""

    params = (("stake", 1.0), ("stop_buffer", 0.001), ("reward_to_risk", 2.0),
              ("fvg_5m", None), ("fvg_10m", None), ("fvg_15m", None),
              ("fvg_1h", None), ("fvg_4h", None),
              ("fvg_4h_age", None), ("max_fvg_4h_age_hours", None),
              ("fvg_mode", "either"), ("fib_low", 0.5), ("fib_high", 0.618),
              ("direction_mode", "both"), ("entry_start_hour", 4),
              ("entry_end_hour", 24), ("reclaim_mode", "full"),
              ("trend_filter", "none"),
              ("mark_open_at_end", True),
              ("slippage", 0.0),
              ("taker_commission", None), ("maker_commission", None))

    def __init__(self):
        self.session_date = None
        self.range_high = self.range_low = None
        self.range_ready = self.break_side = None
        self.break_wick = None
        self.range_valid = self.range_last_utc = None
        self.entry_order = self.stop_order = self.target_order = None
        self.active_risk = self.active_signal_time = self.active_fill_time = None
        self.active_entry_price = self.active_target = None
        self.active_exit_price = self.active_exit_reason = None
        self.active_stop = self.active_direction = None
        self.active_fvg_15m = self.active_fvg_4h = False
        self.active_fvg_10m = False
        self.active_fvg_4h_age = None
        self.active_custom_commission = 0.0
        self.ema_48 = self.ema_288 = self.ema_2016 = None
        self.records = []
        self.signal_times = []

    def _ny_time(self):
        naive = bt.num2date(self.data.datetime[0])
        return naive.replace(tzinfo=UTC).astimezone(NY)

    @staticmethod
    def _ema(previous, close, period):
        if previous is None:
            return close
        alpha = 2.0 / (period + 1.0)
        return alpha * close + (1.0 - alpha) * previous

    def _update_trend(self):
        close = float(self.data.close[0])
        self.ema_48 = self._ema(self.ema_48, close, 48)
        self.ema_288 = self._ema(self.ema_288, close, 288)
        self.ema_2016 = self._ema(self.ema_2016, close, 2016)

    def _trend_allows(self, direction):
        if self.p.trend_filter == "none":
            return True
        if self.p.trend_filter == "weekly_aligned":
            if direction == "LONG":
                return self.ema_288 > self.ema_2016
            return self.ema_288 < self.ema_2016
        if self.p.trend_filter == "local_contra":
            if direction == "LONG":
                return self.ema_48 < self.ema_288
            return self.ema_48 > self.ema_288
        raise ValueError(f"unsupported trend filter: {self.p.trend_filter}")

    def next(self):
        now = self._ny_time()
        self._update_trend()
        if now.date() != self.session_date:
            self.session_date = now.date()
            self.range_high = self.range_low = None
            self.range_ready = self.break_side = None
            self.break_wick = None
            self.range_valid = True
            self.range_last_utc = None

        # The range is exactly the closed candles from 00:00 through 03:55 NY.
        if now.hour < 4:
            utc_now = now.astimezone(UTC)
            if self.range_last_utc is None:
                self.range_valid = now.hour == 0 and now.minute == 0
            elif utc_now - self.range_last_utc != timedelta(minutes=5):
                self.range_valid = False
            self.range_last_utc = utc_now
            high, low = float(self.data.high[0]), float(self.data.low[0])
            self.range_high = high if self.range_high is None else max(self.range_high, high)
            self.range_low = low if self.range_low is None else min(self.range_low, low)
            return
        complete_range = (
            self.range_valid
            and self.range_last_utc is not None
            and (self.range_last_utc.astimezone(NY).hour, self.range_last_utc.astimezone(NY).minute)
            == (3, 55)
        )
        if not complete_range:
            return
        if self.range_high is None or self.position or self.entry_order:
            return
        self.range_ready = True
        if self.break_side == "TRADED":
            return
        if self.break_side is None:
            # "Body closes outside" = both open and close are beyond the range.
            body_low = min(float(self.data.open[0]), float(self.data.close[0]))
            body_high = max(float(self.data.open[0]), float(self.data.close[0]))
            if body_high < self.range_low:
                self.break_side, self.break_wick = "LOW", float(self.data.low[0])
            elif body_low > self.range_high:
                self.break_side, self.break_wick = "HIGH", float(self.data.high[0])
            return

        # Keep the most extreme wick of the entire breakout leg.
        if self.break_side == "LOW":
            self.break_wick = min(self.break_wick, float(self.data.low[0]))
        else:
            self.break_wick = max(self.break_wick, float(self.data.high[0]))

        # A reclaim requires the full 5m body back inside the 4H range.
        body_low = min(float(self.data.open[0]), float(self.data.close[0]))
        body_high = max(float(self.data.open[0]), float(self.data.close[0]))
        full_body_inside = body_low >= self.range_low and body_high <= self.range_high
        close_inside = self.range_low <= float(self.data.close[0]) <= self.range_high
        if self.p.reclaim_mode == "full" and not full_body_inside:
            return
        if self.p.reclaim_mode == "close" and not close_inside:
            return
        expected_entry = float(self.data.close[0])
        if self.break_side == "LOW":
            direction, fvg_direction = "LONG", "bullish"
            stop = self.break_wick * (1 - self.p.stop_buffer)
        else:
            direction, fvg_direction = "SHORT", "bearish"
            stop = self.break_wick * (1 + self.p.stop_buffer)
        if self.p.direction_mode != "both" and direction.lower() != self.p.direction_mode:
            return
        if not self._trend_allows(direction):
            return
        if not self.p.entry_start_hour <= now.hour < self.p.entry_end_hour:
            return
        utc_key = now.astimezone(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        has_5m = fvg_direction in (self.p.fvg_5m or {}).get(utc_key, set())
        has_10m = fvg_direction in (self.p.fvg_10m or {}).get(utc_key, set())
        has_15m = fvg_direction in (self.p.fvg_15m or {}).get(utc_key, set())
        has_1h = fvg_direction in (self.p.fvg_1h or {}).get(utc_key, set())
        has_4h = fvg_direction in (self.p.fvg_4h or {}).get(utc_key, set())
        fvg_4h_age = (self.p.fvg_4h_age or {}).get(utc_key, {}).get(fvg_direction)
        if self.p.max_fvg_4h_age_hours is not None:
            has_4h = (
                has_4h
                and fvg_4h_age is not None
                and fvg_4h_age <= self.p.max_fvg_4h_age_hours
            )
        fvg_allowed = {
            "5m": has_5m,
            "10m": has_10m,
            "15m": has_15m,
            "1h": has_1h,
            "4h": has_4h,
            "both": has_15m and has_4h,
            "either": has_15m or has_4h,
            "10m_or_4h": has_10m or has_4h,
            "10m_or_15m": has_10m or has_15m,
            "10m_and_15m": has_10m and has_15m,
            "any": has_5m or has_10m or has_15m or has_1h or has_4h,
        }[self.p.fvg_mode]
        if not fvg_allowed:
            return
        if not in_fibonacci_zone(
            expected_entry, self.range_low, self.range_high, direction,
            self.p.fib_low, self.p.fib_high,
        ):
            return
        self.entry_order = self.buy(size=self.p.stake) if direction == "LONG" else self.sell(size=self.p.stake)
        self.signal_times.append(now.isoformat())
        self.active_signal_time = now
        self.active_stop, self.active_direction = stop, direction
        self.active_fvg_15m, self.active_fvg_4h = has_15m, has_4h
        self.active_fvg_10m = has_10m
        self.active_fvg_4h_age = fvg_4h_age if has_4h else None
        # One completed setup per New York day.
        self.break_side = "TRADED"

    def notify_order(self, order):
        terminal = (order.Completed, order.Canceled, order.Margin, order.Rejected, order.Expired)
        if order.status not in terminal:
            return
        if self.entry_order is not None and order.ref == self.entry_order.ref:
            self.entry_order = None
            if order.status == order.Completed:
                entry = float(order.executed.price)
                self.active_fill_time = self._ny_time()
                self.active_entry_price = entry
                if self.p.taker_commission is not None:
                    self.active_custom_commission = (
                        abs(order.executed.price * order.executed.size)
                        * self.p.taker_commission
                    )
                risk_per_unit = abs(entry - self.active_stop)
                self.active_risk = risk_per_unit * self.p.stake
                if self.active_direction == "LONG":
                    target = entry + risk_per_unit * self.p.reward_to_risk
                    self.stop_order = self.sell(size=self.p.stake, exectype=bt.Order.Stop, price=self.active_stop)
                    self.target_order = self.sell(size=self.p.stake, exectype=bt.Order.Limit, price=target, oco=self.stop_order)
                else:
                    target = entry - risk_per_unit * self.p.reward_to_risk
                    self.stop_order = self.buy(size=self.p.stake, exectype=bt.Order.Stop, price=self.active_stop)
                    self.target_order = self.buy(size=self.p.stake, exectype=bt.Order.Limit, price=target, oco=self.stop_order)
                self.active_target = target
            else:
                self.active_risk = self.active_signal_time = self.active_fill_time = None
                self.active_entry_price = self.active_target = None
            return
        if order.status == order.Completed:
            if self.stop_order is not None and order.ref == self.stop_order.ref:
                exit_rate = self.p.taker_commission
                self.active_exit_reason = "stop"
            elif self.target_order is not None and order.ref == self.target_order.ref:
                exit_rate = self.p.maker_commission
                self.active_exit_reason = "target"
            else:
                return
            self.active_exit_price = float(order.executed.price)
            if self.p.taker_commission is not None:
                self.active_custom_commission += (
                    abs(order.executed.price * order.executed.size) * exit_rate
                )

    def notify_trade(self, trade):
        if not trade.isclosed or not self.active_risk:
            return
        net_pnl = (
            trade.pnl - self.active_custom_commission
            if self.p.taker_commission is not None
            else trade.pnlcomm
        )
        self.records.append({
            "signal_time_ny": self.active_signal_time.isoformat(),
            "entry_time_ny": self.active_fill_time.isoformat(),
            "close_time_ny": self._ny_time().isoformat(),
            "direction": "LONG" if trade.long else "SHORT",
            "entry_price": self.active_entry_price,
            "stop_price": self.active_stop,
            "target_price": self.active_target,
            "exit_price": self.active_exit_price,
            "exit_reason": self.active_exit_reason,
            "fvg_15m": self.active_fvg_15m,
            "fvg_4h": self.active_fvg_4h,
            "fvg_10m": self.active_fvg_10m,
            "fvg_4h_age_hours": self.active_fvg_4h_age,
            "pnl": round(net_pnl, 6),
            "r_multiple": round(net_pnl / self.active_risk, 6),
        })
        self.active_risk = self.active_signal_time = self.active_fill_time = None
        self.active_entry_price = self.active_target = None
        self.active_exit_price = self.active_exit_reason = None
        self.active_custom_commission = 0.0
        self.stop_order = self.target_order = None

    def stop(self):
        """Mark any final open position to the last close instead of hiding it."""
        if not self.p.mark_open_at_end or not self.position or not self.active_risk:
            return
        close = float(self.data.close[0])
        # A synthetic end-of-data liquidation must use the same adverse
        # slippage convention as a real market exit.
        exit_price = close * (
            1 - self.p.slippage if self.position.size > 0 else 1 + self.p.slippage
        )
        gross_pnl = self.position.size * (exit_price - float(self.position.price))
        if self.p.taker_commission is not None:
            exit_fee = abs(exit_price * self.position.size) * self.p.taker_commission
            net_pnl = gross_pnl - self.active_custom_commission - exit_fee
        else:
            net_pnl = gross_pnl
        self.records.append({
            "signal_time_ny": self.active_signal_time.isoformat(),
            "entry_time_ny": self.active_fill_time.isoformat(),
            "close_time_ny": self._ny_time().isoformat(),
            "direction": self.active_direction,
            "entry_price": self.active_entry_price,
            "stop_price": self.active_stop,
            "target_price": self.active_target,
            "exit_price": exit_price,
            "fvg_15m": self.active_fvg_15m,
            "fvg_4h": self.active_fvg_4h,
            "fvg_10m": self.active_fvg_10m,
            "fvg_4h_age_hours": self.active_fvg_4h_age,
            "pnl": round(net_pnl, 6),
            "r_multiple": round(net_pnl / self.active_risk, 6),
            "exit_reason": "end_of_data_mark",
        })


def make_feed(path):
    return bt.feeds.GenericCSVData(
        dataname=str(path), dtformat="%Y-%m-%d %H:%M:%S", datetime=0,
        open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
        headers=True, timeframe=bt.TimeFrame.Minutes, compression=5,
    )


def monthly_summary(records):
    by_month = defaultdict(list)
    for item in records:
        by_month[item["entry_time_ny"][:7]].append(item)
    rows = []
    for month in sorted(by_month):
        trades = by_month[month]
        longs = [x for x in trades if x["direction"] == "LONG"]
        shorts = [x for x in trades if x["direction"] == "SHORT"]
        wins = [x for x in trades if x["r_multiple"] > 0]
        gross_win = sum(x["r_multiple"] for x in wins)
        gross_loss = abs(sum(x["r_multiple"] for x in trades if x["r_multiple"] < 0))
        wr = lambda values: round(sum(x["r_multiple"] > 0 for x in values) / len(values) * 100, 2) if values else 0.0
        rows.append({"month": month, "trades": len(trades), "long_trades": len(longs), "short_trades": len(shorts), "win_rate_percent": wr(trades), "long_win_rate_percent": wr(longs), "short_win_rate_percent": wr(shorts), "net_r": round(sum(x["r_multiple"] for x in trades), 4), "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else None})
    return rows


def risk_summary(records, initial_capital, risk_percent):
    equity = peak_equity = float(initial_capital)
    cumulative_r = peak_r = max_drawdown_r = 0.0
    max_drawdown_percent = 0.0
    loss_streak = longest_loss_streak = 0
    for item in records:
        value = float(item["r_multiple"])
        cumulative_r += value
        peak_r = max(peak_r, cumulative_r)
        max_drawdown_r = max(max_drawdown_r, peak_r - cumulative_r)
        equity *= 1 + value * risk_percent / 100
        peak_equity = max(peak_equity, equity)
        if peak_equity:
            max_drawdown_percent = max(
                max_drawdown_percent,
                (peak_equity - equity) / peak_equity * 100,
            )
        if value < 0:
            loss_streak += 1
            longest_loss_streak = max(longest_loss_streak, loss_streak)
        else:
            loss_streak = 0
    return {
        "initial_capital": initial_capital,
        "risk_percent_per_trade": risk_percent,
        "final_capital": round(equity, 2),
        "profit": round(equity - initial_capital, 2),
        "return_percent": round((equity / initial_capital - 1) * 100, 2),
        "max_drawdown_percent": round(max_drawdown_percent, 2),
        "max_drawdown_r": round(max_drawdown_r, 4),
        "longest_loss_streak": longest_loss_streak,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", required=True)
    parser.add_argument("--report-file", required=True)
    parser.add_argument("--features-file")
    parser.add_argument("--fvg-4h-age-file")
    parser.add_argument("--max-fvg-4h-age-hours", type=float)
    parser.add_argument(
        "--fvg-mode",
        choices=("5m", "10m", "15m", "1h", "4h", "both", "either", "10m_or_4h", "10m_or_15m", "10m_and_15m", "any"),
        default="either",
    )
    parser.add_argument("--stake", type=float, default=1.0)
    parser.add_argument("--initial-capital", type=float, default=1000.0)
    parser.add_argument("--risk-percent", type=float, default=5.0)
    parser.add_argument("--reward-to-risk", type=float, default=2.0)
    parser.add_argument("--stop-buffer", type=float, default=0.001)
    parser.add_argument("--fib-low", type=float, default=0.5)
    parser.add_argument("--fib-high", type=float, default=0.618)
    parser.add_argument("--direction", choices=("both", "long", "short"), default="both")
    parser.add_argument(
        "--trend-filter",
        choices=("none", "weekly_aligned", "local_contra"),
        default="none",
    )
    parser.add_argument("--entry-start-hour", type=int, default=4)
    parser.add_argument("--entry-end-hour", type=int, default=24)
    parser.add_argument("--commission", type=float, default=0.0, help="commission fraction per side")
    parser.add_argument("--taker-commission", type=float, help="taker commission fraction per execution")
    parser.add_argument("--maker-commission", type=float, help="maker commission fraction per execution")
    parser.add_argument("--slippage", type=float, default=0.0, help="slippage fraction per execution")
    parser.add_argument("--reclaim-mode", choices=("full", "close"), default="full")
    parser.add_argument(
        "--exclude-open-at-end",
        action="store_true",
        help="exclude rather than mark an open final position to the last close",
    )
    args = parser.parse_args()
    path = Path(args.data_file)
    if not path.is_file():
        parser.error(f"CSV not found: {path}")
    if not 0 <= args.fib_low < args.fib_high <= 1:
        parser.error("Fibonacci bounds must satisfy 0 <= low < high <= 1")
    if not 4 <= args.entry_start_hour < args.entry_end_hour <= 24:
        parser.error("Entry hours must satisfy 4 <= start < end <= 24")
    if args.initial_capital <= 0 or not 0 < args.risk_percent < 100:
        parser.error("Initial capital must be positive and risk must be between 0 and 100")
    if (args.taker_commission is None) != (args.maker_commission is None):
        parser.error("--taker-commission and --maker-commission must be supplied together")
    if args.max_fvg_4h_age_hours is not None and not args.fvg_4h_age_file:
        parser.error("--max-fvg-4h-age-hours requires --fvg-4h-age-file")
    if args.features_file:
        feature_payload = json.loads(Path(args.features_file).read_text())
        fvg_5m = {key: set(value) for key, value in feature_payload.get("5m", {}).items()}
        fvg_10m = {key: set(value) for key, value in feature_payload.get("10m", {}).items()}
        fvg_15m = {key: set(value) for key, value in feature_payload["15m"].items()}
        fvg_1h = {key: set(value) for key, value in feature_payload.get("1h", {}).items()}
        fvg_4h = {key: set(value) for key, value in feature_payload["4h"].items()}
    else:
        import pandas as pd
        from strategy_lab.ny_open_range_features import build_all_fvg_features
        frame = pd.read_csv(path, parse_dates=["time"]).sort_values("time").reset_index(drop=True)
        raw = build_all_fvg_features(frame)
        raw_5m, raw_10m, raw_15m, raw_1h, raw_4h = (
            raw["5m"], raw["10m"], raw["15m"], raw["1h"], raw["4h"]
        )
        fvg_5m = {str(key): value for key, value in raw_5m.items() if value}
        fvg_10m = {str(key): value for key, value in raw_10m.items() if value}
        fvg_15m = {str(key): value for key, value in raw_15m.items() if value}
        fvg_1h = {str(key): value for key, value in raw_1h.items() if value}
        fvg_4h = {str(key): value for key, value in raw_4h.items() if value}
    if args.fvg_4h_age_file:
        age_payload = json.loads(Path(args.fvg_4h_age_file).read_text())
        fvg_4h_age = {
            key: {direction: float(age) for direction, age in value.items()}
            for key, value in age_payload["4h"].items()
        }
    else:
        fvg_4h_age = {}
    engine = bt.Cerebro(stdstats=False)
    engine.adddata(make_feed(path))
    engine.addstrategy(
        NewYorkOpeningRange,
        stake=args.stake,
        reward_to_risk=args.reward_to_risk,
        stop_buffer=args.stop_buffer,
        fib_low=args.fib_low,
        fib_high=args.fib_high,
        direction_mode=args.direction,
        entry_start_hour=args.entry_start_hour,
        entry_end_hour=args.entry_end_hour,
        reclaim_mode=args.reclaim_mode,
        fvg_5m=fvg_5m,
        fvg_10m=fvg_10m,
        fvg_15m=fvg_15m,
        fvg_1h=fvg_1h,
        fvg_4h=fvg_4h,
        fvg_4h_age=fvg_4h_age,
        max_fvg_4h_age_hours=args.max_fvg_4h_age_hours,
        fvg_mode=args.fvg_mode,
        trend_filter=args.trend_filter,
        mark_open_at_end=not args.exclude_open_at_end,
        slippage=args.slippage,
        taker_commission=args.taker_commission,
        maker_commission=args.maker_commission,
    )
    # R-multiples are position-size independent; ample virtual capital prevents
    # Backtrader from rejecting a 1 BTC test order solely for margin reasons.
    engine.broker.setcash(10_000_000)
    engine.broker.setcommission(
        commission=0.0 if args.taker_commission is not None else args.commission
    )
    if args.slippage:
        engine.broker.set_slippage_perc(args.slippage)
    result = engine.run()[0]
    rows = monthly_summary(result.records)
    all_records = result.records
    wins = [x for x in all_records if x["r_multiple"] > 0]
    losses = [x for x in all_records if x["r_multiple"] < 0]
    aggregate = {
        "trades": len(all_records),
        "long_trades": sum(x["direction"] == "LONG" for x in all_records),
        "short_trades": sum(x["direction"] == "SHORT" for x in all_records),
        "win_rate_percent": round(len(wins) / len(all_records) * 100, 2) if all_records else 0.0,
        "net_r": round(sum(x["r_multiple"] for x in all_records), 4),
        "average_r": round(mean(x["r_multiple"] for x in all_records), 4) if all_records else 0.0,
        "profit_factor": round(sum(x["r_multiple"] for x in wins) / abs(sum(x["r_multiple"] for x in losses)), 4) if losses else None,
        "risk_model": risk_summary(
            all_records, args.initial_capital, args.risk_percent
        ),
        "both_fvg_trades": sum(
            (x.get("fvg_10m", False) and x["fvg_4h"])
            if args.fvg_mode == "10m_or_4h"
            else (x["fvg_15m"] and x["fvg_4h"])
            for x in all_records
        ),
        "assumptions": {"timezone": "America/New_York", "first_4h_range": "complete 00:00-04:00 NY", "signal": f"full 5m body outside, then {args.reclaim_mode} reclaim inside", "fvg": f"direction-aligned active FVG filter: {args.fvg_mode}", "max_fvg_4h_age_hours": args.max_fvg_4h_age_hours, "fibonacci": f"{args.fib_low:g}-{args.fib_high:g} of first NY 4H range", "direction": args.direction, "trend_filter": args.trend_filter, "entry_hours_ny": f"{args.entry_start_hour:02d}:00-{args.entry_end_hour:02d}:00", "stop": f"extreme breakout wick plus/minus {args.stop_buffer * 100:g}%", "target": f"{args.reward_to_risk:g}R from actual fill", "open_at_end": "excluded" if args.exclude_open_at_end else "marked to last close with taker exit fee", "commission_per_side": args.commission if args.taker_commission is None else None, "taker_commission": args.taker_commission, "maker_commission": args.maker_commission, "slippage_per_execution": args.slippage},
    }
    report_path = Path(args.report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"monthly": rows, "overall": aggregate, "trades": all_records}, ensure_ascii=False, indent=2))
    csv_path = report_path.with_suffix(".csv")
    with csv_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else ["month"])
        writer.writeheader(); writer.writerows(rows)
    signal_months = defaultdict(int)
    for value in result.signal_times:
        signal_months[value[:7]] += 1
    print(json.dumps({"monthly": rows, "overall": aggregate, "signal_months": dict(signal_months), "last_record": all_records[-1] if all_records else None, "final_position_size": engine.broker.getposition(engine.datas[0]).size, "report": str(report_path), "csv": str(csv_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
