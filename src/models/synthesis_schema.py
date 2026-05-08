from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Action(StrEnum):
    BUY = "buy"
    ACCUMULATE = "accumulate"
    HOLD = "hnew"
    REDUCE = "reduce"
    SELL = "sell"
    AVOID = "avoid"


class RiskDecision(StrEnum):
    APPROVED = "approved"
    VETOED = "vetoed"
    ADJUSTED = "adjusted"


class EvidenceItem(BaseModel):
    source: str
    claim: str
    weight: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class FinalSynthesis(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    action: Action
    conviction_score: int = Field(ge=0, le=100)
    entry_price: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    position_size_pct: float = Field(ge=0, le=100)
    risk_decision: RiskDecision
    thesis: str
    key_risks: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_trade_levels(self) -> "FinalSynthesis":
        bullish_actions = {Action.BUY, Action.ACCUMULATE}
        if self.action in bullish_actions:
            missing = [
                field_name
                for field_name in ("entry_price", "take_profit", "stop_loss")
                if getattr(self, field_name) is None
            ]
            if missing:
                msg = f"Bullish actions require trade levels: {', '.join(missing)}"
                raise ValueError(msg)
            if self.stop_loss is not None and self.entry_price is not None and self.stop_loss >= self.entry_price:
                msg = "stop_loss must be below entry_price for bullish recommendations"
                raise ValueError(msg)
            if self.take_profit is not None and self.entry_price is not None and self.take_profit <= self.entry_price:
                msg = "take_profit must be above entry_price for bullish recommendations"
                raise ValueError(msg)
        return self
