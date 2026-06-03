from html import escape

from src.core.i18n import get_text
from src.main_orchestrator import BoardroomResult
from src.models.synthesis_schema import Action, FinalSynthesis, RiskDecision


def _sanitize_text(text: str) -> str:
    """Clean text for output while preserving Unicode (e.g., Thai)."""
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "--", "\u2026": "...",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text


ACTION_ICON = {
    Action.BUY: "[BUY]",
    Action.ACCUMULATE: "[ACCUMULATE]",
    Action.HOLD: "[HOLD]",
    Action.REDUCE: "[REDUCE]",
    Action.SELL: "[SELL]",
    Action.AVOID: "[AVOID]",
}

RISK_ICON = {
    RiskDecision.APPROVED: "[APPROVED]",
    RiskDecision.ADJUSTED: "[ADJUSTED]",
    RiskDecision.VETOED: "[VETOED]",
}


def format_final_synthesis_html(final: FinalSynthesis, persisted_record_id: str | None = None, lang: str = "en") -> str:
    action_icon = ACTION_ICON.get(final.action, "[?]")
    risk_icon = RISK_ICON.get(final.risk_decision, "[?]")
    lines = [
        f"<b>{action_icon} {escape(final.ticker)}: {escape(final.action.value.upper())}</b>",
        f"<b>{get_text(lang, 'conviction')}:</b> {final.conviction_score}/100",
        f"<b>{get_text(lang, 'risk_decision')}:</b> {risk_icon} {escape(final.risk_decision.value.upper())}",
        f"<b>{get_text(lang, 'position_size')}:</b> {final.position_size_pct:.2f}%",
        "",
        f"<b>{get_text(lang, 'trade_plan')}</b>",
        f"{get_text(lang, 'entry')}: {_format_price(final.entry_price, lang)}",
        f"{get_text(lang, 'take_profit')}: {_format_price(final.take_profit, lang)}",
        f"{get_text(lang, 'stop_loss')}: {_format_price(final.stop_loss, lang)}",
        "",
        f"<b>{get_text(lang, 'thesis')}</b>",
        escape(final.thesis),
    ]
    if final.key_risks:
        lines.extend(["", f"<b>{get_text(lang, 'key_risks')}</b>"])
        lines.extend(f"- {escape(risk)}" for risk in final.key_risks)
    if final.evidence:
        lines.extend(["", f"<b>{get_text(lang, 'evidence')}</b>"])
        lines.extend(
            f"- {escape(item.source)}: {escape(item.claim)} ({item.weight:.0%})"
            for item in final.evidence
        )
    if persisted_record_id is not None:
        lines.extend(["", f"<code>{escape(persisted_record_id)}</code>"])
    return _sanitize_text("\n".join(lines))


def format_boardroom_result_html(result: BoardroomResult, lang: str = "en") -> str:
    final_html = format_final_synthesis_html(result.final_synthesis, result.persisted_record_id, lang=lang)
    conflict = result.conflict_assessment
    sections = [
        final_html,
        "",
        f"<b>{get_text(lang, 'boardroom_signals')}</b>",
        f"{get_text(lang, 'fundamentals')}: {escape(', '.join(result.fundamentals.tags) or 'none')}",
        f"{get_text(lang, 'technicals')}: {escape(', '.join(result.technicals.tags) or 'none')}",
        f"{get_text(lang, 'research')}: {escape(result.research.sentiment)} ({result.research.sentiment_score:.2f})",
        f"{get_text(lang, 'visual_chart')}: {escape(result.visual_chart_analysis.sentiment)} ({result.visual_chart_analysis.confidence_score:.2f})",
    ]
    if conflict.has_conflict:
        sections.extend(["", f"<b>{get_text(lang, 'debate_triggered')}</b>"])
        sections.extend(f"- {escape(reason)}" for reason in conflict.reasons)
    return _sanitize_text("\n".join(sections))


def _format_price(value: float | None, lang: str = "en") -> str:
    if value is None:
        return get_text(lang, "na")
    return f"{value:.2f}"
