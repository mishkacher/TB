import json
from pathlib import Path


class ReportStore:
    """Persist backtest reports for comparison between strategy versions."""

    def save(self, report, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def load_validation(path):
        """Load only the safety verdict; absent or invalid reports reject safely."""
        try:
            return ReportStore.load(path)["validation"]
        except FileNotFoundError:
            return {"approved": False, "reasons": ["strategy_report_missing"]}
        except (json.JSONDecodeError, KeyError):
            return {"approved": False, "reasons": ["strategy_report_invalid"]}

    @staticmethod
    def load(path):
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))
