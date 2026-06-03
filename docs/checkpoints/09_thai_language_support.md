# Checkpoint 09: Thai Language Support

**Status:** Done

## Key Changes
- **Created** `src/core/i18n.py` with minimal dict-based i18n layer supporting `en` and `th`.
- **Updated** `src/core/config.py` to add `output_language` setting (default `en`, validated to `en|th`).
- **Updated** `.env.example` to document `OUTPUT_LANGUAGE`.
- **Updated** `tests/test.py` to add `--lang` CLI argument (`choices=["en", "th"]`); passed into `run_live_test` which overrides `settings.output_language`.
- **Updated** `src/interfaces/formatter.py`:
  - Replaced `_sanitize_ascii` with `_sanitize_text` that preserves Unicode/Thai characters.
  - Added `lang` parameter to `format_final_synthesis_html` and `format_boardroom_result_html`.
  - Replaced all hardcoded English labels with `get_text(lang, ...)` lookups.
- **Updated** `src/interfaces/telegram_bot.py` to use i18n lookups for `/start`, `/help`, `/analyze` command responses, and pass `lang` to formatter.
- **Updated** agent system prompts to inject Thai language instructions via `localize_prompt()`:
  - `src/agents/chief_strategist.py` (CEO)
  - `src/agents/researcher.py` (News Analyst)
  - `src/agents/risk_manager.py` (CRO)
  - `src/agents/chartist.py` (Vision Analyst)

## Current State
- All static UI labels, Telegram bot messages, and LLM narrative prompts support Thai via `--lang=th`.
- `_sanitize_text` no longer destroys non-ASCII characters.
- `compileall` passes; offline `uv run python tests/test.py` passes; Thai formatter smoke test passes.

## Next Step
- Test live Thai run: `uv run python tests/test.py --lang=th --live NVDA --no-persist`
