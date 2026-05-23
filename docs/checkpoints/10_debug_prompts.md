# Checkpoint: Debug Prompts Logging (10)

## Status
- **Status:** Done

## Key Changes
- **Config:** `@/d:\Python\neural-investors-lab\src\core\config.py` added `debug_prompts: bool = Field(default=False, alias="DEBUG_PROMPTS")`.
- **Env example:** `@/d:\Python\neural-investors-lab\.env.example` added `DEBUG_PROMPTS=false`.
- **LLM Client:** `@/d:\Python\neural-investors-lab\src\core\llm_client.py` added `_sanitize_messages_for_logging()` static method and `debug_prompts` gated `logger.debug` dump of the full request payload inside `generate_completion()`. Base64 image strings are truncated to `...<base64 truncated>...`.

## Current State
- Setting `DEBUG_PROMPTS=true` in `.env` and `LOG_LEVEL=DEBUG` will print the complete system and user messages sent to every LLM (Researcher, CEO, CRO, Vision Chartist) before the API call.
- This captures SEC EDGAR data, news articles, fundamentals, technicals, macro, options, and chart images in a single upstream location.
- Compilation is clean.

## Next Step
- Test with `DEBUG_PROMPTS=true` against a live ticker to verify output readability, or proceed to next feature.
