from html import escape

from src.main_orchestrator import BoardroomResult
from src.models.synthesis_schema import Action, FinalSynthesis, RiskDecision


ACTION_ICON = {
    Action.BUY: "🟢",
    Action.ACCUMULATE: "🟢",
    Action.HOLD: "🟡",
    Action.REDUCE: "🟠",
    Action.SELL: "🔴",
    Action.AVOID: "⚫",
}

RISK_ICON = {
    RiskDecision.APPROVED: "✅",
    RiskDecision.ADJUSTED: "⚖️",
    RiskDecision.VETOED: "🛑",
}


def format_final_synthesis_html(final: FinalSynthesis, persisted_record_id: str | None = None) -> str:
    action_icon = ACTION_ICON.get(final.action, "📌")
    risk_icon = RISK_ICON.get(final.risk_decision, "📌")
    lines = [
        f"<b>{action_icon} {escape(final.ticker)}: {escape(final.action.value.upper())}</b>",
        f"<b>Conviction:</b> {final.conviction_score}/100",
        f"<b>Risk Decision:</b> {risk_icon} {escape(final.risk_decision.value.upper())}",
        f"<b>Position Size:</b> {final.position_size_pct:.2f}%",
        "",
        "<b>Trade Plan</b>",
        f"Entry: {_format_price(final.entry_price)}",
        f"Take Profit: {_format_price(final.take_profit)}",
        f"Stop Loss: {_format_price(final.stop_loss)}",
        "",
        "<b>Thesis</b>",
        escape(final.thesis),
    ]
    if final.key_risks:
        lines.extend(["", "<b>Key Risks</b>"])
        lines.extend(f"- {escape(risk)}" for risk in final.key_risks)
    if final.evidence:
        lines.extend(["", "<b>Evidence</b>"])
        lines.extend(
            f"- {escape(item.source)}: {escape(item.claim)} ({item.weight:.0%})"
            for item in final.evidence
        )
    if persisted_record_id is not None:
        lines.extend(["", f"<code>{escape(persisted_record_id)}</code>"])
    return "\n".join(lines)


def format_boardroom_result_html(result: BoardroomResult) -> str:
    final_html = format_final_synthesis_html(result.final_synthesis, result.persisted_record_id)
    conflict = result.conflict_assessment
    sections = [
        final_html,
        "",
        "<b>Boardroom Signals</b>",
        f"Fundamentals: {escape(', '.join(result.fundamentals.tags) or 'none')}",
        f"Technicals: {escape(', '.join(result.technicals.tags) or 'none')}",
        f"Research: {escape(result.research.sentiment)} ({result.research.sentiment_score:.2f})",
        f"Visual Chart: {escape(result.visual_chart_analysis.sentiment)} ({result.visual_chart_analysis.confidence_score:.2f})",
    ]
    if conflict.has_conflict:
        sections.extend(["", "<b>Debate Triggered</b>"])
        sections.extend(f"- {escape(reason)}" for reason in conflict.reasons)
    return "\n".join(sections)


def _format_price(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"
