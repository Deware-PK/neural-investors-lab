"""Self-healing normalizers for LLM JSON outputs.

Every schema that is parsed from an LLM response should import helpers from here
and apply them inside a ``model_validator(mode='before')``.  This keeps the
normalization logic co-located with the schema definition and eliminates the
need for ad-hoc per-agent ``normalize_*`` functions.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Exhaustive enum alias maps
# ---------------------------------------------------------------------------

ACTION_ALIASES: dict[str, str] = {
    "bullish": "buy",
    "bull": "buy",
    "long": "buy",
    "strong buy": "buy",
    "accumulate": "accumulate",
    "add": "accumulate",
    "build": "accumulate",
    "scale in": "accumulate",
    "increase": "accumulate",
    "hold": "hnew",
    "hnew": "hnew",
    "hodl": "hnew",
    "wait": "hnew",
    "watch": "hnew",
    "pass": "hnew",
    "stay": "hnew",
    "flat": "hnew",
    "nothing": "hnew",
    "maintain": "hnew",
    "keep": "hnew",
    "neutral": "hnew",
    "reduce": "reduce",
    "trim": "reduce",
    "decrease": "reduce",
    "scale out": "reduce",
    "sell": "sell",
    "bearish": "sell",
    "bear": "sell",
    "short": "sell",
    "exit": "sell",
    "close": "sell",
    "dump": "sell",
    "liquidate": "sell",
    "avoid": "avoid",
    "stay away": "avoid",
    "skip": "avoid",
    "reject": "avoid",
    "danger": "avoid",
}

SENTIMENT_ALIASES: dict[str, str] = {
    "positive": "bullish",
    "bull": "bullish",
    "up": "bullish",
    "buy": "bullish",
    "bullish": "bullish",
    "negative": "bearish",
    "bear": "bearish",
    "down": "bearish",
    "sell": "bearish",
    "bearish": "bearish",
    "neutral": "neutral",
    "mixed": "mixed",
    "uncertain": "neutral",
    "sideways": "neutral",
    "flat": "neutral",
    "unclear": "neutral",
    "inconclusive": "neutral",
}

RISK_DECISION_ALIASES: dict[str, str] = {
    "approved": "approved",
    "approve": "approved",
    "accept": "approved",
    "accepted": "approved",
    "yes": "approved",
    "ok": "approved",
    "go": "approved",
    "pass": "approved",
    "green light": "approved",
    "vetoed": "vetoed",
    "reject": "vetoed",
    "rejected": "vetoed",
    "denied": "vetoed",
    "no": "vetoed",
    "disapproved": "vetoed",
    "blocked": "vetoed",
    "refuse": "vetoed",
    "decline": "vetoed",
    "adjusted": "adjusted",
    "limit": "adjusted",
    "conditional": "adjusted",
    "modify": "adjusted",
    "modified": "adjusted",
    "partial": "adjusted",
    "restricted": "adjusted",
    "amend": "adjusted",
    "tweak": "adjusted",
    "lower": "adjusted",
    "conditional approval": "adjusted",
    "approved with limit": "adjusted",
    "approved with conditions": "adjusted",
    "approved with modification": "adjusted",
    "approve_with_limit": "adjusted",
    "approved_limited": "adjusted",
    "adjusted_down": "adjusted",
    "adjusted_up": "adjusted",
    "partially_approved": "adjusted",
    "limited": "adjusted",
    "approved_with_reduction": "adjusted",
    "reduced": "adjusted",
}

DIVERGENCE_ALIASES: dict[str, str] = {
    "none": "none",
    "no divergence": "none",
    "flat": "none",
    "neutral": "none",
    "bullish_divergence": "bullish_divergence",
    "bullish divergence": "bullish_divergence",
    "bullish": "bullish_divergence",
    "bull": "bullish_divergence",
    "positive": "bullish_divergence",
    "bearish_divergence": "bearish_divergence",
    "bearish divergence": "bearish_divergence",
    "bearish": "bearish_divergence",
    "bear": "bearish_divergence",
    "negative": "bearish_divergence",
}

VOLATILITY_ALIASES: dict[str, str] = {
    "low": "low",
    "normal": "normal",
    "high": "high",
    "extreme": "high",
    "squeeze": "squeeze",
    "tight": "squeeze",
    "narrow": "squeeze",
    "breakout": "breakout",
    "expanding": "breakout",
    "wide": "breakout",
}

TRENDLINE_ALIASES: dict[str, str] = {
    "compressing": "compressing",
    "contracting": "compressing",
    "converging": "compressing",
    "expanding": "expanding",
    "diverging": "expanding",
    "parallel": "parallel",
    "neutral": "parallel",
    "undefined": "undefined",
    "unknown": "undefined",
    "none": "undefined",
}

PATTERN_SENTIMENT_ALIASES: dict[str, str] = {
    "positive": "bullish",
    "bull": "bullish",
    "up": "bullish",
    "bullish": "bullish",
    "negative": "bearish",
    "bear": "bearish",
    "down": "bearish",
    "bearish": "bearish",
    "neutral": "neutral",
    "flat": "neutral",
    "mixed": "neutral",
}

RISK_RATING_ALIASES: dict[str, str] = {
    "low": "low",
    "moderate": "moderate",
    "medium": "moderate",
    "med": "moderate",
    "average": "moderate",
    "high": "high",
    "extreme": "extreme",
    "very high": "extreme",
    "severe": "extreme",
    "critical": "extreme",
    "max": "extreme",
}

MARKET_REGIME_ALIASES: dict[str, str] = {
    "bull": "bull",
    "bull market": "bull",
    "bullish": "bull",
    "uptrend": "bull",
    "bear": "bear",
    "bear market": "bear",
    "bearish": "bear",
    "downtrend": "bear",
    "sideways": "sideways",
    "range": "sideways",
    "neutral": "sideways",
    "flat": "sideways",
    "consolidation": "sideways",
}

# Field-name → alias map
FIELD_ALIAS_MAP: dict[str, dict[str, str]] = {
    "action": ACTION_ALIASES,
    "sentiment": SENTIMENT_ALIASES,
    "risk_decision": RISK_DECISION_ALIASES,
    "divergence": DIVERGENCE_ALIASES,
    "bollinger_state": VOLATILITY_ALIASES,
    "volume_trend": SENTIMENT_ALIASES,
    "moving_average_state": SENTIMENT_ALIASES,
    "state": SENTIMENT_ALIASES,  # generic fallback for TrendState fields
    "pattern_sentiment": PATTERN_SENTIMENT_ALIASES,
    "risk_rating": RISK_RATING_ALIASES,
    "market_regime": MARKET_REGIME_ALIASES,
}


# ---------------------------------------------------------------------------
# Structural helpers
# ---------------------------------------------------------------------------

def unwrap_envelope(
    data: dict[str, Any],
    valid_names: set[str],
) -> dict[str, Any]:
    """Unwrap a single-key envelope such as {"StrategyDraft": {...}}."""
    if len(data) != 1:
        return data
    key = next(iter(data))
    value = data[key]
    if key.lower() not in valid_names:
        return data
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return data


def coerce_enum_field(
    data: dict[str, Any],
    field: str,
    alias_map: dict[str, str] | None = None,
) -> None:
    """Lower-case and map a string enum field in-place."""
    if field not in data or not isinstance(data[field], str):
        return
    raw = data[field].strip().lower()
    target_map = alias_map or FIELD_ALIAS_MAP.get(field)
    if target_map is None:
        data[field] = raw
        return
    data[field] = target_map.get(raw, raw)


def ensure_list_of_strings(data: dict[str, Any], field: str) -> None:
    """Guarantee *field* is a list of strings; coerce or default on failure."""
    if field not in data:
        data[field] = []
        return
    value = data[field]
    if isinstance(value, str):
        data[field] = [value]
        return
    if not isinstance(value, list):
        data[field] = []
        return
    cleaned: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned.append(item)
        elif isinstance(item, dict):
            cleaned.append(item.get("title") or item.get("summary") or str(item))
        else:
            cleaned.append(str(item))
    data[field] = cleaned


def strip_extra_fields(data: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    """Remove keys not present in *allowed*."""
    return {k: v for k, v in data.items() if k in allowed}


def extract_numbers_from_strings(items: list[Any]) -> list[float]:
    """Pull the first numeric token out of strings; keep existing numbers."""
    out: list[float] = []
    for item in items:
        if isinstance(item, (int, float)):
            out.append(float(item))
        elif isinstance(item, str):
            match = re.search(r"[\d.]+", item)
            if match:
                try:
                    out.append(float(match.group()))
                except ValueError:
                    pass
    return out


def fix_conviction_score(value: Any) -> int:
    """Normalise a conviction / sentiment_score that may be 0-1 float or string."""
    if isinstance(value, str):
        try:
            value = float(value)
        except (ValueError, TypeError):
            return 0
    if isinstance(value, float) and 0 <= value <= 1:
        return int(value * 100)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def fix_sentiment_score(value: Any) -> float:
    """Normalise a -1..1 sentiment_score that may arrive on a 0-100 scale."""
    if isinstance(value, str):
        try:
            value = float(value)
        except (ValueError, TypeError):
            return 0.0
    if isinstance(value, (int, float)):
        if abs(value) > 1:
            # Assume 0-100 scale: (score - 50) / 50
            return max(-1.0, min(1.0, (value - 50) / 50))
        return float(value)
    return 0.0


def fix_confidence_score(value: Any) -> float:
    """Normalise a 0-1 confidence_score that may arrive on a 0-100 scale or as text."""
    text_map = {
        "very high": 0.95, "very_high": 0.95,
        "high": 0.80,
        "medium": 0.50, "moderate": 0.50,
        "low": 0.30,
        "very low": 0.10, "very_low": 0.10,
        "none": 0.05, "uncertain": 0.20,
    }
    if isinstance(value, str):
        return text_map.get(value.strip().lower(), 0.50)
    if isinstance(value, (int, float)):
        if value > 1:
            return value / 100
        return float(value)
    return 0.50
