from html import escape

from src.core.i18n import get_text
from src.main_orchestrator import BoardroomResult
from src.models.synthesis_schema import Action, FinalSynthesis, RiskDecision
from src.models.vi_schema import DecisionState


def _sanitize_text(text: str) -> str:
    """Clean text for output while preserving Unicode (e.g., Thai)."""
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "--", "\u2026": "...",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text


# ── Emoji maps ──────────────────────────────────────────────────────

ACTION_ICON = {
    Action.BUY: "🟢",
    Action.ACCUMULATE: "🟡",
    Action.HOLD: "⚪",
    Action.REDUCE: "🟠",
    Action.SELL: "🔴",
    Action.AVOID: "⛔",
}

RISK_ICON = {
    RiskDecision.APPROVED: "✅",
    RiskDecision.ADJUSTED: "⚠️",
    RiskDecision.VETOED: "❌",
}

DECISION_ICON = {
    DecisionState.AVOID: "⛔",
    DecisionState.WATCH: "👀",
    DecisionState.PROBE: "🔍",
    DecisionState.ACCUMULATE: "📥",
    DecisionState.HIGH_CONVICTION_ACCUMULATE: "🚀",
}

_ACTION_EMOJI_MAP = {
    Action.BUY: "🚀",
    Action.ACCUMULATE: "📥",
    Action.HOLD: "⏸️",
    Action.REDUCE: "📤",
    Action.SELL: "🔻",
    Action.AVOID: "🚫",
}

_DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def _format_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs, preserving double-newline breaks."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return paragraphs


def format_final_synthesis_html(final: FinalSynthesis, persisted_record_id: str | None = None, lang: str = "en") -> str:
    action_icon = ACTION_ICON.get(final.action, "❓")
    action_emoji = _ACTION_EMOJI_MAP.get(final.action, "")
    risk_icon = RISK_ICON.get(final.risk_decision, "❓")

    lines: list[str] = []

    # Header
    lines.append(f"{action_icon} <b>{escape(final.ticker)}</b>  {action_emoji} <b>{escape(final.action.value.upper())}</b>")
    if final.decision_state is not None:
        d_icon = DECISION_ICON.get(final.decision_state, "❓")
        lines.append(f"   {d_icon} <b>VI:</b> {final.decision_state.value.upper()}")
    lines.append(_DIVIDER)

    # Key metrics
    lines.append(f"📊 <b>{get_text(lang, 'conviction')}:</b> {final.conviction_score}/100")
    lines.append(f"🛡️ <b>{get_text(lang, 'risk_decision')}:</b> {risk_icon} {escape(final.risk_decision.value.upper())}")
    lines.append(f"💰 <b>{get_text(lang, 'position_size')}:</b> {final.position_size_pct:.2f}%")
    lines.append("")

    # Trade Plan
    lines.append(f"📋 <b>{get_text(lang, 'trade_plan')}</b>")
    lines.append(f"  ▪️ {get_text(lang, 'entry')}: <code>{_format_price(final.entry_price, lang)}</code>")
    lines.append(f"  ▪️ {get_text(lang, 'take_profit')}: <code>{_format_price(final.take_profit, lang)}</code>")
    lines.append(f"  ▪️ {get_text(lang, 'stop_loss')}: <code>{_format_price(final.stop_loss, lang)}</code>")
    lines.append("")

    # Thesis with paragraph breaks
    lines.append(f"📝 <b>{get_text(lang, 'thesis')}</b>")
    for paragraph in _format_paragraphs(final.thesis):
        lines.append(escape(paragraph))
        lines.append("")

    # Key Risks
    if final.key_risks:
        lines.append(f"⚠️ <b>{get_text(lang, 'key_risks')}</b>")
        for risk in final.key_risks:
            lines.append(f"  • {escape(risk)}")
        lines.append("")

    if final.upgrade_trigger:
        lines.append(f"🔼 <b>Upgrade:</b> {escape(final.upgrade_trigger)}")
    if final.downgrade_trigger:
        lines.append(f"🔽 <b>Downgrade:</b> {escape(final.downgrade_trigger)}")
    if final.stop_loss_policy:
        lines.append(f"🛑 <b>Stop Policy:</b> {escape(final.stop_loss_policy)}")
    if final.add_on_policy:
        lines.append(f"➕ <b>Add-On:</b> {escape(final.add_on_policy)}")
    if final.upgrade_trigger or final.downgrade_trigger or final.stop_loss_policy or final.add_on_policy:
        lines.append("")

    # Evidence
    if final.evidence:
        lines.append(f"📌 <b>{get_text(lang, 'evidence')}</b>")
        for item in final.evidence:
            lines.append(f"  • <i>{escape(item.source)}</i>: {escape(item.claim)} ({item.weight:.0%})")
        lines.append("")

    if persisted_record_id is not None:
        lines.append(f"<code>{escape(persisted_record_id)}</code>")

    return _sanitize_text("\n".join(lines))


def format_boardroom_result_html(result: BoardroomResult, lang: str = "en") -> str:
    final_html = format_final_synthesis_html(result.final_synthesis, result.persisted_record_id, lang=lang)
    conflict = result.conflict_assessment

    lines: list[str] = []
    lines.append(final_html)
    lines.append(_DIVIDER)
    lines.append(f"📡 <b>{get_text(lang, 'boardroom_signals')}</b>")

    # Compact signal grid
    fund_tags = ", ".join(result.fundamentals.tags) or "—"
    tech_tags = ", ".join(result.technicals.tags) or "—"
    lines.append(f"  📈 {get_text(lang, 'fundamentals')}: <code>{escape(fund_tags)}</code>")
    lines.append(f"  📉 {get_text(lang, 'technicals')}: <code>{escape(tech_tags)}</code>")
    lines.append(f"  📰 {get_text(lang, 'research')}: {escape(result.research.sentiment)} ({result.research.sentiment_score:.2f})")
    lines.append(f"  👁️ {get_text(lang, 'visual_chart')}: {escape(result.visual_chart_analysis.sentiment)} ({result.visual_chart_analysis.confidence_score:.2f})")

    if conflict.has_conflict:
        lines.append("")
        lines.append(f"🔥 <b>{get_text(lang, 'debate_triggered')}</b>")
        for reason in conflict.reasons:
            lines.append(f"  • {escape(reason)}")

    return _sanitize_text("\n".join(lines))


def _format_price(value: float | None, lang: str = "en") -> str:
    if value is None:
        return get_text(lang, "na")
    return f"{value:.2f}"
