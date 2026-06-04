# Checkpoint 10: Telegram Bot Button Flow

**Status:** Done

## Key Changes
- **Updated** `src/core/i18n.py` with new bot flow keys:
  - `bot_button_start`, `bot_ask_ticker`, `bot_ask_language`
  - `bot_button_thai`, `bot_button_english`
  - `bot_invalid_ticker`, `bot_cancel`
- **Rewrote** `src/interfaces/telegram_bot.py` with `ConversationHandler`:
  - `/start` → shows inline button "🚀 เริ่มต้นวิเคราะห์ / Start Analysis"
  - Click → bot asks "หุ้นอะไร? / Which ticker?" (state `ASKING_TICKER`)
  - User types ticker → sanitized & validated, then shows language buttons 🇹🇭 / 🇬🇧 (state `SELECTING_LANGUAGE`)
  - Click language → sets `output_language`, runs full analysis with auto news, formats output in chosen language
  - `/cancel` clears session and ends conversation
  - Legacy `/analyze` and `/help` commands preserved as fallbacks for power users

## Current State
- Bot flow is fully button-driven with 2 conversation states.
- Thai/English language selection is per-analysis (user asked every time).
- Auto news fetching (no manual URL input required in button flow).
- Output is clean formatter HTML localized to chosen language.

## Validations
- `uv run python -m py_compile src/interfaces/telegram_bot.py` — pass
- `uv run python tests/test.py` — offline smoke test pass
- Import test — all i18n keys and bot classes import correctly

## Next Step
- Deploy and test live with Telegram bot token.
