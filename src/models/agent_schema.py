from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.synthesis_schema import Action, EvidenceItem, RiskDecision
from src.models.vi_schema import DecisionState


class ConflictAssessment(BaseModel):
    ticker: str = Field(max_length=16)
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
    decision_state: DecisionState | None = None
    upgrade_trigger: str | None = None
    downgrade_trigger: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalize_before(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        from src.models._normalizers import (
            coerce_enum_field,
            ensure_list_of_strings,
            fix_conviction_score,
            unwrap_envelope,
        )

        values = unwrap_envelope(values, {"strategydraft", "strategy_draft"})
        coerce_enum_field(values, "action")
        if "conviction_score" in values:
            values["conviction_score"] = fix_conviction_score(values["conviction_score"])
        for level_field in ("entry_price", "take_profit", "stop_loss"):
            if level_field in values:
                val = values[level_field]
                if isinstance(val, (int, float)) and val <= 0:
                    values[level_field] = None
        if "proposed_position_size_pct" not in values or values.get("proposed_position_size_pct") is None:
            values["proposed_position_size_pct"] = 0.0
        elif isinstance(values.get("proposed_position_size_pct"), str):
            try:
                values["proposed_position_size_pct"] = float(values["proposed_position_size_pct"])
            except (ValueError, TypeError):
                values["proposed_position_size_pct"] = 0.0
        coerce_enum_field(values, "market_regime")
        if "vix_level" in values and isinstance(values.get("vix_level"), str):
            try:
                values["vix_level"] = float(values["vix_level"])
            except (ValueError, TypeError):
                values["vix_level"] = None
        ensure_list_of_strings(values, "key_risks")
        if "evidence" in values and not isinstance(values.get("evidence"), list):
            values["evidence"] = []
        elif "evidence" in values and isinstance(values.get("evidence"), list):
            if values["evidence"] and isinstance(values["evidence"][0], str):
                values["evidence"] = []
        if "conflict_assessment" in values:
            ca = values["conflict_assessment"]
            if isinstance(ca, (str, bool)):
                values["conflict_assessment"] = None
            elif isinstance(ca, dict):
                allowed = {"ticker", "has_conflict", "reasons", "deep_dive_query"}
                values["conflict_assessment"] = {k: v for k, v in ca.items() if k in allowed}
                if "ticker" not in values["conflict_assessment"]:
                    values["conflict_assessment"]["ticker"] = values.get("ticker", "")
        return values

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

    @model_validator(mode="before")
    @classmethod
    def _normalize_before(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        from src.models._normalizers import coerce_enum_field, unwrap_envelope

        values = unwrap_envelope(values, {"riskreview", "risk_review"})
        coerce_enum_field(values, "risk_decision")
        return values
