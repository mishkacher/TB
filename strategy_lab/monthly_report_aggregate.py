from strategy_lab.report_store import ReportStore


class MonthlyReportAggregator:
    """Combine already-computed monthly reports without rerunning a strategy."""

    def aggregate(self, report_paths):
        reports = [ReportStore.load(path) for path in report_paths]
        if not reports:
            raise ValueError("At least one monthly report is required")

        symbols = {report.get("symbol") for report in reports}
        intervals = {report.get("interval") for report in reports}
        if len(symbols) != 1 or len(intervals) != 1:
            raise ValueError("Monthly reports must use one symbol and interval")

        reports.sort(key=lambda report: report.get("month", ""))
        trades = sum(report["report"]["trades"] for report in reports)
        wins = sum(report["report"]["wins"] for report in reports)
        losses = sum(report["report"]["losses"] for report in reports)
        long_trades = sum(report["report"].get("long_trades", 0) for report in reports)
        short_trades = sum(report["report"].get("short_trades", 0) for report in reports)
        long_wins = sum(report["report"].get("long_wins", 0) for report in reports)
        short_wins = sum(report["report"].get("short_wins", 0) for report in reports)
        breakeven_exits = sum(report["report"].get("breakeven_exits", 0) for report in reports)
        partial_take_profit_exits = sum(
            report["report"].get("partial_take_profit_exits", 0) for report in reports
        )
        net_return = sum(report["report"]["net_return_percent"] for report in reports)
        equity = 100.0
        for report in reports:
            equity *= 1 + report["report"]["compounded_return_percent"] / 100

        return {
            "symbol": symbols.pop(),
            "interval": intervals.pop(),
            "months": [report.get("month") for report in reports],
            "trades": trades,
            "long_trades": long_trades,
            "short_trades": short_trades,
            "long_wins": long_wins,
            "short_wins": short_wins,
            "long_win_rate_percent": round(long_wins / long_trades * 100, 4) if long_trades else 0.0,
            "short_win_rate_percent": round(short_wins / short_trades * 100, 4) if short_trades else 0.0,
            "breakeven_exits": breakeven_exits,
            "partial_take_profit_exits": partial_take_profit_exits,
            "wins": wins,
            "losses": losses,
            "win_rate_percent": round(wins / trades * 100, 4) if trades else 0.0,
            "net_return_percent": round(net_return, 4),
            "compounded_return_percent": round(equity - 100, 4),
        }
