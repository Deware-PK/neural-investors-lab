# Checkpoint 14: SPY Benchmark for RS Rank

**Status:** Done

## Changes

### `src/agents/chartist.py`
- Added `_fetch_spy_rs_score(period, interval)` private method:
  - Fetches SPY historical prices via `finance_api.fetch_historical_prices`
  - Converts bars to close series via `indicator_math.normalize_price_frame`
  - Computes RS score via `indicator_math._relative_strength`
  - Returns `spy_signal.rs_score` or `None` on failure (wrapped in try/except)
- Modified `analyze()`:
  - Calls `_fetch_spy_rs_score()` after fetching ticker history
  - Passes `benchmark_scores=[spy_rs_score]` to `analyze_technical()` when SPY score is available
  - Log line updated to show `rs_rank`

### `tests/test_chartist_rs.py`
- Added 2 unit tests:
  1. `test_spy_rs_score_injected_when_available`: verifies `benchmark_scores` is passed when SPY fetch succeeds
  2. `test_spy_fetch_failure_falls_back_to_none`: verifies `benchmark_scores=None` fallback when SPY fetch fails, no exception raised

## Validations
- `py_compile` passes
- `pytest tests/test_chartist_rs.py -v` — 2 passed
- `pytest tests/test_indicator_math.py -v` — 6 passed (regression)
- `tests/test.py` offline smoke — passed
- `ruff check src/agents/chartist.py tests/test_chartist_rs.py` — passed

## Notes
- SPY historical prices already cached by `FinanceAPI` (Redis), no extra rate-limit concern
- Single-benchmark percentile behavior: outperform SPY → rs_rank=100, underperform → rs_rank=0, equal → rs_rank=50
