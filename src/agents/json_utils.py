import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)
CONSTRAINED_STRING_FIELDS = {
    "action",
    "bollinger_state",
    "divergence",
    "moving_average_state",
    "risk_decision",
    "sentiment",
    "state",
    "volume_trend",
}


def parse_json_model(content: str, model_type: type[ModelT]) -> ModelT:
    payload = extract_json_object(content)
    payload = normalize_string_values(payload)
    return model_type.model_validate(payload)


def extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced is not None:
        stripped = fenced.group(1)
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end >= start:
            stripped = stripped[start : end + 1]
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        msg = "Expected a JSON object from LLM response"
        raise ValueError(msg)
    return parsed


def normalize_string_values(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_item = normalize_string_values(item)
            if key in CONSTRAINED_STRING_FIELDS and isinstance(normalized_item, str):
                normalized[key] = normalized_item.strip().lower()
            else:
                normalized[key] = normalized_item
        return normalized
    if isinstance(value, list):
        return [normalize_string_values(item) for item in value]
    return value


def normalize_strategy_draft(payload: dict[str, Any], ticker: str) -> dict[str, Any]:
    """Fix common LLM JSON errors in StrategyDraft responses."""
    # Fix action field: map common LLM errors to valid enum values
    action_mapping = {
        "bullish": "buy",
        "bearish": "sell",
        "neutral": "hnew",
        "long": "buy",
        "short": "sell",
    }
    valid_actions = {"buy", "accumulate", "hnew", "reduce", "sell", "avoid"}
    if "action" in payload and isinstance(payload["action"], str):
        action_lower = payload["action"].strip().lower()
        if action_lower in action_mapping:
            payload["action"] = action_mapping[action_lower]
        elif action_lower in valid_actions:
            payload["action"] = action_lower

    # Fix conviction_score: convert float to int (0-100 scale)
    if "conviction_score" in payload and isinstance(payload["conviction_score"], (int, float)):
        # If it's a 0-1 float, convert to 0-100 int
        if isinstance(payload["conviction_score"], float) and 0 <= payload["conviction_score"] <= 1:
            payload["conviction_score"] = int(payload["conviction_score"] * 100)
        else:
            payload["conviction_score"] = int(payload["conviction_score"])

    # Fix key_risks field: if it's a string, convert to list
    if "key_risks" in payload and isinstance(payload["key_risks"], str):
        payload["key_risks"] = [payload["key_risks"]]

    # Fix evidence field: if it's a dict instead of list, default to empty list
    if "evidence" in payload and not isinstance(payload["evidence"], list):
        payload["evidence"] = []
    # Fix evidence items: if they are strings, default to empty list
    elif "evidence" in payload and isinstance(payload["evidence"], list):
        if payload["evidence"] and isinstance(payload["evidence"][0], str):
            payload["evidence"] = []

    # Fix conflict_assessment: if it's a string, default to None
    if "conflict_assessment" in payload and isinstance(payload["conflict_assessment"], str):
        payload["conflict_assessment"] = None
    # Fix conflict_assessment: if it's a boolean, convert to None
    elif "conflict_assessment" in payload and isinstance(payload["conflict_assessment"], bool):
        payload["conflict_assessment"] = None
    # Fix conflict_assessment: add missing ticker field and strip extra fields
    elif "conflict_assessment" in payload and isinstance(payload["conflict_assessment"], dict):
        allowed_ca_fields = {"ticker", "has_conflict", "reasons"}
        payload["conflict_assessment"] = {
            k: v for k, v in payload["conflict_assessment"].items() if k in allowed_ca_fields
        }
        if "ticker" not in payload["conflict_assessment"]:
            payload["conflict_assessment"]["ticker"] = ticker

    return payload


def normalize_visual_chart_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """Fix common LLM JSON errors in VisualChartAnalysis responses."""
    import re

    # Fix sentiment: lowercase and map common variants
    if "sentiment" in payload and isinstance(payload["sentiment"], str):
        raw = payload["sentiment"].strip().lower()
        sentiment_map = {
            "bull": "bullish", "positive": "bullish",
            "bear": "bearish", "negative": "bearish",
            "neutral": "neutral", "mixed": "mixed",
            "uncertain": "neutral", "sideways": "neutral",
        }
        payload["sentiment"] = sentiment_map.get(raw, raw)

    # Fix confidence_score: convert 0-100 scale to 0-1 scale, and handle string values
    if "confidence_score" in payload:
        raw = payload["confidence_score"]
        if isinstance(raw, str):
            confidence_map = {
                "very high": 0.95, "very_high": 0.95,
                "high": 0.80,
                "medium": 0.50, "moderate": 0.50,
                "low": 0.30,
                "very low": 0.10, "very_low": 0.10,
                "none": 0.05, "uncertain": 0.20,
            }
            payload["confidence_score"] = confidence_map.get(raw.strip().lower(), 0.50)
        elif isinstance(raw, (int, float)):
            if raw > 1:
                payload["confidence_score"] = raw / 100

    # Fix observed_patterns: ensure all items are strings
    if "observed_patterns" in payload and isinstance(payload["observed_patterns"], list):
        payload["observed_patterns"] = [str(item) for item in payload["observed_patterns"]]

    # Fix risks: ensure all items are strings
    if "risks" in payload and isinstance(payload["risks"], list):
        payload["risks"] = [str(item) for item in payload["risks"]]

    # Fix support_zones: extract numbers from strings like "195 - 200"
    if "support_zones" in payload and isinstance(payload["support_zones"], list):
        normalized_support = []
        for item in payload["support_zones"]:
            if isinstance(item, str):
                # Extract first number from string
                match = re.search(r"[\d.]+", item)
                if match:
                    try:
                        normalized_support.append(float(match.group()))
                    except ValueError:
                        pass
            elif isinstance(item, (int, float)):
                normalized_support.append(float(item))
        payload["support_zones"] = normalized_support

    # Fix resistance_zones: extract numbers from strings like "220 - 225 (Current psychological level)"
    if "resistance_zones" in payload and isinstance(payload["resistance_zones"], list):
        normalized_resistance = []
        for item in payload["resistance_zones"]:
            if isinstance(item, str):
                # Extract first number from string
                match = re.search(r"[\d.]+", item)
                if match:
                    try:
                        normalized_resistance.append(float(match.group()))
                    except ValueError:
                        pass
            elif isinstance(item, (int, float)):
                normalized_resistance.append(float(item))
        payload["resistance_zones"] = normalized_resistance

    return payload


def normalize_research_finding(payload: dict[str, Any]) -> dict[str, Any]:
    """Fix common LLM JSON errors in ResearchFinding responses."""
    # Fix sentiment_score: convert 0-100 scale to -1 to 1 scale
    if "sentiment_score" in payload and isinstance(payload["sentiment_score"], (int, float)):
        if abs(payload["sentiment_score"]) > 1:
            # Convert from 0-100 to -1 to 1: (score - 50) / 50
            payload["sentiment_score"] = (payload["sentiment_score"] - 50) / 50
            # Clamp to valid range
            payload["sentiment_score"] = max(-1, min(1, payload["sentiment_score"]))

    # Fix articles field: if items are strings (URLs or titles), convert to minimal NewsArticle objects
    # Also strip extra fields that the LLM may add (sentiment, sentiment_contribution, etc.)
    allowed_article_fields = {"title", "url", "source", "published_at", "extracted_text"}
    if "articles" in payload and isinstance(payload["articles"], list):
        normalized_articles = []
        for item in payload["articles"]:
            if isinstance(item, str):
                normalized_articles.append({"title": item, "url": item})
            elif isinstance(item, dict):
                cleaned = {k: v for k, v in item.items() if k in allowed_article_fields}
                if "title" not in cleaned and "url" in cleaned:
                    cleaned["title"] = cleaned["url"]
                elif "title" not in cleaned:
                    cleaned["title"] = "Unknown"
                normalized_articles.append(cleaned)
        payload["articles"] = normalized_articles

    # Fix catalysts/concerns: wrap single strings into lists
    for field in ("catalysts", "concerns"):
        if field in payload and isinstance(payload[field], str):
            payload[field] = [payload[field]]

    return payload


def normalize_risk_review(payload: dict[str, Any]) -> dict[str, Any]:
    """Fix common LLM JSON errors in RiskReview responses."""
    # Fix risk_decision field: map common LLM errors to valid enum values
    risk_decision_mapping = {
        "approved_with_limit": "adjusted",
        "approved_with_conditions": "adjusted",
        "approved_with_modification": "adjusted",
        "conditional_approval": "adjusted",
        "approve_with_limit": "adjusted",
        "approved_limited": "adjusted",
        "modified": "adjusted",
        "modify": "adjusted",
        "adjusted_down": "adjusted",
        "adjusted_up": "adjusted",
        "partially_approved": "adjusted",
        "limited": "adjusted",
        "restricted": "adjusted",
        "reject": "vetoed",
        "denied": "vetoed",
        "no": "vetoed",
        "disapproved": "vetoed",
        "rejected": "vetoed",
        "blocked": "vetoed",
        "yes": "approved",
        "accept": "approved",
        "accepted": "approved",
        "ok": "approved",
        "go": "approved",
        "hnew": "approved",
        "wait": "approved",
        "watch": "approved",
    }
    valid_risk_decisions = {"approved", "vetoed", "adjusted"}
    if "risk_decision" in payload and isinstance(payload["risk_decision"], str):
        decision_lower = payload["risk_decision"].strip().lower()
        if decision_lower in risk_decision_mapping:
            payload["risk_decision"] = risk_decision_mapping[decision_lower]
        elif decision_lower in valid_risk_decisions:
            payload["risk_decision"] = decision_lower

    return payload
