from strategy_lab.models import ClosedTrade


class Backtester:
    """Run a signal strategy without allowing it to see future candles."""

    def __init__(self, fee_percent_per_side=0.0, slippage_percent_per_side=0.0):
        if fee_percent_per_side < 0 or slippage_percent_per_side < 0:
            raise ValueError("fees and slippage cannot be negative")
        self.fee_percent_per_side = fee_percent_per_side
        self.slippage_percent_per_side = slippage_percent_per_side

    def run(self, df, strategy, symbol, warmup=200, start_index=None):
        if len(df) <= warmup:
            raise ValueError("Not enough candles for the selected warmup")

        trades = []
        # ``start_index`` lets a walk-forward run use the preceding training
        # candles as context while opening trades only in its test segment.
        index = max(warmup - 1, (start_index or 0) - 1)

        if hasattr(strategy, "prepare"):
            strategy.prepare(df)

        while index < len(df) - 1:
            if hasattr(strategy, "generate_at"):
                signal = strategy.generate_at(index)
            else:
                history = df.iloc[: index + 1].copy()
                signal = strategy.generate(history)

            if signal is None:
                index += 1
                continue

            enter_on_signal_close = bool(
                getattr(strategy, "enter_on_signal_close", False)
            )
            entry_index, reference_entry = self._entry_for_signal(
                df, index if enter_on_signal_close else index + 1, signal,
                enter_on_signal_close=enter_on_signal_close,
                max_entry_index=(
                    index + getattr(strategy, "limit_order_expiry_candles")
                    if getattr(strategy, "limit_order_expiry_candles", None)
                    else None
                ),
            )
            if entry_index is None:
                if getattr(strategy, "limit_order_expiry_candles", None):
                    index += 1
                    continue
                # One pending order remains active until the end of this
                # backtest segment; no second position is opened alongside it.
                break
            signal = self._resolve_signal(signal, reference_entry)
            if not self._is_valid_signal(signal, reference_entry):
                index = entry_index
                continue
            entry_price = (
                reference_entry
                if signal.entry_limit is not None
                else self._apply_entry_slippage(reference_entry, signal.direction)
            )
            exit_index, exit_price, exit_reason, partial_exit_price = self._find_exit(
                df,
                entry_index + 1 if enter_on_signal_close else entry_index,
                signal,
                entry_price,
            )
            exit_price = self._apply_exit_slippage(exit_price, signal.direction)
            if partial_exit_price is not None:
                partial_exit_price = self._apply_exit_slippage(
                    partial_exit_price, signal.direction
                )
            trades.append(
                ClosedTrade(
                    symbol=symbol,
                    direction=signal.direction,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    risk_per_unit=abs(entry_price - signal.stop_loss),
                    entry_fee_percent=self.fee_percent_per_side,
                    exit_fee_percent=self.fee_percent_per_side,
                    exit_reason=exit_reason,
                    partial_exit_price=partial_exit_price,
                    partial_exit_fraction=(
                        signal.partial_close_fraction if partial_exit_price is not None else 0.0
                    ),
                )
            )
            index = exit_index

        return trades

    def _entry_for_signal(
        self, df, first_index, signal, enter_on_signal_close=False, max_entry_index=None
    ):
        if enter_on_signal_close:
            return first_index, float(df.iloc[first_index]["close"])
        if signal.entry_limit is None:
            return first_index, float(df.iloc[first_index]["open"])
        return self._find_limit_entry(df, first_index, signal, max_entry_index)

    @staticmethod
    def _find_limit_entry(df, first_index, signal, max_entry_index=None):
        limit = signal.entry_limit
        last_index = min(
            len(df), (max_entry_index + 1) if max_entry_index is not None else len(df)
        )
        for index in range(first_index, last_index):
            candle = df.iloc[index]
            opening = float(candle["open"])
            low = float(candle["low"])
            high = float(candle["high"])
            if signal.direction == "LONG":
                if opening <= limit:
                    return index, opening
                if low <= limit <= high:
                    return index, limit
            else:
                if opening >= limit:
                    return index, opening
                if low <= limit <= high:
                    return index, limit
        return None, None

    @staticmethod
    def _resolve_signal(signal, entry_price):
        if signal.take_profit is not None:
            return signal
        risk = abs(entry_price - signal.stop_loss)
        take_profit = (
            entry_price + risk * signal.reward_to_risk
            if signal.direction == "LONG"
            else entry_price - risk * signal.reward_to_risk
        )
        return signal.__class__(
            direction=signal.direction,
            stop_loss=signal.stop_loss,
            take_profit=take_profit,
            entry_limit=signal.entry_limit,
            breakeven_trigger=signal.breakeven_trigger,
            runner_take_profit=signal.runner_take_profit,
            partial_close_fraction=signal.partial_close_fraction,
        )

    def _apply_entry_slippage(self, price, direction):
        multiplier = 1 + self.slippage_percent_per_side / 100
        return price * multiplier if direction == "LONG" else price / multiplier

    def _apply_exit_slippage(self, price, direction):
        multiplier = 1 - self.slippage_percent_per_side / 100
        return price * multiplier if direction == "LONG" else price / multiplier

    @staticmethod
    def _is_valid_signal(signal, entry_price):
        if signal.direction == "LONG":
            return signal.stop_loss < entry_price < signal.take_profit
        return signal.take_profit < entry_price < signal.stop_loss

    @staticmethod
    def _find_exit(df, entry_index, signal, entry_price):
        active_stop = signal.stop_loss
        breakeven_armed = False
        partial_exit_price = None
        for index in range(entry_index, len(df)):
            candle = df.iloc[index]
            high = float(candle["high"])
            low = float(candle["low"])

            # If both levels are reached in one candle, use the conservative
            # assumption that the stop-loss was filled first.
            if signal.direction == "LONG":
                if low <= active_stop:
                    reason = "breakeven" if breakeven_armed else "stop"
                    return index, active_stop, reason, partial_exit_price
                if partial_exit_price is not None and high >= signal.runner_take_profit:
                    return index, signal.runner_take_profit, "target", partial_exit_price
                if high >= signal.take_profit:
                    if signal.partial_close_fraction:
                        partial_exit_price = signal.take_profit
                        if high >= signal.runner_take_profit:
                            return index, signal.runner_take_profit, "target", partial_exit_price
                    else:
                        return index, signal.take_profit, "target", None
                if (
                    not breakeven_armed
                    and signal.breakeven_trigger is not None
                    and high >= signal.breakeven_trigger
                ):
                    active_stop = entry_price
                    breakeven_armed = True
            else:
                if high >= active_stop:
                    reason = "breakeven" if breakeven_armed else "stop"
                    return index, active_stop, reason, partial_exit_price
                if partial_exit_price is not None and low <= signal.runner_take_profit:
                    return index, signal.runner_take_profit, "target", partial_exit_price
                if low <= signal.take_profit:
                    if signal.partial_close_fraction:
                        partial_exit_price = signal.take_profit
                        if low <= signal.runner_take_profit:
                            return index, signal.runner_take_profit, "target", partial_exit_price
                    else:
                        return index, signal.take_profit, "target", None
                if (
                    not breakeven_armed
                    and signal.breakeven_trigger is not None
                    and low <= signal.breakeven_trigger
                ):
                    active_stop = entry_price
                    breakeven_armed = True

        return len(df) - 1, float(df.iloc[-1]["close"]), "close", partial_exit_price
