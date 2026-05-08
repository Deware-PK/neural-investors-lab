import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from src.models.evaluation_schema import BacktestOutcome, PerformanceReport


class PerformanceLogger:
    def build_report(self, outcomes: list[BacktestOutcome]) -> PerformanceReport:
        total = len(outcomes)
        outcome_counts = Counter(outcome.outcome for outcome in outcomes)
        wins = outcome_counts.get("take_profit_hit", 0)
        win_rate = round((wins / total) * 100, 2) if total else 0
        return PerformanceReport(
            generated_at=datetime.now(UTC),
            total_trades=total,
            win_rate_pct=win_rate,
            average_t7_return_pct=self._average([outcome.t7_return_pct for outcome in outcomes]),
            average_t30_return_pct=self._average([outcome.t30_return_pct for outcome in outcomes]),
            average_max_drawdown_pct=self._average([outcome.max_drawdown_pct for outcome in outcomes]),
            outcomes=dict(outcome_counts),
            pattern_notes=self._pattern_notes(outcomes),
        )

    def write_json_report(self, report: PerformanceReport, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
        return output_path

    def write_markdown_report(self, report: PerformanceReport, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_markdown(report), encoding="utf-8")
        return output_path

    @staticmethod
    def to_markdown(report: PerformanceReport) -> str:
        lines = [
            "# Neural Investors Lab Performance Report",
            "",
            f"Generated: {report.generated_at.isoformat()}",
            f"Total Trades: {report.total_trades}",
            f"Win Rate: {report.win_rate_pct:.2f}%",
            f"Average T+7 Return: {_format_optional(report.average_t7_return_pct)}",
            f"Average T+30 Return: {_format_optional(report.average_t30_return_pct)}",
            f"Average Max Drawdown: {_format_optional(report.average_max_drawdown_pct)}",
            "",
            "## Outcomes",
        ]
        if report.outcomes:
            lines.extend(f"- {name}: {count}" for name, count in sorted(report.outcomes.items()))
        else:
            lines.append("- No outcomes available")
        lines.extend(["", "## Pattern Notes"])
        if report.pattern_notes:
            lines.extend(f"- {note}" for note in report.pattern_notes)
        else:
            lines.append("- No statistically meaningful pattern detected yet")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _average(values: list[float | None]) -> float | None:
        present = [value for value in values if value is not None]
        if not present:
            return None
        return round(sum(present) / len(present), 2)

    @staticmethod
    def _pattern_notes(outcomes: list[BacktestOutcome]) -> list[str]:
        notes: list[str] = []
        if not outcomes:
            return notes
        by_ticker: dict[str, list[BacktestOutcome]] = defaultdict(list)
        for outcome in outcomes:
            by_ticker[outcome.ticker].append(outcome)
        for ticker, ticker_outcomes in by_ticker.items():
            if len(ticker_outcomes) < 3:
                continue
            losses = sum(1 for outcome in ticker_outcomes if outcome.outcome == "stop_loss_hit")
            if losses / len(ticker_outcomes) >= 0.6:
                notes.append(f"High stop-loss frequency for {ticker}")
        if len(outcomes) >= 5:
            expired = sum(1 for outcome in outcomes if outcome.outcome == "expired")
            if expired / len(outcomes) >= 0.5:
                notes.append("Many recommendations expired without hitting target or stop")
            insufficient = sum(1 for outcome in outcomes if outcome.outcome == "insufficient_data")
            if insufficient:
                notes.append("Some recommendations could not be evaluated due to insufficient forward data")
        return notes


def _format_optional(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"
