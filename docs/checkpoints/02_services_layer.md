# Services Layer Checkpoint

## Status
Done

## Key Changes
- Added `src/services/finance_api.py` for yfinance profile, historical price, income statement, and balance sheet fetching with Redis cache support.
- Added `src/services/indicator_math.py` for deterministic pandas and pandas-ta calculations covering fundamentals, momentum, trend, volume, volatility, support, resistance, and divergence detection.
- Added `src/services/deep_research.py` for newspaper3k article extraction with Redis cache support.
- Added `src/models/market_data_schema.py` and expanded technical/fundamental schemas with strict service output tags.
- Promoted `newspaper3k`, `pandas-ta`, and `lxml-html-clean` to project dependencies via `uv`.

## Current State
The project now has a deterministic services layer that can fetch market data, calculate institutional-grade indicators in Python, and extract article text without any LLM calls.

## Next Step
Implement Part 4: deterministic Auditor and Chartist agents, LLM Researcher, Chief Strategist, and Risk Manager using the existing service outputs and strict Pydantic contracts.
