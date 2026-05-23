# Checkpoint: StrategyDraft Bugfix + SHOW_AI_DATA Mode (11)

## Status
- **Status:** Done

## Key Changes
- **Bugfix — json_utils:** `@/d:\Python\neural-investors-lab\src\agents\json_utils.py` `normalize_strategy_draft()` now converts `0.0` / `0` / negative values to `None` for `entry_price`, `take_profit`, and `stop_loss`. This fixes the `pydantic_core.ValidationError: Input should be greater than 0` that occurred when the CEO LLM returned `0.0` for trade levels.
- **Config:** `@/d:\Python\neural-investors-lab\src\core\config.py` added `show_ai_data: bool = Field(default=False, alias="SHOW_AI_DATA")`.
- **Env example:** `@/d:\Python\neural-investors-lab\.env.example` added `SHOW_AI_DATA=false`.
- **Orchestrator:** `@/d:\Python\neural-investors-lab\src\main_orchestrator.py` logs all fetched data objects (Technicals, VisualChart, MacroContext, OptionsFlow, EdgarBundle, Fundamentals, ResearchFinding) as JSON when `show_ai_data` is enabled.
- **LLM Client:** `@/d:\Python\neural-investors-lab\src\core\llm_client.py` logs the raw LLM response content when `show_ai_data` is enabled.

## Current State
- `SHOW_AI_DATA=true` prints the raw structured data inputs (SEC EDGAR, yfinance fundamentals, technicals, research, etc.) and the raw LLM text outputs for every agent.
- `DEBUG_PROMPTS=true` prints the full formatted prompt payloads.
- The two modes are independent: you can use one, both, or neither.
- Compilation is clean.

## Next Step
- Test live run with `SHOW_AI_DATA=true` to verify readability, or proceed to next feature.
