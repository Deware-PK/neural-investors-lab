---
status: Done
---

# Defensive Enum Validation (End Whack-a-Mole)

## Key Changes
- **Created** `src/models/_normalizers.py` — centralized enum alias maps and structural helpers (`unwrap_envelope`, `coerce_enum_field`, `ensure_list_of_strings`, `fix_conviction_score`, `fix_sentiment_score`, `fix_confidence_score`, `extract_numbers_from_strings`, `strip_extra_fields`).
- **Added** `model_validator(mode='before')` to every LLM-parsed schema so they **self-heal**:
  - `StrategyDraft` — unwraps envelope, maps `HOLD`→`hnew`, `bullish`→`buy`, etc.; fixes conviction_score scale (0-1 float → 0-100 int); zero/negative trade levels → `None`; string key_risks → list; bad evidence → `[]`; malformed conflict_assessment → `None`.
  - `RiskReview` — unwraps envelope, maps `REJECT`→`vetoed`, `YES`→`approved`, etc.
  - `ResearchFinding` — unwraps envelope, maps `Neutral`→`neutral`; fixes sentiment_score scale (0-100 → -1..1); wraps stray NewsArticle dicts; strips extra article fields.
  - `VisualChartAnalysis` — unwraps envelope, strips extra fields, maps sentiment aliases, fixes confidence_score scale/string-map, extracts floats from string zones.
  - `FinalSynthesis` — maps action/risk_decision aliases, fixes conviction_score, ensures list types.
- **Refactored** `src/agents/json_utils.py`:
  - `parse_json_model(content, model_type)` is now the **single entry point** for all agent JSON parsing. It extracts JSON then calls `model_type.model_validate()` — schemas handle their own normalization.
  - Removed dead code `CONSTRAINED_STRING_FIELDS` and `normalize_string_values`.
- **Refactored all 4 agents** to use `parse_json_model`:
  - `chief_strategist.py`
  - `risk_manager.py`
  - `researcher.py`
  - `chartist.py`
- **Fixed LLM prompts** to reference exact schema enum strings:
  - Chief Strategist: changed `"changing the action to HOLD"` → `"changing the action to 'hnew'"`; added explicit allowed values for `action` and `market_regime`.
  - Risk Manager: added explicit allowed values for `risk_decision`.
- **Fixed** `tests/test.py` `FakeChiefStrategist` signature to match the real agent's expanded parameter list (`macro_context`, `options_flow`).
- **Added** missing `edgartools` dependency to `pyproject.toml` (was required by `edgar_api.py` but not recorded).
- **Removed** `min_length=1` from `VisualChartAnalysis.ticker`, `ResearchFinding.ticker`, and `ConflictAssessment.ticker` — live LLMs sometimes omit the ticker entirely; the agent already patches it after parsing, but validation must not crash first.
- **Fixed** `StrategyDraft._normalize_before` to inject `ticker` into an incomplete `conflict_assessment` dict when the LLM omits it (e.g., `{"has_conflict": False}`).

## Current State
- All schemas automatically coerce common LLM enum aliases (`HOLD`, `bullish`, `Neutral`, `REJECT`, etc.) to strict schema values before validation.
- `parse_json_model` is the single hardened parsing path used by every agent.
- `compileall` passes with zero errors.
- Offline smoke test (`uv run python tests/test.py`) passes end-to-end.
- `HOLD` → `hnew` bug is definitively fixed.

## Next Step
- Run live test: `uv run python tests/test.py --live NVDA --no-persist` to confirm real LLM responses are handled correctly.
