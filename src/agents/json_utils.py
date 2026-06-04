import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_json_model(content: str, model_type: type[ModelT]) -> ModelT:
    """Extract JSON from an LLM response and validate it against *model_type*.

    Schemas that are parsed from LLM output must define a
    ``model_validator(mode='before')`` that normalises enum aliases, fixes
    numeric scales, unwraps envelopes, and strips extra fields.  This keeps
    parsing logic co-located with the schema and removes the need for ad-hoc
    ``normalize_*`` helper functions.
    """
    payload = extract_json_object(content)
    return model_type.model_validate(payload)


def _repair_json(text: str) -> str:
    """Repair common LLM JSON malformations (unescaped newlines/quotes, unclosed strings/braces)."""
    result: list[str] = []
    in_string = False
    escape_next = False
    i = 0
    while i < len(text):
        char = text[i]
        if escape_next:
            result.append(char)
            escape_next = False
            i += 1
            continue
        if char == "\\":
            result.append(char)
            escape_next = True
            i += 1
            continue
        if char == '"':
            in_string = not in_string
            result.append(char)
            i += 1
            continue
        if char == "\n" and in_string:
            result.append("\\n")
            i += 1
            continue
        result.append(char)
        i += 1

    repaired = "".join(result)
    if in_string:
        repaired += '"'

    # Close unclosed braces
    open_braces = repaired.count("{") - repaired.count("}")
    if open_braces > 0:
        repaired += "}" * open_braces

    # Remove trailing commas before closing braces/brackets
    repaired = re.sub(r",\s*}", "}", repaired)
    repaired = re.sub(r",\s*]", "]", repaired)

    return repaired


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

    # Try strict parse first
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        # Attempt repair for common LLM malformations (Thai text, unescaped chars, etc.)
        repaired = _repair_json(stripped)
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError as exc:
            msg = f"Could not parse LLM JSON response even after repair: {exc}"
            raise ValueError(msg) from exc

    if not isinstance(parsed, dict):
        msg = "Expected a JSON object from LLM response"
        raise ValueError(msg)
    return parsed


def normalize_strategy_draft(payload: dict[str, Any], ticker: str) -> dict[str, Any]:
    """Fix common LLM JSON errors in StrategyDraft responses."""
    # Unwrap envelope like {"StrategyDraft": {...}}
    if len(payload) == 1:
        key = next(iter(payload))
        if isinstance(payload[key], dict) and key.lower() in ("strategydraft", "strategy_draft"):
            payload = payload[key]
        elif isinstance(payload[key], list) and key.lower() in ("strategydraft", "strategy_draft"):
            items = payload[key]
            if items and isinstance(items[0], dict):
                payload = items[0]
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

    # Fix market_regime: map common LLM variants
    if "market_regime" in payload and isinstance(payload["market_regime"], str):
        regime_lower = payload["market_regime"].strip().lower()
        regime_map = {
            "bull market": "bull", "bullish": "bull",
            "bear market": "bear", "bearish": "bear",
            "sideways market": "sideways", "range": "sideways", "neutral": "sideways",
        }
        payload["market_regime"] = regime_map.get(regime_lower, regime_lower)

    # Fix vix_level: convert string to float
    if "vix_level" in payload and isinstance(payload["vix_level"], str):
        try:
            payload["vix_level"] = float(payload["vix_level"])
        except (ValueError, TypeError):
            payload["vix_level"] = None

    # Fix trade levels: 0.0/0/negative values from LLM should be treated as None (schema requires gt=0)
    for level_field in ("entry_price", "take_profit", "stop_loss"):
        if level_field in payload:
            val = payload[level_field]
            if isinstance(val, (int, float)) and val <= 0:
                payload[level_field] = None

    # Fix proposed_position_size_pct: None or missing should default to 0.0 (schema is non-nullable float)
    if "proposed_position_size_pct" not in payload or payload["proposed_position_size_pct"] is None:
        payload["proposed_position_size_pct"] = 0.0
    elif isinstance(payload["proposed_position_size_pct"], str):
        try:
            payload["proposed_position_size_pct"] = float(payload["proposed_position_size_pct"])
        except (ValueError, TypeError):
            payload["proposed_position_size_pct"] = 0.0

    return payload


VISUAL_CHART_ALLOWED_FIELDS = {
    "ticker", "sentiment", "confidence_score", "summary",
    "observed_patterns", "support_zones", "resistance_zones", "risks",
}


def normalize_visual_chart_analysis(payload: dict[str, Any], ticker: str = "") -> dict[str, Any]:
    """Fix common LLM JSON errors in VisualChartAnalysis responses."""
    import re

    # Strip extra fields not in the schema
    payload = {k: v for k, v in payload.items() if k in VISUAL_CHART_ALLOWED_FIELDS}

    # Unwrap envelope like {"VisualChartAnalysis": {...}}
    if len(payload) == 1:
        key = next(iter(payload))
        if isinstance(payload[key], dict) and key.lower() in ("visualchartanalysis", "visual_chart_analysis"):
            payload = payload[key]
            payload = {k: v for k, v in payload.items() if k in VISUAL_CHART_ALLOWED_FIELDS}
        elif isinstance(payload[key], list) and key.lower() in ("visualchartanalysis", "visual_chart_analysis"):
            items = payload[key]
            if items and isinstance(items[0], dict):
                payload = items[0]
                payload = {k: v for k, v in payload.items() if k in VISUAL_CHART_ALLOWED_FIELDS}

    # Fill missing required fields with safe defaults
    if "ticker" not in payload:
        payload["ticker"] = ticker
    if "sentiment" not in payload:
        payload["sentiment"] = "neutral"
    if "confidence_score" not in payload:
        payload["confidence_score"] = 0.50
    if "summary" not in payload:
        payload["summary"] = "Visual chart analysis could not be fully parsed; defaulting to neutral."

    # Fix sentiment: lowercase and map common variants
    if isinstance(payload.get("sentiment"), str):
        raw = payload["sentiment"].strip().lower()
        sentiment_map = {
            "bull": "bullish", "positive": "bullish",
            "bear": "bearish", "negative": "bearish",
            "neutral": "neutral", "mixed": "mixed",
            "uncertain": "neutral", "sideways": "neutral",
        }
        payload["sentiment"] = sentiment_map.get(raw, raw)

    # Fix confidence_score: convert 0-100 scale to 0-1 scale, and handle string values
    raw = payload.get("confidence_score")
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
    if isinstance(payload.get("observed_patterns"), list):
        payload["observed_patterns"] = [str(item) for item in payload["observed_patterns"]]

    # Fix risks: ensure all items are strings
    if isinstance(payload.get("risks"), list):
        payload["risks"] = [str(item) for item in payload["risks"]]

    # Fix support_zones: extract numbers from strings like "195 - 200"
    if isinstance(payload.get("support_zones"), list):
        normalized_support = []
        for item in payload["support_zones"]:
            if isinstance(item, str):
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
    if isinstance(payload.get("resistance_zones"), list):
        normalized_resistance = []
        for item in payload["resistance_zones"]:
            if isinstance(item, str):
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
    # Unwrap envelope like {"ResearchFinding": {...}} or {"ResearchFinding": [...]}
    if len(payload) == 1:
        key = next(iter(payload))
        if key.lower() in ("researchfinding", "research_finding"):
            value = payload[key]
            if isinstance(value, dict):
                payload = value
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # If items look like NewsArticles (have title/url), build ResearchFinding
                if any("title" in item or "url" in item for item in value[:1]):
                    payload = {
                        "ticker": "",
                        "sentiment": "neutral",
                        "sentiment_score": 0,
                        "summary": "Research finding constructed from article list.",
                        "catalysts": [],
                        "concerns": [],
                        "articles": value,
                    }
                else:
                    payload = value[0]
    # If payload looks like a NewsArticle (has title/url but no ticker), wrap into ResearchFinding
    if "ticker" not in payload and ("title" in payload or "url" in payload):
        payload = {
            "ticker": "",
            "sentiment": "neutral",
            "sentiment_score": 0,
            "summary": "Research finding constructed from article data.",
            "catalysts": [],
            "concerns": [],
            "articles": [payload],
        }
    # Ensure ticker is always present
    if "ticker" not in payload:
        payload["ticker"] = ""
    # Fix sentiment: map common variants
    if "sentiment" in payload and isinstance(payload["sentiment"], str):
        raw = payload["sentiment"].strip().lower()
        sentiment_map = {
            "positive": "bullish", "bull": "bullish",
            "negative": "bearish", "bear": "bearish",
            "neutral": "neutral", "mixed": "mixed",
        }
        payload["sentiment"] = sentiment_map.get(raw, raw)
    # Fill missing summary with safe default
    if "summary" not in payload:
        payload["summary"] = "News analysis summary could not be parsed; defaulting to neutral."
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

    # Fix catalysts/concerns: wrap single strings into lists, and convert dict items to strings
    for field in ("catalysts", "concerns"):
        if field in payload:
            if isinstance(payload[field], str):
                payload[field] = [payload[field]]
            elif isinstance(payload[field], list):
                normalized = []
                for item in payload[field]:
                    if isinstance(item, str):
                        normalized.append(item)
                    elif isinstance(item, dict):
                        normalized.append(item.get("title") or item.get("summary") or str(item))
                    else:
                        normalized.append(str(item))
                payload[field] = normalized

    return payload


def normalize_risk_review(payload: dict[str, Any]) -> dict[str, Any]:
    """Fix common LLM JSON errors in RiskReview responses."""
    # Unwrap envelope like {"RiskReview": {...}}
    if len(payload) == 1:
        key = next(iter(payload))
        if isinstance(payload[key], dict) and key.lower() in ("riskreview", "risk_review"):
            payload = payload[key]
        elif isinstance(payload[key], list) and key.lower() in ("riskreview", "risk_review"):
            items = payload[key]
            if items and isinstance(items[0], dict):
                payload = items[0]
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
        "reduced": "adjusted",
        "approved_with_reduction": "adjusted",
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
        elif "veto" in decision_lower or "reject" in decision_lower or "denied" in decision_lower:
            payload["risk_decision"] = "vetoed"
        elif "approve" in decision_lower:
            payload["risk_decision"] = "approved"
        else:
            payload["risk_decision"] = "adjusted"

    return payload
