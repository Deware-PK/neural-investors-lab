import logging

from src.agents.json_utils import parse_json_model
from src.agents.researcher import ResearcherAgent
from src.core.config import Settings, get_settings
from src.core.i18n import localize_prompt
from src.core.llm_client import ChatMessage, OpenRouterClient, get_openrouter_client
from src.models.agent_schema import ConflictAssessment, StrategyDraft
from src.models.fundamental_schema import FundamentalAnalysis
from src.models.macro_schema import MacroContext, OptionsFlow
from src.models.research_schema import ResearchFinding
from src.models.synthesis_schema import Action
from src.models.technical_schema import TechnicalAnalysis
from src.models.vision_schema import VisualChartAnalysis
from src.models.vi_schema import DecisionState, MandateContext


logger = logging.getLogger(__name__)


class ChiefStrategistAgent:
    def __init__(
        self,
        llm_client: OpenRouterClient | None = None,
        settings: Settings | None = None,
        researcher: ResearcherAgent | None = None,
        mandate: MandateContext | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.researcher = researcher
        self.mandate = mandate

    def identify_contradictions(
        self,
        fundamentals: FundamentalAnalysis,
        technicals: TechnicalAnalysis,
        research: ResearchFinding,
    ) -> ConflictAssessment:
        reasons: list[str] = []
        if fundamentals.piotroski_f_score is not None and fundamentals.piotroski_f_score >= 7 and research.sentiment == "bearish":
            reasons.append("Strong fundamentals conflict with bearish news sentiment")
        if fundamentals.piotroski_f_score is not None and fundamentals.piotroski_f_score <= 3 and research.sentiment == "bullish":
            reasons.append("Weak fundamentals conflict with bullish news sentiment")
        if technicals.moving_average.state == "bullish" and research.sentiment == "bearish":
            reasons.append("Bullish technical trend conflicts with bearish news sentiment")
        if technicals.moving_average.state == "bearish" and research.sentiment == "bullish":
            reasons.append("Bearish technical trend conflicts with bullish news sentiment")
        if technicals.momentum.divergence != "none":
            reasons.append(f"Technical divergence requires narrative validation: {technicals.momentum.divergence}")
        query = None
        if reasons:
            query = f"Investigate conflicts for {fundamentals.ticker}: " + "; ".join(reasons)
        return ConflictAssessment(
            ticker=fundamentals.ticker,
            has_conflict=bool(reasons),
            reasons=reasons,
            deep_dive_query=query,
        )

    def draft_strategy(
        self,
        fundamentals: FundamentalAnalysis,
        technicals: TechnicalAnalysis,
        research: ResearchFinding,
        visual_chart_analysis: VisualChartAnalysis | None = None,
        macro_context: MacroContext | None = None,
        options_flow: OptionsFlow | None = None,
    ) -> StrategyDraft:
        conflict = self.identify_contradictions(fundamentals, technicals, research)
        final_research = research
        if conflict.has_conflict and self.researcher is not None and conflict.deep_dive_query is not None:
            logger.info("CEO triggered debate deep-dive for %s", fundamentals.ticker)
            final_research = self.researcher.investigate_conflict(fundamentals.ticker, conflict.deep_dive_query)
        return self._generate_strategy(
            fundamentals, technicals, final_research, conflict,
            visual_chart_analysis, macro_context, options_flow
        )

    def draft_strategy_with_assessment(
        self,
        fundamentals: FundamentalAnalysis,
        technicals: TechnicalAnalysis,
        research: ResearchFinding,
        conflict: ConflictAssessment,
        visual_chart_analysis: VisualChartAnalysis | None = None,
        macro_context: MacroContext | None = None,
        options_flow: OptionsFlow | None = None,
    ) -> StrategyDraft:
        return self._generate_strategy(
            fundamentals, technicals, research, conflict,
            visual_chart_analysis, macro_context, options_flow
        )

    def _generate_strategy(
        self,
        fundamentals: FundamentalAnalysis,
        technicals: TechnicalAnalysis,
        research: ResearchFinding,
        conflict: ConflictAssessment,
        visual_chart_analysis: VisualChartAnalysis | None = None,
        macro_context: MacroContext | None = None,
        options_flow: OptionsFlow | None = None,
    ) -> StrategyDraft:
        client = self.llm_client or get_openrouter_client(self.settings)
        lang = self.settings.output_language
        is_vi = self.mandate is not None and self.mandate.investment_style == "deep_value_vi"
        vi_prefix = ""
        if is_vi:
            vi_prefix = (
                f"ACTIVE MANDATE: {self.mandate.model_dump(mode='json')}\n"
                "You are the Chief Strategist (CEO) in a multi-agent investment system. "
                "You synthesize Auditor, Chartist, and Researcher outputs into a mandate-aware investment decision. "
                "You are not a short-term trader unless the mandate says so.\n"
                "Decision philosophy in deep_value_vi mode:\n"
                "1. Fundamental survivability and valuation dominate short-term price action.\n"
                "2. Technicals determine entry quality, not long-term thesis validity.\n"
                "3. A downtrend does not invalidate a value thesis by itself.\n"
                "4. Use staged decisions rather than categorical avoidance when the thesis is intact but timing is weak.\n"
                "5. Avoid only when hard blocks exist or when long-term expected value is unattractive.\n"
                "You must output one of these decision states: avoid, watch, probe, accumulate, high_conviction_accumulate.\n"
                "Required reasoning steps:\n"
                "1. State whether the long-term thesis is intact.\n"
                "2. State whether valuation offers a margin of safety.\n"
                "3. State whether technicals weaken timing only, or signal deeper thesis risk.\n"
                "4. State what would upgrade the decision by one level.\n"
                "5. State what would downgrade the decision by one level.\n"
                "Rules: Do not let momentum, RS rank, options flow, or supertrend dominate a VI mandate. "
                "If fundamentals are mixed but survivability is strong and valuation is improving, prefer watch or probe over avoid. "
                "If long-term catalysts exist but near-term catalysts are absent, say so explicitly. "
                "If there is disagreement between agents, resolve it in favor of the active mandate rather than defaulting to the most conservative voice.\n"
            )
        messages = [
            ChatMessage(
                role="system",
                content=localize_prompt(
                    vi_prefix + (
                        "You are the Chief Strategist of an elite quantitative hedge fund. Your primary goal is capital preservation and high-probability swing trades (T+7 to T+30). "
                        "Analyze the intersection of fundamentals, technical indicators, and news sentiment. "
                        "RULES: "
                        "1. Return ONLY strict JSON matching the StrategyDraft schema. "
                        "2. Do not invent numeric metrics; rely entirely on the provided Python calculations. "
                        "3. If 'ConflictAssessment' flags a contradiction (e.g., Bearish news vs Bullish technicals), you MUST address it in your 'thesis' and reflect the uncertainty by lowering the 'conviction_score' or changing the action to 'hnew'. "
                        "4. For BUY/ACCUMULATE actions, strictly set 'entry_price', 'take_profit' (targeting a realistic 1.5x - 2.0x ATR), and 'stop_loss' using the provided technical support/resistance levels. "
                        "5. MacroContext is the GLOBAL backdrop — a bear market regime or extreme VIX must lower conviction regardless of individual stock signals. "
                        "6. Your 'thesis' must be a ruthless, logical deduction explaining EXACTLY why the reward-to-risk ratio justifies the trade in the current market context."
                        "7. Always populate 'market_regime' and 'vix_level' in your JSON output using values from MacroContext — these fields are required for backtest analytics."
                    ),
                    lang,
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Fundamentals: {fundamentals.model_dump(mode='json')}\n"
                    f"Technicals: {technicals.model_dump(mode='json')}\n"
                    f"Research: {research.model_dump(mode='json')}\n"
                    f"VisualChartAnalysis: {visual_chart_analysis.model_dump(mode='json') if visual_chart_analysis else None}\n"
                    f"ConflictAssessment: {conflict.model_dump(mode='json')}\n"
                    f"MacroContext: {macro_context.model_dump(mode='json') if macro_context else None}\n"
                    f"OptionsFlow: {options_flow.model_dump(mode='json') if options_flow else None}\n"
                    "Return JSON fields: ticker, action, conviction_score, entry_price, take_profit, stop_loss, "
                    "proposed_position_size_pct, market_regime, vix_level, thesis, key_risks, evidence, conflict_assessment"
                    + (", decision_state, upgrade_trigger, downgrade_trigger" if is_vi else "") +
                    ". "
                    "action MUST be one of: buy, accumulate, hnew, reduce, sell, avoid. "
                    "market_regime MUST be one of: bull, bear, sideways."
                ),
            ),
        ]
        response = client.generate_completion(
            model=self.settings.ceo_model,
            messages=messages,
            use_reasoning=self.settings.ceo_model_reasoning,
            temperature=0.1,
        )
        draft = parse_json_model(response.content, StrategyDraft)
        if draft.ticker.upper() != fundamentals.ticker.upper():
            draft = draft.model_copy(update={"ticker": fundamentals.ticker.upper()})
        if draft.conflict_assessment is None:
            draft = draft.model_copy(update={"conflict_assessment": conflict})
        if draft.action in {Action.BUY, Action.ACCUMULATE} and draft.entry_price is None:
            draft = draft.model_copy(update={"action": Action.HOLD, "proposed_position_size_pct": 0})
        return draft
