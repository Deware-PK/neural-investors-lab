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

Neural Investors Lab is a **boardroom-style AI trading system** where specialized agents — Auditor, Chartist, Researcher, Chief Strategist, and Risk Manager — collaborate to produce structured, auditable investment decisions. Every output is validated through strict Pydantic schemas and persisted to PostgreSQL.

Unlike research prototypes that ask LLMs to calculate numbers or interpret chart images for pattern recognition, this system enforces a **strict separation of concerns**: all mathematical computation runs in deterministic Python, while LLMs handle only narrative synthesis and strategic reasoning.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   BoardroomOrchestrator                  │
├──────────┬──────────┬──────────┬──────────┬────────────┤
│ Auditor  │ Chartist │Researcher│   CEO    │ Risk Mgr   │
│ (Python) │ (Python) │ (LLM)    │  (LLM)   │ (LLM+Math) │
├──────────┴──────────┴──────────┴──────────┴────────────┤
│                    Service Layer                         │
│  FinanceAPI  │  IndicatorMath  │  DeepResearch          │
├─────────────────────────────────────────────────────────┤
│                    Infrastructure                        │
│  PostgreSQL (JSONB)  │  Redis (Cache)  │  OpenRouter     │
└─────────────────────────────────────────────────────────┘
```

### Agents

| Agent | Role | Engine | Model |
|---|---|---|---|
| **Auditor** | Fundamental analysis — Piotroski F-Score, PEG, Altman Z, ROE, D/E, revenue growth | Pure Python | — |
| **Chartist** | Technical analysis — MA alignment, RSI, MACD, MFI, VWAP, ATR, Bollinger Bands, S/R levels, candlestick patterns, trendline fitting | Pure Python + numpy | — |
| **Researcher** | News sentiment analysis — fetches 10 articles, LLM evaluates catalysts & concerns | LLM | `NEWS_ANALYST_MODEL` |
| **Chief Strategist (CEO)** | Synthesizes all agent outputs, detects contradictions, triggers debate, produces BUY/SELL/HOLD decision with conviction score | LLM | `CEO_MODEL` |
| **Risk Manager (CRO)** | Kelly criterion position sizing, VaR limits, ATR-adjusted allocation, final approval/veto | Math + LLM | `CRO_MODEL` |

### Key Design Principles

- **Deterministic Math** — Indicators, patterns, and trendlines are computed in Python/numpy. LLMs never calculate numbers.
- **Strict Contracts** — All inter-agent data passes through Pydantic models with `extra="forbid"`.
- **Debate Mechanism** — When agents disagree (e.g., bullish technicals vs bearish news), the CEO triggers a deep-dive investigation.
- **Anti-403 Caching** — Redis → PostgreSQL → API tiered caching prevents rate limits from `yfinance` and news sources.

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

CEO_MODEL=google/gemini-3-flash-preview
CEO_MODEL_REASONING=true

CRO_MODEL=moonshotai/kimi-k2.5
CRO_MODEL_REASONING=true

NEWS_ANALYST_MODEL=openai/gpt-4o-mini
NEWS_ANALYST_MODEL_REASONING=false

POSTGRES_URL=postgresql://user:password@localhost:5432/arena_db
REDIS_URL=redis://localhost:6379/0
```

### 4. Verify

```bash
uv run python test.py
```

---

## Usage

### Live Analysis

```bash
# Analyze a single ticker
uv run python test.py --live AAPL

# With custom article URLs for research context
uv run python test.py --live TSLA --article-url https://example.com/news/tesla

# Skip database persistence
uv run python test.py --live NVDA --no-persist
```

### Backtesting

```bash
# Generate synthetic historical signals (5 years) then backtest
uv run python test.py --generate-synthetic-backtest AAPL
uv run python test.py --generate-synthetic-backtest MSFT
uv run python test.py --generate-synthetic-backtest GOOGL

# Run backtest report on all stored predictions
uv run python test.py --backtest-report
```

### Telegram Bot

Set `TELEGRAM_BOT_TOKEN` in `.env`, then run the bot to receive analysis via Telegram messages.

---

## Backtest Performance

Results from synthetic signal generation across 8 tickers (37 trades, 5-year lookback):

| Metric | Value |
|---|---|
| Win Rate | **46%** |
| Win/Loss | 17W / 17L / 3 open |
| Avg T+7 Return | -0.38% |
| Avg Max Drawdown | -7.57% |

Signal filters: MA bullish alignment + RSI 25-65 + MACD histogram positive + volume bullish + no bearish candlestick patterns.

---

## Project Structure

```
neural-investors-lab/
├── src/
│   ├── agents/           # Agent implementations
│   │   ├── auditor.py        # Fundamental analysis
│   │   ├── chartist.py       # Technical + visual analysis
│   │   ├── chief_strategist.py  # CEO decision maker
│   │   ├── researcher.py     # News sentiment
│   │   ├── risk_manager.py   # CRO risk review
│   │   └── json_utils.py     # LLM output normalization
│   ├── core/             # Infrastructure
│   │   ├── config.py         # pydantic-settings
│   │   ├── llm_client.py     # OpenRouter SDK wrapper
│   │   ├── db_postgres.py    # PostgreSQL + JSONB
│   │   └── db_redis.py       # Redis cache
│   ├── evaluation/       # Backtesting
│   │   ├── backtest_engine.py
│   │   ├── synthetic_signal_generator.py
│   │   └── performance_logger.py
│   ├── interfaces/       # Output formatting
│   ├── models/           # Pydantic schemas
│   │   ├── technical_schema.py
│   │   ├── fundamental_schema.py
│   │   ├── research_schema.py
│   │   ├── synthesis_schema.py
│   │   └── vision_schema.py
│   ├── services/         # Pure computation layer
│   │   ├── indicator_math.py  # All technical indicators
│   │   ├── finance_api.py     # yfinance wrapper
│   │   └── deep_research.py   # News extraction
│   └── main_orchestrator.py   # Boardroom coordinator
├── reports/              # Backtest JSON reports
├── docker-compose.yml    # PostgreSQL + Redis
├── pyproject.toml
└── test.py               # CLI test runner
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
| Data | yfinance, newspaper3k |
| Indicators | pandas-ta, numpy |
| Charts | mplfinance |
| Validation | Pydantic v2 |
| Config | pydantic-settings |
| Containerization | Docker Compose |

---

## Features

| Feature | Neural Investors Lab |
|---|---|
| Pattern Detection | Deterministic Python (8 patterns) |
| Trendline Analysis | numpy optimization |
| Fundamental Analysis | ✅ Piotroski, PEG, Altman Z |
| Risk Management | ✅ Kelly, VaR, CRO review |
| Debate Mechanism | ✅ Contradiction detection |
| Persistent Storage | ✅ PostgreSQL + Redis |
| Backtesting | ✅ Synthetic signals + analytics |
| Telegram + CLI | ✅ |
| Cost per Analysis | ~$0.01-0.03 |

---

## License

Not decided yet.

---