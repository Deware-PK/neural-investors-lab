from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


StatementPeriod = Literal["annual", "quarterly"]
StatementType = Literal["income_statement", "balance_sheet"]


class PriceBar(BaseModel):
    date: date
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    adj_close: float | None = Field(default=None, ge=0)
    volume: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class TickerProfile(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    short_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    market_cap: float | None = Field(default=None, ge=0)
    beta: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    dividend_yield: float | None = None
    earnings_growth: float | None = None
    revenue_growth: float | None = None

    model_config = ConfigDict(extra="forbid")


class FinancialStatement(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    statement_type: StatementType
    period: StatementPeriod
    columns: list[str] = Field(default_factory=list)
    rows: dict[str, dict[str, float | None]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class FinanceBundle(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    profile: TickerProfile
    history: list[PriceBar] = Field(default_factory=list)
    income_statement: FinancialStatement
    balance_sheet: FinancialStatement

    model_config = ConfigDict(extra="forbid")
