from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RiskRating = Literal["low", "moderate", "high", "extreme"]


class PositionSizingInput(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    account_equity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    win_probability: float = Field(ge=0, le=1)
    reward_risk_ratio: float = Field(gt=0)
    atr: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_stop_loss(self) -> "PositionSizingInput":
        if self.stop_loss >= self.entry_price:
            msg = "stop_loss must be below entry_price for long position sizing"
            raise ValueError(msg)
        return self


class RiskAssessment(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    position_size_pct: float = Field(ge=0, le=100)
    kelly_fraction: float | None = Field(default=None, ge=0)
    value_at_risk_pct: float | None = Field(default=None, ge=0)
    max_drawdown_pct: float | None = Field(default=None, ge=0)
    risk_rating: RiskRating
    veto: bool = False
    veto_reason: str | None = None

    model_config = ConfigDict(extra="forbid")
