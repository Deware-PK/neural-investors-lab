# Checkpoint 12: JSON Repair for Thai LLM Output

**Status:** Done

## Problem
LLM (CEO/ ChiefStrategist) returned JSON with an unterminated string when writing Thai narrative text, causing `json.decoder.JSONDecodeError` in Telegram bot.

## Root Cause
When prompted to write in Thai, the LLM sometimes emits:
- Literal newlines (`\n`) inside JSON string values without escaping them
- Unclosed strings (token limit or malformed output)
- Trailing commas before closing braces

## Fix
**Updated** `src/agents/json_utils.py`:
- Added `_repair_json(text: str) -> str` function that scans character-by-character to:
  1. Escape literal newlines that appear inside JSON strings (`\n` -> `\\n`)
  2. Close unclosed strings with a trailing `"`
  3. Close unclosed braces with trailing `}`
  4. Remove trailing commas before `}` or `]`
- Updated `extract_json_object()` to try strict `json.loads` first, then fall back to `_repair_json()` before giving up

## Validations
- `uv run python -m py_compile src/agents/json_utils.py` — pass
- `uv run python tests/test.py` — offline smoke test pass
- JSON repair unit tests:
  - Thai text with literal newlines inside string → repaired and parsed OK
  - Trailing comma → repaired and parsed OK

## Next Step
- Re-run live Thai test in Telegram bot
