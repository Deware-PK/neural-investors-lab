from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VI_RISK_LEVEL = Literal["low", "medium", "high"]
VI_VALUATION_REGIME = Literal["cheap", "reasonable", "expensive"]
VI_HARD_BLOCK = Literal["none", "fraud_risk", "insolvency_risk", "severe_dilution", "governance_break"]


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
    quality_score: float | None = Field(default=None, ge=0, le=10)
    balance_sheet_score: float | None = Field(default=None, ge=0, le=10)
    cash_flow_quality_score: float | None = Field(default=None, ge=0, le=10)
    dilution_risk: VI_RISK_LEVEL | None = None
    cyclicality_risk: VI_RISK_LEVEL | None = None
    thesis_durability: VI_RISK_LEVEL | None = None
    valuation_regime: VI_VALUATION_REGIME | None = None
    margin_of_safety_pct: float | None = None
    thesis_impairment_flag: bool | None = None
    hard_block_fundamental: VI_HARD_BLOCK | None = None

    model_config = ConfigDict(extra="forbid")
