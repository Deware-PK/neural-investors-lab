# Checkpoint 10: Tavily Advanced Search Integration

**Status:** Done

## Key Changes
- `src/core/config.py`: Added 4 settings — `tavily_api_key` (SecretStr), `advanced_search` (bool, default False), `tavily_max_results` (int, 1-10), `tavily_search_depth` (Literal["ultra-fast","basic","fast","advanced"])
- `src/services/tavily_research.py` (new): `TavilyResearchService` with lazy import of `tavily.TavilyClient`, graceful degradation (returns `[]` if no key or import fails), `topic="finance"`, `time_range="week"`, content capped at 1500 chars, credits logged
- `src/agents/researcher.py`: Added `tavily` param to `__init__`, merge logic in `analyze()` — URL-deduplicates Tavily results against existing Yahoo Finance articles
- `src/main_orchestrator.py`: Conditionally creates `TavilyResearchService` when `advanced_search=True`, passes to `ResearcherAgent`
- `.env.example`: Added commented-out Tavily section
- `pyproject.toml`: Added `[project.optional-dependencies] advanced-search = ["tavily-python>=0.5.0"]`
- Installed `tavily-python==0.7.25` + `tiktoken==0.13.0`

## Current State
- `ADVANCED_SEARCH=false` (default): pipeline behaves identically to before — zero impact
- `ADVANCED_SEARCH=true` + no key: logs warning, skips gracefully
- `ADVANCED_SEARCH=true` + valid key: Tavily articles merged with URL dedup, credits tracked

## Validation
- `uv run python -m compileall` — clean on all 4 files
- `uv run python tests/test.py` — offline smoke test passed, full boardroom orchestration OK

## Next Step
- To enable: set `ADVANCED_SEARCH=true` and `TAVILY_API_KEY=tvly-...` in `.env`
- Live test: `uv run python tests/test.py --live NVDA --no-persist`
