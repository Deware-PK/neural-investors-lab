from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DecisionState(StrEnum):
    AVOID = "avoid"
    WATCH = "watch"
    PROBE = "probe"
    ACCUMULATE = "accumulate"
    HIGH_CONVICTION_ACCUMULATE = "high_conviction_accumulate"


class MandateContext(BaseModel):
    investment_style: Literal["swing_trader", "deep_value_vi"] = "swing_trader"
    time_horizon_days: int = Field(default=540, ge=1)
    allow_countertrend_entries: bool = True
    technicals_role: Literal["timing_only", "balanced", "hard_risk_gate"] = "timing_only"
    entry_mode: Literal["single_shot", "staggered_dca", "probe_then_add"] = "staggered_dca"
    capital_preservation_priority: Literal["low", "medium", "high"] = "medium"
    max_initial_probe_pct: float = Field(default=0.5, ge=0, le=100)
    max_total_position_pct: float = Field(default=3.0, ge=0, le=100)

    model_config = ConfigDict(extra="forbid")
