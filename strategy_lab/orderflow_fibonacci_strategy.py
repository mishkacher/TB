"""15-minute order-flow impulse retracement strategy."""

import pandas as pd

from strategy_lab.models import TradeSignal


class OrderflowFibonacciStrategy:
    """Trade a confirmed 15m swing impulse from the 0.5 Fibonacci retracement.

    A high/low is confirmed only after ``pivot_right`` later candles.  That
    prevents the strategy from using an unclosed swing as historical knowledge.
    """

    VERSION = "orderflow-fibonacci-0.1.0"
    ENTRY_INTERVAL = "15m"
    SUPPORTED_INTERVALS = {"15m", "1h"}
    limit_order_expiry_candles = 48

    def __init__(
        self,
        interval=ENTRY_INTERVAL,
        pivot_left=4,
        pivot_right=4,
        min_impulse_percent=1.0,
        take_profit_extension=0.23,
        entry_retracement=0.5,
        direction="both",
        monthly_trend_filter=False,
        breakeven_level=None,
        runner_take_profit_extension=0.5,
        partial_close_fraction=0.8,
    ):
        if interval not in self.SUPPORTED_INTERVALS:
            raise ValueError("order-flow Fibonacci strategy supports 15m or 1h candles only")
        if (
            pivot_left < 1 or pivot_right < 1 or min_impulse_percent <= 0
            or take_profit_extension <= 0 or not 0 < entry_retracement < 1
            or runner_take_profit_extension <= take_profit_extension
            or not 0 <= partial_close_fraction < 1
        ):
            raise ValueError("pivot sizes and minimum impulse must be positive")
        if direction not in {"both", "long", "short"}:
            raise ValueError("direction must be both, long or short")
        self.interval = interval
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.min_impulse_percent = min_impulse_percent
        self.take_profit_extension = take_profit_extension
        self.entry_retracement = entry_retracement
        self.direction = direction
        self.monthly_trend_filter = monthly_trend_filter
        self.breakeven_level = breakeven_level
        self.runner_take_profit_extension = runner_take_profit_extension
        self.partial_close_fraction = partial_close_fraction
        self.monthly_directions = {}
        self.dataframe = None

    @property
    def minimum_history(self):
        return self.pivot_left + self.pivot_right + 1

    def prepare(self, dataframe):
        self.dataframe = dataframe.reset_index(drop=True)
        if self.monthly_trend_filter:
            self.monthly_directions = self._calculate_monthly_directions()

    def generate_at(self, index):
        if self.dataframe is None:
            raise RuntimeError("prepare must be called before generate_at")
        if index < self.minimum_history - 1:
            return None
        pivot_index = index - self.pivot_right
        if self.direction != "short" and self._is_pivot_high(pivot_index):
            prior_low = self._previous_pivot(pivot_index, "low")
            if prior_low is not None:
                signal = self._long_signal(prior_low, pivot_index)
                if signal is not None and self._allows_direction(index, "long"):
                    return signal
        if self.direction != "long" and self._is_pivot_low(pivot_index):
            prior_high = self._previous_pivot(pivot_index, "high")
            if prior_high is not None:
                signal = self._short_signal(prior_high, pivot_index)
                if signal is not None and self._allows_direction(index, "short"):
                    return signal
        return None

    def _allows_direction(self, index, direction):
        if not self.monthly_trend_filter:
            return True
        month = str(pd.Timestamp(self.dataframe.iloc[index]["time"]).to_period("M"))
        return self.monthly_directions.get(month) == direction

    def _calculate_monthly_directions(self):
        daily = (
            self.dataframe.set_index("time")
            .resample("1D")
            .agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
            .dropna()
            .reset_index()
        )
        directions = {}
        for month in sorted(self.dataframe["time"].dt.to_period("M").unique()):
            history = daily[daily["time"] < month.start_time]
            if len(history) < 50:
                continue
            close = history["close"]
            ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
            ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
            votes = [close.iloc[-1] > ema20, ema20 > ema50]
            structure = self._daily_structure_vote(history.tail(50))
            if structure is None:
                structure = close.iloc[-1] > close.iloc[-21]
            votes.append(structure)
            directions[str(month)] = "long" if sum(votes) >= 2 else "short"
        return directions

    @staticmethod
    def _daily_structure_vote(history):
        pivot_highs = []
        pivot_lows = []
        for index in range(2, len(history) - 2):
            window = history.iloc[index - 2:index + 3]
            current = history.iloc[index]
            if current["high"] == window["high"].max():
                pivot_highs.append(float(current["high"]))
            if current["low"] == window["low"].min():
                pivot_lows.append(float(current["low"]))
        if len(pivot_highs) < 2 or len(pivot_lows) < 2:
            return None
        if pivot_highs[-1] > pivot_highs[-2] and pivot_lows[-1] > pivot_lows[-2]:
            return True
        if pivot_highs[-1] < pivot_highs[-2] and pivot_lows[-1] < pivot_lows[-2]:
            return False
        return None

    def _previous_pivot(self, before_index, kind):
        for index in range(before_index - 1, self.pivot_left - 1, -1):
            if kind == "low" and self._is_pivot_low(index):
                return index
            if kind == "high" and self._is_pivot_high(index):
                return index
        return None

    def _is_pivot_high(self, index):
        window = self.dataframe.iloc[
            index - self.pivot_left:index + self.pivot_right + 1
        ]
        return len(window) == self.pivot_left + self.pivot_right + 1 and (
            float(self.dataframe.iloc[index]["high"]) == float(window["high"].max())
        )

    def _is_pivot_low(self, index):
        window = self.dataframe.iloc[
            index - self.pivot_left:index + self.pivot_right + 1
        ]
        return len(window) == self.pivot_left + self.pivot_right + 1 and (
            float(self.dataframe.iloc[index]["low"]) == float(window["low"].min())
        )

    def _long_signal(self, low_index, high_index):
        low = float(self.dataframe.iloc[low_index]["low"])
        high = float(self.dataframe.iloc[high_index]["high"])
        if (high - low) / low * 100 < self.min_impulse_percent:
            return None
        impulse = high - low
        return TradeSignal(
            "LONG",
            stop_loss=low,
            take_profit=high + impulse * self.take_profit_extension,
            entry_limit=high - impulse * self.entry_retracement,
            breakeven_trigger=(
                high - impulse * self.breakeven_level
                if self.breakeven_level is not None else None
            ),
            runner_take_profit=high + impulse * self.runner_take_profit_extension,
            partial_close_fraction=self.partial_close_fraction,
        )

    def _short_signal(self, high_index, low_index):
        high = float(self.dataframe.iloc[high_index]["high"])
        low = float(self.dataframe.iloc[low_index]["low"])
        if (high - low) / high * 100 < self.min_impulse_percent:
            return None
        impulse = high - low
        return TradeSignal(
            "SHORT",
            stop_loss=high,
            take_profit=low - impulse * self.take_profit_extension,
            entry_limit=low + impulse * self.entry_retracement,
            breakeven_trigger=(
                low + impulse * self.breakeven_level
                if self.breakeven_level is not None else None
            ),
            runner_take_profit=low - impulse * self.runner_take_profit_extension,
            partial_close_fraction=self.partial_close_fraction,
        )
