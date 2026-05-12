# News Vision Integration Checkpoint

## Status
Done

## Key Changes
- Added `mplfinance` dependency for candlestick chart rendering.
- Added `src/models/vision_schema.py` with strict `VisualChartAnalysis` contract.
- Added yfinance news aggregation to `FinanceAPI.fetch_ticker_news` with Redis caching, fetch throttling, and defensive parsing for flat and nested yfinance news payloads.
- Updated `ResearcherAgent` to use provided article URLs when present, otherwise automatically analyze yfinance news headlines/snippets.
- Updated `ChartistAgent` with `_get_chart_image_base64` and async `get_visual_analysis` using mplfinance chart images and `NEWS_ANALYST_MODEL` multimodal calls.
- Wired `visual_chart_analysis` through `BoardroomResult`, Round 1 orchestration, formatter output, and Chief Strategist CEO context.
- Updated offline `test.py` fakes to include visual chart analysis without live LLM/image calls.

## Current State
The boardroom now runs four Round 1 signals: deterministic fundamentals, deterministic technicals, LLM news research from yfinance/news URLs, and vision-based chart analysis. All new handoffs are Pydantic validated. Visual analysis fails closed to neutral if chart rendering or the configured model is unavailable.

## Next Step
Run live mode with a multimodal `NEWS_ANALYST_MODEL`, e.g. `uv run python test.py --live NVDA --no-persist`, and confirm the configured OpenRouter model accepts image inputs.
