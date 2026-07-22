class BacktestReport:
    """Calculate transparent performance metrics from completed paper trades."""

    def generate(self, trades):
        trades = list(trades)
        long_trades = sum(trade.direction == "LONG" for trade in trades)
        short_trades = sum(trade.direction == "SHORT" for trade in trades)
        long_wins = sum(
            trade.direction == "LONG" and trade.return_percent > 0 for trade in trades
        )
        short_wins = sum(
            trade.direction == "SHORT" and trade.return_percent > 0 for trade in trades
        )
        breakeven_exits = sum(trade.exit_reason == "breakeven" for trade in trades)
        partial_take_profit_exits = sum(
            trade.partial_exit_price is not None for trade in trades
        )
        returns = [trade.return_percent for trade in trades]
        r_multiples = [trade.r_multiple for trade in trades]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]

        equity = 100.0
        peak = equity
        max_drawdown = 0.0

        for trade_return in returns:
            equity *= 1 + trade_return / 100
            peak = max(peak, equity)
            drawdown = (peak - equity) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (
            round(gross_profit / gross_loss, 4)
            if gross_loss
            else None
        )

        return {
            "trades": len(trades),
            "long_trades": long_trades,
            "short_trades": short_trades,
            "long_wins": long_wins,
            "short_wins": short_wins,
            "long_win_rate_percent": self._average_as_percent(long_wins, long_trades),
            "short_win_rate_percent": self._average_as_percent(short_wins, short_trades),
            "breakeven_exits": breakeven_exits,
            "partial_take_profit_exits": partial_take_profit_exits,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_percent": self._average_as_percent(len(wins), len(trades)),
            "net_return_percent": round(sum(returns), 4),
            "compounded_return_percent": round(equity - 100, 4),
            "profit_factor": profit_factor,
            "max_drawdown_percent": round(max_drawdown, 4),
            "average_r_multiple": self._average(r_multiples),
        }

    @staticmethod
    def _average(values):
        return round(sum(values) / len(values), 4) if values else None

    @staticmethod
    def _average_as_percent(value, total):
        return round(value / total * 100, 4) if total else 0.0
