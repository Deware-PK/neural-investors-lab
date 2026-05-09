# Rate Limit and LLM Normalization Checkpoint

## Status
Done

## Key Changes
- Added configurable `FINANCE_FETCH_DELAY_SECONDS` and `RESEARCH_FETCH_DELAY_SECONDS` settings with `1.5` second defaults.
- Added cache-miss-only throttling in `FinanceAPI` before yfinance profile, history, income statement, and balance sheet calls.
- Added cache-miss-only throttling in `DeepResearchService` before article downloads/parsing.
- Wired `BoardroomOrchestrator` to pass shared settings into `FinanceAPI` and `DeepResearchService`.
- Added constrained-field string normalization in `src/agents/json_utils.py` so LLM enum/literal outputs like `Neutral` validate as `neutral` without lowercasing narrative text.

## Current State
External finance/research fetches are throttled by default to reduce rate-limit risk, cache hits remain fast, and live LLM responses are more robust against casing drift in strict JSON fields.

## Next Step
Retry live console mode with `uv run python test.py --live NVDA --no-persist` first, then run without `--no-persist` only when PostgreSQL is ready for writes.
