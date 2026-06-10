# Checkpoint 11: VI Mode Prompt Pack

**Status:** Done

## Key Changes

### New File
- `src/models/vi_schema.py`: `DecisionState` enum (avoid/watch/probe/accumulate/high_conviction_accumulate), `MandateContext` model with 8 fields for runtime mandate configuration

### Config
- `src/core/config.py`: Added `investment_style` setting (`swing_trader` | `deep_value_vi`, default `swing_trader`)

### Extended Schemas (all new fields optional, default `None`)
- `fundamental_schema.py`: 11 VI auditor fields (quality_score, balance_sheet_score, cash_flow_quality_score, dilution_risk, cyclicality_risk, thesis_durability, valuation_regime, margin_of_safety_pct, thesis_impairment_flag, hard_block_fundamental)
- `technical_schema.py`: 6 VI chartist fields (entry_timing_score, drawdown_severity, support_quality, reversal_confirmation, risk_of_further_underwater_entry, preferred_entry_mode)
- `research_schema.py`: 5 VI researcher fields (near_term_catalyst_strength, long_term_catalyst_strength, insider_signal, thesis_tailwind, narrative_risk)
- `agent_schema.py`: 3 VI fields on StrategyDraft (decision_state, upgrade_trigger, downgrade_trigger)
- `synthesis_schema.py`: 6 VI fields on FinalSynthesis (decision_state, upgrade_trigger, downgrade_trigger, stop_loss_policy, add_on_policy, hard_block_risk); relaxed trade level validation for VI avoid/watch states

### Deterministic Math
- `indicator_math.py`: `_compute_vi_scores()` maps Piotroski→quality_score, Altman→balance_sheet_score, PEG→valuation_regime, Altman<1.0→insolvency_risk hard block. Wired into `analyze_fundamentals()`.

### Mandate-Aware Agent Prompts
- `researcher.py`: Injects VI prefix distinguishing short-term news from long-duration catalysts when mandate is active
- `chief_strategist.py`: Injects VI CEO prompt with staged decision philosophy, requires upgrade/downgrade triggers, requests decision_state in output
- `risk_manager.py`: `_vi_sizing()` implements VI position sizing (probe→0.5%, accumulate→1.5%, high_conviction→3.0%); VI CRO prompt converts role from veto engine to position-sizing governor; `_build_final_synthesis()` carries forward VI fields

### Orchestration & Output
- `main_orchestrator.py`: Builds `MandateContext` when `investment_style == "deep_value_vi"`, passes to ResearcherAgent, ChiefStrategistAgent, RiskManagerAgent
- `formatter.py`: Displays VI decision state with emoji, upgrade/downgrade triggers, stop/add-on policies

## Current State
- `INVESTMENT_STYLE=swing_trader` (default): zero behavioral change, all VI fields `None`
- `INVESTMENT_STYLE=deep_value_vi`: staged decisions, technicals=timing penalties, CRO=governor, VI scoring active

## Validation
- `uv run python -m compileall` — clean on all 13 files
- `uv run python tests/test.py` — offline smoke test passed, full boardroom orchestration OK

## Next Step
- To enable VI mode: set `INVESTMENT_STYLE=deep_value_vi` in `.env`
- Live VI test: `uv run python tests/test.py --live NVDA --no-persist`
