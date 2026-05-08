from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.synthesis_schema import Action, FinalSynthesis


OutcomeLabel = Literal["take_profit_hit", "stop_loss_hit", "open", "expired", "insufficient_data"]


class HistoricalPrediction(BaseModel):
    record_id: str
    ticker: str = Field(min_length=1, max_length=16)
    created_at: datetime
    synthesis: FinalSynthesis

    model_config = ConfigDict(extra="forbid")


class BacktestOutcome(BaseModel):
    record_id: str
    ticker: str = Field(min_length=1, max_length=16)
    action: Action
    created_at: datetime
    entry_price: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    t7_return_pct: float | None = None
    t30_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    outcome: OutcomeLabel
    hit_take_profit: bool = False
    hit_stop_loss: bool = False

    model_config = ConfigDict(extra="forbid")


class PerformanceReport(BaseModel):
    generated_at: datetime
    total_trades: int = Field(ge=0)
    win_rate_pct: float = Field(ge=0, le=100)
    average_t7_return_pct: float | None = None
    average_t30_return_pct: float | None = None
    average_max_drawdown_pct: float | None = None
    outcomes: dict[str, int] = Field(default_factory=dict)
    pattern_notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
