from pydantic import BaseModel, ConfigDict, Field

from src.models.research_schema import SentimentLabel


class VisualChartAnalysis(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    sentiment: SentimentLabel
    confidence_score: float = Field(ge=0, le=1)
    summary: str
    observed_patterns: list[str] = Field(default_factory=list)
    support_zones: list[float] = Field(default_factory=list)
    resistance_zones: list[float] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
