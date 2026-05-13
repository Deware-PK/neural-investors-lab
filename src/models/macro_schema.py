from __future__ import annotations

from pydantic import BaseModel, Field


class MacroContext(BaseModel):
    """Macro-economic environment snapshot — sourced entirely from yfinance."""

    model_config = {"extra": "forbid"}

    vix: float | None = Field(None, description="CBOE VIX index — fear gauge (>30=high fear, <15=complacency)")
    vix_regime: str | None = Field(None, description="'low' (<15), 'normal' (15-25), 'elevated' (25-35), 'extreme' (>35)")

    yield_10y: float | None = Field(None, description="US 10-Year Treasury yield (%)")
    yield_5y: float | None = Field(None, description="US 5-Year Treasury yield (%)")
    yield_2y: float | None = Field(None, description="US 2-Year Treasury yield (%)")
    yield_curve_spread: float | None = Field(None, description="10Y minus 2Y spread — negative = inverted = recession warning")
    yield_curve_inverted: bool | None = Field(None, description="True if yield curve is inverted")

    dxy: float | None = Field(None, description="US Dollar Index — strong dollar = headwind for commodities/EM stocks")
    dxy_trend: str | None = Field(None, description="'strengthening' or 'weakening' based on 20-day MA comparison")

    sp500_price: float | None = Field(None, description="S&P 500 latest price")
    sp500_above_200ma: bool | None = Field(None, description="True = bull market regime, False = bear market regime")
    market_regime: str | None = Field(None, description="'bull', 'bear', or 'sideways' based on SPY vs 200MA")

    macro_summary: str | None = Field(None, description="Human-readable 2-3 sentence macro environment summary for CEO prompt")


class OptionsFlow(BaseModel):
    """Options market sentiment for the ticker being analyzed."""

    model_config = {"extra": "forbid"}

    ticker: str
    nearest_expiry: str | None = Field(None, description="Nearest options expiry date (YYYY-MM-DD)")
    put_call_ratio: float | None = Field(None, description="Total Put OI / Total Call OI")
    options_sentiment: str | None = Field(None, description="'bullish' (<0.7), 'neutral' (0.7-1.2), 'bearish' (>1.2)")
    total_call_oi: int | None = Field(None, description="Total Call Open Interest")
    total_put_oi: int | None = Field(None, description="Total Put Open Interest")
    max_pain: float | None = Field(None, description="Max pain price — price where most options expire worthless")


class MultiTimeframeConfluence(BaseModel):
    """Higher-timeframe trend analysis for confluence with daily signals."""

    model_config = {"extra": "forbid"}

    weekly_trend: str | None = Field(None, description="'bullish', 'bearish', or 'neutral' on weekly timeframe")
    monthly_trend: str | None = Field(None, description="'bullish', 'bearish', or 'neutral' on monthly timeframe")
    weekly_close_vs_ma20: str | None = Field(None, description="'above' or 'below' 20-period MA on weekly")
    monthly_close_vs_ma20: str | None = Field(None, description="'above' or 'below' 20-period MA on monthly")
    confluence_tag: str | None = Field(None, description="'aligned_bullish', 'aligned_bearish', 'conflicting', or 'insufficient_data'")
