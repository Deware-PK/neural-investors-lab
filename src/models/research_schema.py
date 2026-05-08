from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


SentimentLabel = Literal["bullish", "bearish", "neutral", "mixed"]


class NewsArticle(BaseModel):
    title: str
    url: HttpUrl
    source: str | None = None
    published_at: datetime | None = None
    extracted_text: str | None = None

    model_config = ConfigDict(extra="forbid")


class ResearchFinding(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    sentiment: SentimentLabel
    sentiment_score: float = Field(ge=-1, le=1)
    summary: str
    catalysts: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    articles: list[NewsArticle] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
