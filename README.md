# 🧠 Neural Investors Lab

<div align="center">

**Modular multi-agent AI system for stock market analysis, backtesting, and trade signal generation.**

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-orange.svg)](https://openrouter.ai/)
[![PostgreSQL](https://img.shields.io/badge/DB-PostgreSQL-336791.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Cache-Redis-DC382D.svg)](https://redis.io/)

</div>

---

## Overview

Neural Investors Lab is a **boardroom-style AI trading system** where specialized agents — Auditor, Chartist, Researcher, Chief Strategist, and Risk Manager — collaborate to produce structured, auditable investment decisions. The system enriches analysis with live SEC EDGAR filings (8-K, Form 4 insider trades, financials), auto-aggregated news, and multimodal vision-based chart interpretation. Every output is validated through strict Pydantic schemas and persisted to PostgreSQL.

Unlike research prototypes that ask LLMs to calculate numbers, this system enforces a **strict separation of concerns**: all mathematical computation runs in deterministic Python (`pandas`, `pandas-ta`, `numpy`), while LLMs handle only narrative synthesis, sentiment analysis, and strategic reasoning.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     BoardroomOrchestrator                     │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ Auditor  │ Chartist │Researcher│   CEO    │   Risk Manager  │
│ (Python) │(Python + │  (LLM)   │  (LLM)   │  (Math + LLM)   │
│          │ Vision)  │          │          │                 │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                       Service Layer                           │
│  FinanceAPI  │  EdgarAPI  │  IndicatorMath  │  DeepResearch │
├──────────────────────────────────────────────────────────────┤
│                       Infrastructure                          │
│  PostgreSQL (JSONB)  │  Redis (Cache)  │  OpenRouter         │
└──────────────────────────────────────────────────────────────┘
```

### Agents

| Agent | Role | Engine | Model |
|---|---|---|---|
| **Auditor** | Fundamental analysis — Piotroski F-Score, PEG, Altman Z, ROE, D/E, revenue growth; enriched with EDGAR financials as tags | Pure Python | — |
| **Chartist** | Technical analysis — MA alignment, RSI, MACD, MFI, VWAP, ATR, Bollinger Bands, S/R levels, candlestick patterns, trendline fitting; **multimodal vision chart analysis** via mplfinance-rendered candlestick images | Pure Python + numpy + Vision LLM | `NEWS_ANALYST_MODEL` (multimodal) |
| **Researcher** | News sentiment analysis — auto-aggregates yfinance headlines or custom article URLs; enriched with SEC EDGAR 8-K items + Form 4 insider summaries | LLM | `NEWS_ANALYST_MODEL` |
| **Chief Strategist (CEO)** | Synthesizes all agent outputs (fundamentals, technicals, research, visual chart, macro, options), detects contradictions, triggers debate deep-dive, produces BUY/SELL/HOLD decision with conviction score | LLM | `CEO_MODEL` |
| **Risk Manager (CRO)** | Kelly criterion position sizing, VaR limits, ATR-adjusted allocation, final approval/veto | Math + LLM | `CRO_MODEL` |

### Key Design Principles

- **Deterministic Math** — Indicators, patterns, and trendlines are computed in Python/numpy. LLMs never calculate numbers.
- **Strict Contracts** — All inter-agent data passes through Pydantic models with `extra="forbid"`.
- **Debate Mechanism** — When agents disagree (e.g., bullish technicals vs bearish news), the CEO triggers a deep-dive investigation.
- **Anti-403 Caching** — Redis → PostgreSQL → API tiered caching prevents rate limits from `yfinance`, `edgartools`, and news sources. Fetch throttling is configurable via env vars.
- **SEC EDGAR Integration** — Live 8-K filings, Form 4 insider trade summaries, and annual financials from `edgartools` feed directly into Researcher and Auditor prompts.
- **Multimodal Vision** — Candlestick charts are rendered via `mplfinance` and analyzed by a vision-capable LLM for pattern validation beyond raw indicator values.
- **Robust LLM Parsing** — `json_utils.py` normalizes casing drift (e.g., `Neutral` → `neutral`) in constrained enum fields while preserving narrative text.
- **Debug Observability** — `DEBUG_PROMPTS` and `SHOW_AI_DATA` flags let you inspect exactly what data and prompts are sent to every LLM.

---

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (for PostgreSQL + Redis)

### 1. Clone & Install

```bash
git clone https://github.com/Deware-PK/neural-investors-lab.git
cd neural-investors-lab
uv sync
```

### 2. Start Infrastructure

```bash
docker compose up -d
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
TELEGRAM_BOT_TOKEN=your_bot_token      # optional

CEO_MODEL=google/gemini-3.1-flash-lite
CEO_MODEL_REASONING=true

CRO_MODEL=google/gemini-3.1-flash-lite
CRO_MODEL_REASONING=true

NEWS_ANALYST_MODEL=openai/gpt-4o-mini
NEWS_ANALYST_MODEL_REASONING=false

POSTGRES_URL=postgresql://user:password@localhost:5432/arena_db
REDIS_URL=redis://localhost:6379/0

# Rate-limit throttling (seconds, cache-miss only)
FINANCE_FETCH_DELAY_SECONDS=1.5
RESEARCH_FETCH_DELAY_SECONDS=1.5

# SEC EDGAR identity (required for edgartools)
EDGAR_IDENTITY="Your Name your@email.com"

# Logging & debug modes
LOG_LEVEL=INFO
DEBUG_PROMPTS=false          # dump full LLM prompt payloads
SHOW_AI_DATA=false           # dump raw data inputs and LLM outputs
```

### 4. Verify

```bash
uv run python tests/test.py
```

---

## Usage

### Live Analysis

```bash
# Analyze a single ticker (recommended first run — skip DB persistence)
uv run python tests/test.py --live NVDA --no-persist

# With custom article URLs for research context
uv run python tests/test.py --live TSLA --article-url https://example.com/news/tesla

# Skip database persistence
uv run python tests/test.py --live AAPL --no-persist

# Debug modes — see exactly what the AI sees
DEBUG_PROMPTS=true SHOW_AI_DATA=true uv run python tests/test.py --live NVDA --no-persist
```

### Backtesting

```bash
# Generate synthetic historical signals (5 years) then backtest
uv run python tests/test.py --generate-synthetic-backtest AAPL
uv run python tests/test.py --generate-synthetic-backtest MSFT
uv run python tests/test.py --generate-synthetic-backtest GOOGL

# Run backtest report on all stored predictions
uv run python tests/test.py --backtest-report
```

### Telegram Bot

Set `TELEGRAM_BOT_TOKEN` in `.env`, then run the bot to receive analysis via Telegram messages.

---

## Backtest Performance

Results from synthetic signal generation across 16 tickers (101 trades, 5-year lookback):

| Metric | Value |
|---|---|
| Win Rate | **52.48%** |
| Win/Loss | 53W / 47L / 1 open |
| Avg T+7 Return | 1.02% |
| Avg Max Drawdown | -13.53% |

Signal filters: MA bullish alignment + RSI 25-65 + MACD histogram positive + volume bullish + no bearish candlestick patterns.

---

## Project Structure

```
neural-investors-lab/
├── src/
│   ├── agents/              # Agent implementations
│   │   ├── auditor.py           # Fundamental analysis (enriched with EDGAR)
│   │   ├── chartist.py          # Technical + multimodal vision chart analysis
│   │   ├── chief_strategist.py  # CEO decision maker (synthesizes all signals)
│   │   ├── researcher.py        # News sentiment (auto-news + EDGAR context)
│   │   ├── risk_manager.py      # CRO risk review (Kelly + VaR + LLM)
│   │   └── json_utils.py        # LLM output normalization & hardening
│   ├── core/                # Infrastructure
│   │   ├── config.py            # pydantic-settings (env-driven)
│   │   ├── llm_client.py        # OpenRouter SDK wrapper
│   │   ├── db_postgres.py       # PostgreSQL + JSONB persistence
│   │   ├── db_redis.py          # Redis cache
│   │   └── logging.py           # Structured logging setup
│   ├── evaluation/          # Backtesting
│   │   ├── backtest_engine.py
│   │   ├── synthetic_signal_generator.py
│   │   └── performance_logger.py
│   ├── interfaces/          # Output formatting
│   │   ├── formatter.py         # Console / human-readable output
│   │   └── telegram_bot.py      # Telegram bot interface
│   ├── models/              # Pydantic schemas (extra="forbid")
│   │   ├── agent_schema.py
│   │   ├── edgar_schema.py
│   │   ├── evaluation_schema.py
│   │   ├── fundamental_schema.py
│   │   ├── macro_schema.py
│   │   ├── market_data_schema.py
│   │   ├── research_schema.py
│   │   ├── risk_schema.py
│   │   ├── synthesis_schema.py
│   │   ├── technical_schema.py
│   │   └── vision_schema.py
│   ├── services/            # Pure computation & data layer
│   │   ├── edgar_api.py         # SEC EDGAR filings (8-K, Form 4, financials)
│   │   ├── finance_api.py       # yfinance wrapper with Redis + throttling
│   │   ├── indicator_math.py    # All technical indicators (pandas-ta/numpy)
│   │   └── deep_research.py     # News extraction with throttling
│   └── main_orchestrator.py     # Boardroom coordinator
├── docs/
│   ├── project_blueprint.md
│   └── checkpoints/             # Session checkpoint notes
├── reports/                 # Backtest JSON reports
├── tests/
│   ├── __init__.py
│   └── test.py              # CLI test runner
├── docker-compose.yml       # PostgreSQL + Redis
├── pyproject.toml
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.13+ |
| Package Manager | uv |
| LLM Gateway | OpenRouter (OpenAI SDK) |
| Database | PostgreSQL 17 (JSONB) |
| Cache | Redis 7 |
| Data | yfinance, edgartools, newspaper3k |
| Indicators | pandas-ta, numpy |
| Charts | mplfinance |
| Validation | Pydantic v2 |
| Config | pydantic-settings |
| Containerization | Docker Compose |
| Async | asyncio (concurrent data fetching) |

---

## Features

| Feature | Neural Investors Lab |
|---|---|
| Pattern Detection | Deterministic Python (8+ candlestick patterns) |
| Trendline Analysis | numpy optimization |
| Fundamental Analysis | ✅ Piotroski, PEG, Altman Z, ROE, D/E |
| SEC EDGAR Integration | ✅ 8-K filings, Form 4 insider trades, annual financials |
| Vision Chart Analysis | ✅ mplfinance → multimodal LLM (pattern validation) |
| Auto-News Aggregation | ✅ yfinance headlines with Redis caching |
| Risk Management | ✅ Kelly, VaR, ATR-adjusted sizing, CRO review |
| Debate Mechanism | ✅ Contradiction detection + deep-dive re-research |
| Persistent Storage | ✅ PostgreSQL (JSONB) + Redis |
| Backtesting | ✅ Synthetic signals + analytics |
| Telegram + CLI | ✅ |
| Rate-Limit Protection | ✅ Configurable throttling + tiered cache |
| Debug Observability | ✅ DEBUG_PROMPTS + SHOW_AI_DATA modes |
| Cost per Analysis | ~$0.01-0.03 |

---

## License

Not decided yet.

---