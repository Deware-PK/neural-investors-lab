# Checkpoint 15: Config-Driven & Adaptive Indicator Thresholds

**Status:** Done

## Changes

### `src/core/config.py`
- Added `Settings` fields for all technical thresholds previously hardcoded in `indicator_math.py`: RSI overbought/oversold, MFI overbought/oversold, volume trend bullish/bearish multipliers, bollinger squeeze/low/high quantiles, RS-score weights (3m/6m/9m/12m), supertrend `atr_period`/`multiplier`.
- Added fundamental threshold fields: Piotroski strong/weak cutoffs, PEG cheap/expensive cutoffs, Altman Z safe/distress cutoffs, `_compute_vi_scores` internal Altman buckets, PEG regime cutoffs, insolvency hard-block cutoff.
- Added adaptive threshold mode fields: `adaptive_thresholds` (bool, default `False`), `adaptive_lookback` (default 252), `adaptive_percentile_overbought`/`adaptive_percentile_oversold` (default 0.9/0.1).
- All new fields default to the exact values that were previously hardcoded — zero behavior change unless `.env` overrides are set.

### `src/services/indicator_math.py`
- `IndicatorMath` now takes a `settings: Settings | None` constructor arg (defaults to `get_settings()`).
- `analyze_technical` reads thresholds/weights from `self.settings` and passes them into `_volume_trend`, `_bollinger_state`, `_supertrend`, `_relative_strength`, `_momentum_tag`, `_volume_tag`.
- `analyze_fundamentals` reads Piotroski/PEG/Altman cutoffs from `self.settings` and passes bucket/regime thresholds into `_compute_vi_scores`.
- All previously `@staticmethod` helpers (`_momentum_tag`, `_volume_tag`, `_volume_trend`, `_bollinger_state`, `_relative_strength`, `_compute_vi_scores`) kept as staticmethods with new optional keyword params (defaults = old hardcoded constants) — preserves direct unbound-call unit-testability (e.g. `IndicatorMath._relative_strength(close)` still works).
- Added `_resolve_rsi_thresholds` / `_resolve_mfi_thresholds` instance methods: when `adaptive_thresholds=True` and enough history exists (`>= adaptive_lookback` bars), overbought/oversold bands become the ticker's own trailing-percentile distribution instead of fixed constants; falls back to fixed thresholds otherwise.

### `src/agents/chartist.py`, `src/agents/auditor.py`, `src/main_orchestrator.py`
- `IndicatorMath` and `FinanceAPI` now constructed with the shared `settings` instance instead of defaults, so config actually propagates end-to-end.
- `AuditorAgent` gained a `settings` constructor param.

### `.env.example`
- Documented all new threshold/adaptive-mode variables (commented out, showing defaults).

### `tests/test_indicator_thresholds.py` (new)
- Regression tests confirming default `Settings` reproduce prior hardcoded values.
- Tests confirming custom thresholds (RSI, volume trend multiplier, RS weights, PEG regime, Altman insolvency, Piotroski cutoff) change classification output.
- Adaptive-mode tests: disabled-by-default fixed behavior, percentile-based thresholds when enabled with sufficient history, fallback to fixed thresholds when history is short, MFI adaptive thresholds, end-to-end `analyze_technical` smoke test for both modes.

## Validations
- `pytest tests/ -v` — 20 passed (8 existing + 12 new)
- `py_compile` / `compileall src` — passes
- `ruff check` on touched files — clean (pre-existing unrelated `F401` in `indicator_math.py` for `MandateContext` import, not introduced by this change)
- `uv run python tests/test.py` offline smoke test — passes end-to-end

## Notes
- Risk-related thresholds in `risk_manager.py` (VaR/risk-per-share cutoffs) were explicitly left out of scope per user decision.
- Adaptive mode currently covers RSI + MFI only, per user decision. Volume trend, bollinger, and historical volatility remain fixed-only (config-driven, not adaptive) for now.
- Noticed pre-existing typos unrelated to this task (e.g. `"momentum:oversnew"`, `"volume:oversnew_flow"`, `hnews`/`threshnews` in `docs/project_blueprint.md`) — appears to be a historical bad find/replace of "old"→"new". Not fixed here to avoid scope creep; flagging for a future dedicated cleanup pass if desired.
