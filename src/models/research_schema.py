from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


SentimentLabel = Literal["bullish", "bearish", "neutral", "mixed"]


class NewsArticle(BaseModel):
    title: str
    url: str | None = None
    source: str | None = None
    published_at: datetime | None = None
    extracted_text: str | None = None

    model_config = ConfigDict(extra="forbid")


class ResearchFinding(BaseModel):
    ticker: str = Field(max_length=16)
    sentiment: SentimentLabel
    sentiment_score: float = Field(ge=-1, le=1)
    summary: str
    catalysts: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    articles: list[NewsArticle] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalize_before(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        from src.models._normalizers import (
            coerce_enum_field,
            ensure_list_of_strings,
            fix_sentiment_score,
            strip_extra_fields,
            unwrap_envelope,
        )

        values = unwrap_envelope(
            values,
            {"researchfinding", "research_finding"},
        )
        # If the payload looks like a single NewsArticle (has title/url but no ticker),
        # wrap it into a ResearchFinding.
        if "ticker" not in values and ("title" in values or "url" in values):
            values = {
                "ticker": "",
                "sentiment": "neutral",
                "sentiment_score": 0,
                "summary": "Research finding constructed from article data.",
                "catalysts": [],
                "concerns": [],
                "articles": [values],
            }
        if "ticker" not in values:
            values["ticker"] = ""
        coerce_enum_field(values, "sentiment")
        if "sentiment_score" in values:
            values["sentiment_score"] = fix_sentiment_score(values["sentiment_score"])
        if "summary" not in values:
            values["summary"] = "News analysis summary could not be parsed; defaulting to neutral."
        ensure_list_of_strings(values, "catalysts")
        ensure_list_of_strings(values, "concerns")
        allowed_article_fields = {"title", "url", "source", "published_at", "extracted_text"}
        if "articles" in values and isinstance(values["articles"], list):
            normalized: list[dict[str, Any]] = []
            for item in values["articles"]:
                if isinstance(item, str):
                    normalized.append({"title": item, "url": item})
                elif isinstance(item, dict):
                    cleaned = strip_extra_fields(item, allowed_article_fields)
                    if "title" not in cleaned and "url" in cleaned:
                        cleaned["title"] = cleaned["url"]
                    elif "title" not in cleaned:
                        cleaned["title"] = "Unknown"
                    normalized.append(cleaned)
            values["articles"] = normalized
        return values
