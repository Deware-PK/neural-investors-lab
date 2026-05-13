from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.macro_schema import MultiTimeframeConfluence


TrendState = Literal["bullish", "bearish", "neutral", "mixed"]
DivergenceState = Literal["bullish_divergence", "bearish_divergence", "none"]
VolatilityState = Literal["low", "normal", "high", "squeeze", "breakout"]
TrendlineState = Literal["compressing", "expanding", "parallel", "undefined"]
PatternSentiment = Literal["bullish", "bearish", "neutral"]


class MovingAverageAlignment(BaseModel):
    ma50: float | None = None
    ma100: float | None = None
    ma200: float | None = None
    state: TrendState
    tag: str | None = None

    model_config = ConfigDict(extra="forbid")


class MomentumSignal(BaseModel):
    rsi: float | None = Field(default=None, ge=0, le=100)
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    divergence: DivergenceState = "none"
    tag: str | None = None

    model_config = ConfigDict(extra="forbid")


class VolumeSignal(BaseModel):
    mfi: float | None = Field(default=None, ge=0, le=100)
    vwap: float | None = Field(default=None, ge=0)
    point_of_control: float | None = Field(default=None, ge=0)
    volume_trend: TrendState
    tag: str | None = None

    model_config = ConfigDict(extra="forbid")


class VolatilitySignal(BaseModel):
    atr: float | None = Field(default=None, ge=0)
    historical_volatility: float | None = Field(default=None, ge=0)
    bollinger_state: VolatilityState
    tag: str | None = None

    model_config = ConfigDict(extra="forbid")


class TrendlineSignal(BaseModel):
    support_slope: float | None = None
    support_intercept: float | None = None
    resistance_slope: float | None = None
    resistance_intercept: float | None = None
    support_price: float | None = None
    resistance_price: float | None = None
    support_quality: float | None = None
    resistance_quality: float | None = None
    state: TrendlineState = "undefined"
    tag: str | None = None

    model_config = ConfigDict(extra="forbid")


class PatternSignal(BaseModel):
    detected_patterns: list[str] = Field(default_factory=list)
    primary_pattern: str | None = None
    pattern_sentiment: PatternSentiment = "neutral"
    tag: str | None = None

    model_config = ConfigDict(extra="forbid")


class TechnicalAnalysis(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    close_price: float = Field(gt=0)
    moving_average: MovingAverageAlignment
    momentum: MomentumSignal
    volume: VolumeSignal
    volatility: VolatilitySignal
    trendline: TrendlineSignal | None = None
    pattern: PatternSignal | None = None
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    multi_timeframe: MultiTimeframeConfluence | None = None
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
