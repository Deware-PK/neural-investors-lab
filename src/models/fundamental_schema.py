from pydantic import BaseModel, ConfigDict, Field


class FundamentalSnapshot(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    market_cap: float | None = Field(default=None, ge=0)
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    debt_to_equity: float | None = None
    return_on_equity: float | None = None
    free_cash_flow: float | None = None

    model_config = ConfigDict(extra="forbid")


class FundamentalAnalysis(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    piotroski_f_score: int | None = Field(default=None, ge=0, le=9)
    peg_ratio: float | None = None
    altman_z_score: float | None = None
    tags: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    snapshot: FundamentalSnapshot

    model_config = ConfigDict(extra="forbid")
