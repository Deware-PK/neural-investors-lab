# Checkpoint 12: VI Mode Improvement (CEO + CRO Patch)

**Status:** Done

## Key Changes

### New Files
- `src/core/prompts/ceo_prompt_vi.md`: Externalized VI CEO system prompt with hard-block rules (avoid only if hard_block≠none, thesis_impaired, or expensive+low durability). "Good but expensive" → watch. Requires upgrade/downgrade triggers.
- `src/core/prompts/cro_prompt_vi.md`: Externalized VI CRO system prompt. Kelly=0 does NOT imply 0% allocation. Mapping: avoid/watch→0%, probe→0.25%-max_initial_probe_pct (even if Kelly=0), accumulate/hi-conv→cap with Kelly/VaR.

### Modified Files

**`src/models/agent_schema.py`** — `RiskReview` extended with:
- `stop_loss_policy: str | None`
- `add_on_policy: str | None`
- `hard_block_risk: str | None`

**`src/agents/chief_strategist.py`**:
- Replaced inline VI prefix string with `importlib.resources.files("src.core.prompts").joinpath("ceo_prompt_vi.md").read_text()` + `.format()`
- Added `_post_process_vi_decision()` guard: if LLM returns `avoid` but fundamentals show no hard block, no thesis impairment, and only expensive valuation → downgrades to `watch` + `HOLD`
- Called after `parse_json_model()` in `_generate_strategy()`

**`src/agents/risk_manager.py`**:
- Replaced inline VI CRO prefix with file loading (same pattern as CEO)
- Rewrote `_vi_sizing()`: decision_state drives base size; Kelly computed from conviction+reward_risk acts as cap (not veto); probe gets 0.25% floor even when Kelly=0
- `_review_with_cro` user message requests `stop_loss_policy, add_on_policy, hard_block_risk` when VI mode
- `_build_final_synthesis` uses `review.stop_loss_policy/add_on_policy/hard_block_risk` from CRO LLM response instead of hardcoded values

## Current State
- `INVESTMENT_STYLE=swing_trader` (default): zero behavioral change
- `INVESTMENT_STYLE=deep_value_vi`: prompts externalized, CEO avoids unnecessary `avoid`, CRO allows probe positions with Kelly=0

## Validation
- `uv run python -m compileall` — clean on all 3 modified files
- `uv run python tests/test.py` — offline smoke test passed

## Next Step
- Live VI test: `uv run python tests/test.py --live MP --no-persist --vi`
