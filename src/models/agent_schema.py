from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.synthesis_schema import Action, EvidenceItem, RiskDecision


class ConflictAssessment(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    has_conflict: bool
    reasons: list[str] = Field(default_factory=list)
    deep_dive_query: str | None = None

    model_config = ConfigDict(extra="forbid")


class StrategyDraft(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    action: Action
    conviction_score: int = Field(ge=0, le=100)
    entry_price: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    proposed_position_size_pct: float = Field(default=0, ge=0, le=100)
    market_regime: str | None = Field(None, description="Market regime at decision time for backtest analytics")
    vix_level: float | None = Field(None, description="VIX value at decision time for backtest analytics")
    thesis: str
    key_risks: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    conflict_assessment: ConflictAssessment | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_trade_levels(self) -> "StrategyDraft":
        if self.action in {Action.BUY, Action.ACCUMULATE}:
            missing = [field_name for field_name in ("entry_price", "take_profit", "stop_loss") if getattr(self, field_name) is None]
            if missing:
                msg = f"Bullish draft requires trade levels: {', '.join(missing)}"
                raise ValueError(msg)
            if self.stop_loss is not None and self.entry_price is not None and self.stop_loss >= self.entry_price:
                msg = "stop_loss must be below entry_price for bullish drafts"
                raise ValueError(msg)
            if self.take_profit is not None and self.entry_price is not None and self.take_profit <= self.entry_price:
                msg = "take_profit must be above entry_price for bullish drafts"
                raise ValueError(msg)
        return self


class RiskReview(BaseModel):
    risk_decision: RiskDecision
    approved_position_size_pct: float = Field(ge=0, le=100)
    rationale: str
    additional_risks: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
