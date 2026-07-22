from analysis.fvg import FairValueGapDetector
from strategy_lab.models import TradeSignal


class FvgEntryStrategy:
    """Enter immediately after a newly closed 15m three-candle FVG.

    Signal is known at the close of candle three.  Backtester enters at the
    next candle's open, places the stop behind the FVG, and derives the target
    from that actual entry price.
    """

    VERSION = "fvg-entry-0.1.0"
    ENTRY_INTERVAL = "15m"

    def __init__(
        self,
        reward_to_risk=2.0,
        detector=None,
        min_impulse_percent=2.0,
        impulse_lookback=16,
        consolidation_candles=4,
        max_consolidation_range_percent=0.75,
        interval=ENTRY_INTERVAL,
        entry_mode="market",
        volume_lookback=5,
        volume_multiplier=0.6,
        require_context=True,
        enter_on_signal_close=False,
    ):
        if reward_to_risk <= 0:
            raise ValueError("reward_to_risk must be positive")
        if min_impulse_percent <= 0 or impulse_lookback < 1 or consolidation_candles < 1:
            raise ValueError("impulse and consolidation parameters must be positive")
        if volume_lookback < 1 or volume_multiplier <= 0:
            raise ValueError("volume parameters must be positive")
        if interval != self.ENTRY_INTERVAL:
            raise ValueError("FVG entry strategy supports 15m candles only")
        if entry_mode not in {"market", "limit"}:
            raise ValueError("entry_mode must be market or limit")
        self.reward_to_risk = reward_to_risk
        self.detector = detector or FairValueGapDetector()
        self.min_impulse_percent = min_impulse_percent
        self.impulse_lookback = impulse_lookback
        self.consolidation_candles = consolidation_candles
        self.max_consolidation_range_percent = max_consolidation_range_percent
        self.interval = interval
        self.entry_mode = entry_mode
        self.volume_lookback = volume_lookback
        self.volume_multiplier = volume_multiplier
        self.require_context = require_context
        self.enter_on_signal_close = enter_on_signal_close
        self.dataframe = None

    def prepare(self, dataframe):
        self.dataframe = dataframe.reset_index(drop=True)

    def generate_at(self, index):
        if self.dataframe is None:
            raise RuntimeError("prepare must be called before generate_at")
        if index < self.minimum_history - 1:
            return None
        return self.generate(self.dataframe.iloc[: index + 1])

    @property
    def minimum_history(self):
        return max(
            self.impulse_lookback + self.consolidation_candles + 3,
            self.volume_lookback + 2,
        )

    def generate(self, history):
        if len(history) < self.minimum_history:
            return None
        gaps = self.detector.find(history.tail(3), lookback=3)
        if not gaps:
            return None
        gap = gaps[-1]
        direction = gap["direction"]
        middle_candle_position = len(history) - 2
        if not self._has_required_volume(history, middle_candle_position):
            return None
        if self.require_context and not self._has_required_context(history, direction):
            return None
        if direction == "BULLISH":
            return TradeSignal(
                "LONG",
                stop_loss=gap["lower"],
                reward_to_risk=self.reward_to_risk,
                entry_limit=gap["upper"] if self.entry_mode == "limit" else None,
            )
        return TradeSignal(
            "SHORT",
            stop_loss=gap["upper"],
            reward_to_risk=self.reward_to_risk,
            entry_limit=gap["lower"] if self.entry_mode == "limit" else None,
        )

    def _has_required_context(self, history, direction):
        fvg_start = len(history) - 3
        consolidation_start = fvg_start - self.consolidation_candles
        consolidation = history.iloc[consolidation_start:fvg_start]
        consolidation_range = (
            (float(consolidation["high"].max()) - float(consolidation["low"].min()))
            / float(consolidation.iloc[-1]["close"])
            * 100
        )
        if consolidation_range > self.max_consolidation_range_percent:
            return False

        middle_candle_position = len(history) - 2
        if not self._has_required_volume(history, middle_candle_position):
            return False

        impulse = history.iloc[
            max(0, consolidation_start - self.impulse_lookback):consolidation_start
        ]
        low_position = impulse["low"].idxmin()
        high_position = impulse["high"].idxmax()
        low = float(impulse.loc[low_position, "low"])
        high = float(impulse.loc[high_position, "high"])

        if direction == "BULLISH":
            return (
                low_position < high_position
                and (high - low) / low * 100 >= self.min_impulse_percent
            )
        return (
            high_position < low_position
            and (high - low) / high * 100 >= self.min_impulse_percent
        )

    def _has_required_volume(self, history, middle_candle_position):
        prior_volumes = history.iloc[
            middle_candle_position - self.volume_lookback:middle_candle_position
        ]["volume"]
        if len(prior_volumes) < self.volume_lookback:
            return False
        if float(history.iloc[middle_candle_position]["volume"]) < (
            float(prior_volumes.mean()) * self.volume_multiplier
        ):
            return False
        return True
