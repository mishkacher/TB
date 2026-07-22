from dataclasses import dataclass


@dataclass(frozen=True)
class ClosedTrade:
    """A completed paper trade used only for historical evaluation."""

    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    risk_per_unit: float
    entry_fee_percent: float = 0.0
    exit_fee_percent: float = 0.0
    exit_reason: str = "close"
    partial_exit_price: float | None = None
    partial_exit_fraction: float = 0.0

    def __post_init__(self):
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if self.entry_price <= 0 or self.risk_per_unit <= 0:
            raise ValueError("entry_price and risk_per_unit must be positive")
        if self.entry_fee_percent < 0 or self.exit_fee_percent < 0:
            raise ValueError("fees cannot be negative")
        if self.exit_reason not in {"target", "stop", "breakeven", "close"}:
            raise ValueError("invalid exit reason")
        if not 0 <= self.partial_exit_fraction < 1:
            raise ValueError("partial_exit_fraction must be from 0 up to 1")
        if self.partial_exit_fraction and self.partial_exit_price is None:
            raise ValueError("partial exit price is required when a fraction is closed")

    @property
    def pnl_per_unit(self):
        def directional_pnl(exit_price):
            return (
                exit_price - self.entry_price
                if self.direction == "LONG"
                else self.entry_price - exit_price
            )
        remainder = 1 - self.partial_exit_fraction
        gross = directional_pnl(self.exit_price) * remainder
        if self.partial_exit_price is not None:
            gross += directional_pnl(self.partial_exit_price) * self.partial_exit_fraction
        fees = (
            self.entry_price * self.entry_fee_percent / 100
            + self.exit_price * remainder * self.exit_fee_percent / 100
        )
        if self.partial_exit_price is not None:
            fees += self.partial_exit_price * self.partial_exit_fraction * self.exit_fee_percent / 100
        return gross - fees

    @property
    def return_percent(self):
        return self.pnl_per_unit / self.entry_price * 100

    @property
    def r_multiple(self):
        return self.pnl_per_unit / self.risk_per_unit


@dataclass(frozen=True)
class TradeSignal:
    """A strategy request to open a paper trade on the next candle."""

    direction: str
    stop_loss: float
    take_profit: float | None = None
    reward_to_risk: float | None = None
    entry_limit: float | None = None
    breakeven_trigger: float | None = None
    runner_take_profit: float | None = None
    partial_close_fraction: float = 0.0

    def __post_init__(self):
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if self.take_profit is None and self.reward_to_risk is None:
            raise ValueError("take_profit or reward_to_risk is required")
        if self.reward_to_risk is not None and self.reward_to_risk <= 0:
            raise ValueError("reward_to_risk must be positive")
        if self.entry_limit is not None and self.entry_limit <= 0:
            raise ValueError("entry_limit must be positive")
        if self.breakeven_trigger is not None and self.breakeven_trigger <= 0:
            raise ValueError("breakeven_trigger must be positive")
        if self.runner_take_profit is not None and self.runner_take_profit <= 0:
            raise ValueError("runner_take_profit must be positive")
        if not 0 <= self.partial_close_fraction < 1:
            raise ValueError("partial_close_fraction must be from 0 up to 1")
        if self.partial_close_fraction and self.runner_take_profit is None:
            raise ValueError("runner_take_profit is required for a partial close")
