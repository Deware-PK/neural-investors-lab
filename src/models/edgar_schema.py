from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class InsiderTrade(BaseModel):
    """Single Form 4 insider transaction."""

    model_config = {"extra": "forbid"}

    date: date
    insider_name: str
    position: Optional[str] = None
    net_shares: int  # positive=buy, negative=sell, 0=no change


class InsiderTradeSummary(BaseModel):
    """Aggregated summary of recent Form 4 filings."""

    model_config = {"extra": "forbid"}

    total_filings: int
    buy_count: int
    sell_count: int
    zero_count: int
    total_net_shares: int
    largest_tx_name: Optional[str] = None
    largest_tx_date: Optional[date] = None
    largest_tx_shares: Optional[int] = None  # absolute value


class FilingEvent(BaseModel):
    """A single SEC filing event (e.g. 8-K)."""

    model_config = {"extra": "forbid"}

    filing_date: date
    form_type: str
    accession_number: str
    items: list[str] = Field(default_factory=list)
    text_preview: Optional[str] = None


class EdgarFinancials(BaseModel):
    """Key financial metrics from the most recent annual filing."""

    model_config = {"extra": "forbid"}

    revenue: Optional[float] = None
    net_income: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None


class EdgarBundle(BaseModel):
    """Aggregated SEC EDGAR data for a single ticker."""

    model_config = {"extra": "forbid"}

    ticker: str
    company_name: Optional[str] = None
    cik: Optional[str] = None
    filings_8k: list[FilingEvent] = Field(default_factory=list)
    insider_trades: list[InsiderTrade] = Field(default_factory=list)
    insider_summary: Optional[InsiderTradeSummary] = None
    financials: Optional[EdgarFinancials] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
