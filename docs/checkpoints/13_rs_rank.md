# Checkpoint 13: RS Rank Implementation

**Status:** Done

## Changes

### `src/models/technical_schema.py`
- Added `RelativeStrengthSignal` model with `rs_score`, `rs_rank`, `perf_3m/6m/9m/12m`, `tag`
- Added `relative_strength: RelativeStrengthSignal | None = None` to `TechnicalAnalysis`

### `src/services/indicator_math.py`
- Added `RelativeStrengthSignal` to imports
- Added `_relative_strength(close, benchmark_scores=None)` static method:
  - Guard: returns `None` if `len(close) < 63`
  - Calculates weighted composite: `0.4*perf_3m + 0.2*perf_6m + 0.2*perf_9m + 0.2*perf_12m`
  - Percentile rank vs benchmark (default 50 if no benchmark)
  - Tag format: `rs_rank:{N}|score:{score}`
- Updated `analyze_technical()` signature with optional `benchmark_scores`
- Wired `_relative_strength` into `analyze_technical`: calculation, tags list, and `TechnicalAnalysis` return

### `tests/test_indicator_math.py`
- Added 6 unit tests covering:
  - Short history (< 63 bars) → None
  - Empty benchmark → rs_rank == 50
  - Benchmark percentile rank
  - Tag format validation
  - Partial history fallback weights
  - Negative returns allowed

## Validations
- `py_compile` passes
- `pytest tests/test_indicator_math.py` — 6 passed
- `ruff check` passes
- `tests/test.py` offline smoke test passes
