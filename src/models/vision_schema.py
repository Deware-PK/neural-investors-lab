from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.research_schema import SentimentLabel


class VisualChartAnalysis(BaseModel):
    ticker: str = Field(max_length=16)
    sentiment: SentimentLabel
    confidence_score: float = Field(ge=0, le=1)
    summary: str
    observed_patterns: list[str] = Field(default_factory=list)
    support_zones: list[float] = Field(default_factory=list)
    resistance_zones: list[float] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalize_before(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        from src.models._normalizers import (
            coerce_enum_field,
            ensure_list_of_strings,
            extract_numbers_from_strings,
            fix_confidence_score,
            strip_extra_fields,
            unwrap_envelope,
        )

        values = unwrap_envelope(
            values,
            {"visualchartanalysis", "visual_chart_analysis"},
        )
        values = strip_extra_fields(
            values,
            {
                "ticker",
                "sentiment",
                "confidence_score",
                "summary",
                "observed_patterns",
                "support_zones",
                "resistance_zones",
                "risks",
            },
        )
        if "ticker" not in values:
            values["ticker"] = ""
        if "sentiment" not in values:
            values["sentiment"] = "neutral"
        if "confidence_score" not in values:
            values["confidence_score"] = 0.50
        if "summary" not in values:
            values["summary"] = "Visual chart analysis could not be fully parsed; defaulting to neutral."
        coerce_enum_field(values, "sentiment")
        if "confidence_score" in values:
            values["confidence_score"] = fix_confidence_score(values["confidence_score"])
        ensure_list_of_strings(values, "observed_patterns")
        ensure_list_of_strings(values, "risks")
        if "support_zones" in values and isinstance(values.get("support_zones"), list):
            values["support_zones"] = extract_numbers_from_strings(values["support_zones"])
        if "resistance_zones" in values and isinstance(values.get("resistance_zones"), list):
            values["resistance_zones"] = extract_numbers_from_strings(values["resistance_zones"])
        return values
