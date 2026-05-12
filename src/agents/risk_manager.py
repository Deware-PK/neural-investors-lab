import logging

from src.agents.json_utils import extract_json_object, normalize_risk_review
from src.core.config import Settings, get_settings
from src.core.llm_client import ChatMessage, OpenRouterClient, get_openrouter_client
from src.models.agent_schema import RiskReview, StrategyDraft
from src.models.risk_schema import RiskAssessment
from src.models.synthesis_schema import Action, FinalSynthesis, RiskDecision
from src.models.technical_schema import TechnicalAnalysis


logger = logging.getLogger(__name__)


class RiskManagerAgent:
    def __init__(
        self,
        llm_client: OpenRouterClient | None = None,
        settings: Settings | None = None,
        max_position_size_pct: float = 10,
        max_value_at_risk_pct: float = 2,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.max_position_size_pct = max_position_size_pct
        self.max_value_at_risk_pct = max_value_at_risk_pct

    def finalize(self, draft: StrategyDraft, technicals: TechnicalAnalysis | None = None) -> FinalSynthesis:
        logger.info("Risk Manager started for %s", draft.ticker)
        risk_assessment = self.calculate_risk(draft, technicals)
        review = self._review_with_cro(draft, risk_assessment)
        final = self._build_final_synthesis(draft, risk_assessment, review)
        logger.info(
            "Risk Manager completed for %s: decision=%s, approved_position=%.2f%%, risk_rating=%s, var=%.2f%%, kelly=%.4f",
            draft.ticker,
            final.risk_decision,
            final.position_size_pct,
            risk_assessment.risk_rating,
            risk_assessment.value_at_risk_pct,
            risk_assessment.kelly_fraction,
        )
        return final

    def calculate_risk(self, draft: StrategyDraft, technicals: TechnicalAnalysis | None = None) -> RiskAssessment:
        if draft.action not in {Action.BUY, Action.ACCUMULATE} or draft.entry_price is None or draft.stop_loss is None:
            return RiskAssessment(
                ticker=draft.ticker,
                position_size_pct=0,
                kelly_fraction=0,
                value_at_risk_pct=0,
                max_drawdown_pct=0,
                risk_rating="low",
                veto=False,
            )

        risk_per_share_pct = ((draft.entry_price - draft.stop_loss) / draft.entry_price) * 100
        reward_risk = self._reward_risk_ratio(draft)
        win_probability = self._conviction_to_probability(draft.conviction_score)
        kelly_fraction = self._kelly_fraction(win_probability, reward_risk)
        kelly_position_pct = kelly_fraction * 100
        stop_based_size_pct = self.max_value_at_risk_pct / max(risk_per_share_pct, 0.01) * 100
        volatility_size_pct = self._atr_adjusted_size(draft, technicals)
        proposed = draft.proposed_position_size_pct
        position_size_pct = max(0, min(proposed, kelly_position_pct, stop_based_size_pct, volatility_size_pct, self.max_position_size_pct))
        value_at_risk_pct = position_size_pct * risk_per_share_pct / 100
        risk_rating = self._risk_rating(value_at_risk_pct, risk_per_share_pct, technicals)
        veto = value_at_risk_pct > self.max_value_at_risk_pct or position_size_pct <= 0
        veto_reason = None
        if veto:
            veto_reason = "Position violates risk limits or has no valid risk budget"
        return RiskAssessment(
            ticker=draft.ticker,
            position_size_pct=round(position_size_pct, 2),
            kelly_fraction=round(kelly_fraction, 4),
            value_at_risk_pct=round(value_at_risk_pct, 2),
            max_drawdown_pct=round(risk_per_share_pct, 2),
            risk_rating=risk_rating,
            veto=veto,
            veto_reason=veto_reason,
        )

    def _review_with_cro(self, draft: StrategyDraft, risk_assessment: RiskAssessment) -> RiskReview:
        if risk_assessment.veto:
            return RiskReview(
                risk_decision=RiskDecision.VETOED,
                approved_position_size_pct=0,
                rationale=risk_assessment.veto_reason or "Risk veto applied",
                additional_risks=[],
            )
        if self.llm_client is None and self.settings.openrouter_api_key is None:
            decision = RiskDecision.ADJUSTED if risk_assessment.position_size_pct < draft.proposed_position_size_pct else RiskDecision.APPROVED
            return RiskReview(
                risk_decision=decision,
                approved_position_size_pct=risk_assessment.position_size_pct,
                rationale="Deterministic CRO limits applied without LLM review because OPENROUTER_API_KEY is not configured.",
                additional_risks=[],
            )

        client = self.llm_client or get_openrouter_client(self.settings)
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are the Chief Risk Officer. Return only strict JSON matching RiskReview. "
                    "Do not calculate numbers. Use the provided Python risk assessment as hard limits. "
                    "Never approve a position larger than position_size_pct."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"StrategyDraft: {draft.model_dump(mode='json')}\n"
                    f"PythonRiskAssessment: {risk_assessment.model_dump(mode='json')}\n"
                    "Return JSON fields: risk_decision, approved_position_size_pct, rationale, additional_risks."
                ),
            ),
        ]
        response = client.generate_completion(
            model=self.settings.cro_model,
            messages=messages,
            use_reasoning=self.settings.cro_model_reasoning,
            temperature=0.1,
        )
        payload = extract_json_object(response.content)
        payload = normalize_risk_review(payload)
        review = RiskReview.model_validate(payload)
        approved_size = min(review.approved_position_size_pct, risk_assessment.position_size_pct)
        if approved_size != review.approved_position_size_pct:
            review = review.model_copy(update={"approved_position_size_pct": approved_size, "risk_decision": RiskDecision.ADJUSTED})
        return review

    @staticmethod
    def _build_final_synthesis(draft: StrategyDraft, risk_assessment: RiskAssessment, review: RiskReview) -> FinalSynthesis:
        action = draft.action
        position_size = review.approved_position_size_pct
        risk_decision = review.risk_decision
        if risk_decision == RiskDecision.VETOED:
            action = Action.HOLD if draft.action in {Action.BUY, Action.ACCUMULATE} else draft.action
            position_size = 0
        key_risks = [*draft.key_risks, *review.additional_risks]
        if risk_assessment.veto_reason is not None:
            key_risks.append(risk_assessment.veto_reason)
        thesis = f"{draft.thesis}\nCRO: {review.rationale}"
        return FinalSynthesis(
            ticker=draft.ticker,
            action=action,
            conviction_score=draft.conviction_score,
            entry_price=draft.entry_price,
            take_profit=draft.take_profit,
            stop_loss=draft.stop_loss,
            position_size_pct=round(position_size, 2),
            risk_decision=risk_decision,
            thesis=thesis,
            key_risks=key_risks,
            evidence=draft.evidence,
        )

    @staticmethod
    def _reward_risk_ratio(draft: StrategyDraft) -> float:
        if draft.entry_price is None or draft.stop_loss is None or draft.take_profit is None:
            return 0
        risk = draft.entry_price - draft.stop_loss
        reward = draft.take_profit - draft.entry_price
        if risk <= 0 or reward <= 0:
            return 0
        return reward / risk

    @staticmethod
    def _conviction_to_probability(conviction_score: int) -> float:
        return min(0.7, max(0.35, conviction_score / 100))

    @staticmethod
    def _kelly_fraction(win_probability: float, reward_risk_ratio: float) -> float:
        if reward_risk_ratio <= 0:
            return 0
        loss_probability = 1 - win_probability
        raw_kelly = win_probability - (loss_probability / reward_risk_ratio)
        return max(0, min(raw_kelly * 0.25, 0.1))

    def _atr_adjusted_size(self, draft: StrategyDraft, technicals: TechnicalAnalysis | None) -> float:
        if technicals is None or technicals.volatility.atr is None or draft.entry_price is None:
            return self.max_position_size_pct
        atr_pct = technicals.volatility.atr / draft.entry_price * 100
        if atr_pct >= 8:
            return min(self.max_position_size_pct, 2)
        if atr_pct >= 5:
            return min(self.max_position_size_pct, 4)
        if atr_pct >= 3:
            return min(self.max_position_size_pct, 6)
        return self.max_position_size_pct

    @staticmethod
    def _risk_rating(value_at_risk_pct: float, risk_per_share_pct: float, technicals: TechnicalAnalysis | None) -> str:
        if value_at_risk_pct >= 2 or risk_per_share_pct >= 12:
            return "extreme"
        if value_at_risk_pct >= 1.25 or risk_per_share_pct >= 8:
            return "high"
        if value_at_risk_pct >= 0.75 or (technicals is not None and technicals.volatility.bollinger_state == "high"):
            return "moderate"
        return "low"
