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
    # Fix conflict_assessment: add missing ticker field
    elif "conflict_assessment" in payload and isinstance(payload["conflict_assessment"], dict):
        if "ticker" not in payload["conflict_assessment"]:
            payload["conflict_assessment"]["ticker"] = ticker

    return payload
