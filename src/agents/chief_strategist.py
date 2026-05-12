import logging

from src.agents.json_utils import extract_json_object, normalize_strategy_draft
from src.agents.researcher import ResearcherAgent
from src.core.config import Settings, get_settings
from src.core.llm_client import ChatMessage, OpenRouterClient, get_openrouter_client
from src.models.agent_schema import ConflictAssessment, StrategyDraft
from src.models.fundamental_schema import FundamentalAnalysis
from src.models.research_schema import ResearchFinding
from src.models.synthesis_schema import Action
from src.models.technical_schema import TechnicalAnalysis
from src.models.vision_schema import VisualChartAnalysis


logger = logging.getLogger(__name__)


class ChiefStrategistAgent:
    def __init__(
        self,
        llm_client: OpenRouterClient | None = None,
        settings: Settings | None = None,
        researcher: ResearcherAgent | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.researcher = researcher

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
    ) -> StrategyDraft:
        conflict = self.identify_contradictions(fundamentals, technicals, research)
        final_research = research
        if conflict.has_conflict and self.researcher is not None and conflict.deep_dive_query is not None:
            logger.info("CEO triggered debate deep-dive for %s", fundamentals.ticker)
            final_research = self.researcher.investigate_conflict(fundamentals.ticker, conflict.deep_dive_query)
        return self._generate_strategy(fundamentals, technicals, final_research, conflict, visual_chart_analysis)

    def draft_strategy_with_assessment(
        self,
        fundamentals: FundamentalAnalysis,
        technicals: TechnicalAnalysis,
        research: ResearchFinding,
        conflict: ConflictAssessment,
        visual_chart_analysis: VisualChartAnalysis | None = None,
    ) -> StrategyDraft:
        return self._generate_strategy(fundamentals, technicals, research, conflict, visual_chart_analysis)

    def _generate_strategy(
        self,
        fundamentals: FundamentalAnalysis,
        technicals: TechnicalAnalysis,
        research: ResearchFinding,
        conflict: ConflictAssessment,
        visual_chart_analysis: VisualChartAnalysis | None = None,
    ) -> StrategyDraft:
        client = self.llm_client or get_openrouter_client(self.settings)
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are the Chief Strategist Agent. Return only strict JSON matching StrategyDraft. "
                    "Do not calculate indicators or invent numeric metrics. Use provided Python metrics only. "
                    "If bullish, include entry_price, take_profit, and stop_loss using supplied technical levels."
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
                    "Return JSON fields: ticker, action, conviction_score, entry_price, take_profit, stop_loss, "
                    "proposed_position_size_pct, thesis, key_risks, evidence, conflict_assessment."
                ),
            ),
        ]
        response = client.generate_completion(
            model=self.settings.ceo_model,
            messages=messages,
            use_reasoning=self.settings.ceo_model_reasoning,
            temperature=0.1,
        )
        payload = extract_json_object(response.content)
        payload = normalize_strategy_draft(payload, fundamentals.ticker)
        draft = StrategyDraft.model_validate(payload)
        if draft.ticker.upper() != fundamentals.ticker.upper():
            draft = draft.model_copy(update={"ticker": fundamentals.ticker.upper()})
        if draft.conflict_assessment is None:
            draft = draft.model_copy(update={"conflict_assessment": conflict})
        if draft.action in {Action.BUY, Action.ACCUMULATE} and draft.entry_price is None:
            draft = draft.model_copy(update={"action": Action.HOLD, "proposed_position_size_pct": 0})
        return draft
