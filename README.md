# QuantNiti — Conversational NIFTY 50 Strategy Research

QuantNiti is a full-stack research workbench for NIFTY 50 trading strategies. You
describe an idea in chat (or fill in a structured spec), an LLM writes a
Backtrader strategy, the strategy is sandboxed and backtested on real index
history, passed through a quality gate, and then advanced bar-by-bar in a
**simulated paper-trading account**.

> ⚠️ **Educational prototype — paper trading only.**
> Nothing in this repository places a real order, connects to a broker, or moves
> real money. Backtest and paper results are simulations and do not predict
> future returns.

---

## Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Strategy lifecycle](#strategy-lifecycle)
- [Chat and strategy extraction](#chat-and-strategy-extraction)
- [Structured strategy builder](#structured-strategy-builder)
- [Backtest pipeline](#backtest-pipeline)
- [Paper-trading engine](#paper-trading-engine)
- [Market intelligence (dashboard)](#market-intelligence-dashboard)
- [Sandbox and security model](#sandbox-and-security-model)
- [QuantCode-Bench integration](#quantcode-bench-integration)
- [Database and migrations](#database-and-migrations)
- [Frontend guide](#frontend-guide)
- [Testing](#testing)
- [CI](#ci)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Roadmap and known gaps](#roadmap-and-known-gaps)

---

## What it does

| Capability | Where |
|---|---|
| Conversational strategy design with a Groq-hosted LLM | `/studio`, `POST /chat` |
| Structured (form-driven) strategy generation | `/studio/builder`, `POST /strategies/builder` |
| Sandboxed Backtrader backtests over cached NIFTY 50 daily bars | `POST /strategies/{id}/backtest` |
| Quality gate: `draft → backtested → approved → paper_trading` | `/strategies/{id}/approval` |
| Simulated paper-trading account (cash, positions, orders, trades, equity) | `/paper-trading`, `/strategies/{id}/deployment` |
| Market terminal: index quotes, charts, indicators, pulse, breadth, news, AI briefing | `/dashboard` |
| Market News Hub: multi-source aggregation, filters/search, sentiment, trending tickers, stock-linked news | `/news` |
| Conversation and project history | `/studio` sidebar, `/conversations/*` |
| Analytics over cached backtest runs (recalculates nothing) | `/analytics` |
| Public marketing landing page with a simulated live chart | `/` |

Scope note: **NIFTY 50 only.** The data layer maps `NIFTY50 → ^NSEI`; the
builder rejects other markets because no other dataset is wired up.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  React 19 SPA (Vite 8, react-router 7)                               │
│  Landing · Login · Studio · Builder · Dashboard · News · Strategies      │
│  Backtest · Approval · Deployment · Paper Trading · Analytics · Docs  │
└───────────────┬──────────────────────────────────────────────────────┘
                │  fetch JSON (dev: Vite proxy /api → :8000)
┌───────────────▼──────────────────────────────────────────────────────┐
│  FastAPI backend (7 routers, ~60 routes)                             │
│                                                                      │
│  chat ─── Groq LLM ──► strategy_extractor ──► strategies             │
│  strategies ──► backtest_service ──► subprocess: strategy_runner      │
│  strategies ──► deployment_gate ──► paper_engine ──► paper_bars       │
│  dashboard ──► market_data_extended ──► yfinance                     │
│  market (public) ──► yfinance 1-minute ^NSEI                         │
│  news ───► news_service ──► taxonomy + feeds (RSS · Reddit · keys)   │
│  conversations ──► projects / conversations / messages               │
└───────────────┬───────────────────────────┬──────────────────────────┘
                │                           │
      ┌─────────▼─────────┐       ┌─────────▼──────────────────────┐
      │ Postgres 16 / Neon│       │ backend/data/NIFTY50.csv cache │
      │ 12 tables         │       │ (2y daily OHLCV from Yahoo)    │
      │ Alembic-managed   │       └────────────────────────────────┘
      └───────────────────┘
```

- Startup runs `alembic upgrade head` (retried up to 10 times) before serving.
- The backend has **no authentication**. Every request runs as a fixed local
  identity (`dev@local`). The frontend login is cosmetic — see
  [Known gaps](#roadmap-and-known-gaps).

---

## Project structure

```
Ai_Quant/
├── README.md
├── docker-compose.yml            # db + backend + frontend
├── .github/workflows/ci.yml      # backend tests + frontend lint/build
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── pytest.ini
│   ├── .env.example
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/             # 10 migrations, head d5e6f7a8b9c0
│   ├── data/
│   │   └── NIFTY50.csv           # cached OHLCV (regenerated when stale)
│   ├── app/
│   │   ├── main.py               # FastAPI app, lifespan migrations, CORS
│   │   ├── config.py             # pydantic-settings
│   │   ├── database.py           # engine + get_db
│   │   ├── auth.py               # fixed local identity (auth removed)
│   │   ├── ids.py                # UUID validation helpers
│   │   ├── middleware.py         # JSON error handler + CORS origin list
│   │   ├── schemas.py            # all request/response models
│   │   ├── models/
│   │   │   └── db_models.py      # 12 SQLAlchemy models
│   │   ├── routers/
│   │   │   ├── chat.py
│   │   │   ├── conversations.py
│   │   │   ├── dashboard.py      # ~1,300 lines of market intelligence
│   │   │   ├── market.py         # public live/history endpoints
│   │   │   ├── news.py           # Market News Hub feed / refresh / sources
│   │   │   ├── paper.py          # paper-trading hub
│   │   │   └── strategies.py     # builder, lifecycle, backtest, paper
│   │   └── services/
│   │       ├── llm_service.py
│   │       ├── news_service.py   # ingestion, classification, queries
│   │       ├── news_taxonomy.py  # source registry + credibility rules
│   │       ├── strategy_extractor.py
│   │       ├── strategy_builder.py
│   │       ├── finalize_service.py
│   │       ├── backtest_service.py
│   │       ├── strategy_runner.py    # sandboxed worker (standalone file)
│   │       ├── deployment_gate.py
│   │       ├── paper_engine.py
│   │       ├── paper_bars.py
│   │       ├── market_data.py
│   │       ├── market_data_extended.py
│   │       ├── qcb_mapper.py
│   │       └── qcb_evaluator.py
│   └── tests/                    # 19 test modules, 363 checks
└── frontend/
    ├── Dockerfile / nginx.conf / vercel.json
    ├── vite.config.js            # /api → http://localhost:8000 proxy
    ├── package.json
    ├── public/                   # QuantNiti brand kit (SVGs, PNGs, tokens)
    └── src/
        ├── App.jsx               # route map
        ├── main.jsx
        ├── index.css
        ├── context/AuthContext.jsx
        ├── lib/                  # api.js, storage.js, formatting, hooks
        ├── components/           # shell, charts, studio, builder widgets
        ├── pages/                # 18 page components
        └── styles/               # tokens.css + page/component styles
```

---

## Tech stack

**Backend**

- Python 3.11 (Docker image), FastAPI 0.115, Uvicorn
- SQLAlchemy 2.0 + psycopg2, Alembic 1.13
- Postgres 16 (local compose) or hosted Neon
- Backtrader 1.9.78 for strategy execution
- pandas / numpy, yfinance for market data
- Groq (OpenAI-compatible API) for the LLM
- pytest 8.4

**Frontend**

- React 19, React DOM 19, react-router-dom 7
- Vite 8 + `@vitejs/plugin-react`
- `lightweight-charts` for price/equity charts
- GSAP + OGL for landing-page animation
- lucide-react icons
- oxlint (no ESLint config)
- Plain CSS with design tokens (`src/styles/tokens.css`), light theme

**Infra**

- Docker Compose: `db` (postgres:16-alpine), `backend`, `frontend` (nginx)
- GitHub Actions CI
- Neon (hosted Postgres), Render (backend), Vercel (frontend) are the
  deployment targets the repo is configured for

---

## Prerequisites

- Python 3.11+
- Node.js 22+ and npm
- Postgres 16 (or a Neon connection string)
- A free [Groq API key](https://console.groq.com) — only chat/builder need it;
  every other feature works without a key
- Optional: Docker Desktop (for the compose stack)

---

## Getting started

### 1. Backend

```powershell
cd backend
python -m venv ..\venv
..\venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# edit backend/.env: set DATABASE_URL and GROQ_API_KEY

..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

On startup the app applies Alembic migrations automatically. Check it:

```powershell
curl http://localhost:8000/health          # {"status":"ok"}
# interactive docs: http://localhost:8000/docs
```

> The repo's `backend/.env` currently points at **Neon**, not the compose
> Postgres. If you want a local database, set
> `DATABASE_URL=postgresql://quant_user:quant_pass@localhost:5432/quant_trading`
> and start the `db` service first.

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Vite proxies `/api/*` to `http://localhost:8000`, stripping the prefix, so local
development never hits CORS.

The login page accepts the fixed local credential:

```
email:    admin@local
password: admin
```

### 3. Docker Compose

```powershell
docker compose up --build
# frontend → http://localhost:3000
# backend  → http://localhost:8000
# postgres → localhost:5432
```

Compose reads `backend/.env` for the backend environment, so the backend will
use whatever `DATABASE_URL` is set there. The compose file also bind-mounts
`D:/QuantCode-Bench` into the backend at `/opt/quantcode-bench`; if that path
does not exist the mount (and therefore `docker compose up`) can fail. See
[QuantCode-Bench integration](#quantcode-bench-integration).

### 4. Useful commands

| Task | Command |
|---|---|
| Backend dev server | `python -m uvicorn app.main:app --reload --port 8000` (from `backend/`) |
| Frontend dev server | `npm run dev` (from `frontend/`) |
| Frontend lint | `npm run lint` |
| Frontend production build | `npm run build` |
| All backend tests | `python -m pytest -q` (from `backend/`) |
| Fast unit subset | `python -m pytest tests/test_guardrails.py tests/test_display.py -q` |
| Apply migrations | `alembic upgrade head` (from `backend/`) |
| New migration | `alembic revision --autogenerate -m "message"` |

---

## Configuration

Settings are defined in `backend/app/config.py` and read from `backend/.env`
(process env wins). **The defaults below are what the code actually uses** —
note the drift against the shipped `.env.example` in the last column.

| Variable | Default in code | Used for | `.env.example` |
|---|---|---|---|
| `DATABASE_URL` | `postgresql://quant_user:quant_pass@localhost:5432/quant_trading` | SQLAlchemy engine | matches |
| `GROQ_API_KEY` | `""` (disabled) | Chat + builder LLM calls | placeholder |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model id | matches |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | OpenAI-compatible endpoint | matches |
| `DEFAULT_MARKET` | `NIFTY50` | Declared but **unused** — NIFTY 50 is fixed in code | matches |
| `MARKET_DATA_REFRESH_DAYS` | `1` | CSV cache staleness | matches |
| `SANDBOX_MEMORY_MB` | `2048` | POSIX address-space cap for the worker | matches |
| `SANDBOX_CPU_SECONDS` | unset | Optional POSIX CPU cap | commented out |
| `APPROVAL_MIN_TRADES` | `10` | Intended approval threshold | **`1` (stale)** |
| `APPROVAL_MAX_DRAWDOWN_PCT` | `50.0` | Intended drawdown cap | matches |
| `ALLOWED_ORIGINS` | `""` (dev origins) | Comma-separated CORS allow-list | not listed |
| `QCB_PATH` | `D:\QuantCode-Bench` (Win) / `/mnt/d/QuantCode-Bench` | QuantCode-Bench root | not listed |
| `AI_QUANT_BACKEND` | this repo's backend dir | QCB `PYTHONPATH` entry | not listed |
| `MARKETAUX_API_KEY` | `""` (disabled) | Optional Marketaux news API key | commented out |
| `FINNHUB_API_KEY` | `""` (disabled) | Optional Finnhub news API key | commented out |
| `ALPHA_VANTAGE_API_KEY` | `""` (disabled) | Optional Alpha Vantage news API key | commented out |
| `NEWS_REFRESH_MINUTES` | `30` | Background refresh cadence | matches |
| `NEWS_RETENTION_DAYS` | `7` | How long articles are kept | matches |
| `NEWS_MAX_ARTICLES` | `3000` | Cap on stored articles | matches |
| `NEWS_ENABLE_REDDIT` | `true` | Enable Reddit sentiment feeds | matches |
| `NEWS_ENABLE_GOOGLE_NEWS` | `true` | Enable Google News RSS index | matches |
| `NEWS_AUTO_REFRESH` | `true` | Run background ingestion task | matches |
| `NEWS_USER_AGENT` | descriptive UA | HTTP User-Agent for feeds | not listed |
| `REDDIT_USER_AGENT` | descriptive UA | Reddit API User-Agent | not listed |

**Known drift:** `DEFAULT_MARKET`, `APPROVAL_MIN_TRADES` and
`APPROVAL_MAX_DRAWDOWN_PCT` are currently **not read** anywhere.
`deployment_gate.py` hardcodes the gate rules (10 trades, 25% drawdown, Sharpe
0.5, win rate 40%), so changing those env vars or the code defaults above has no
effect today. `.env.example` also still ships `APPROVAL_MIN_TRADES=1`.

Unused leftovers still present in local env files (not read by any code):

- `backend/.env`: `SUPABASE_JWT_SECRET`, `SMTP_HOST`, `SMTP_PORT`,
  `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`
- `frontend/.env`: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`

Frontend build-time variables:

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Absolute backend URL for Vercel/Render builds |
| `VITE_API_BASE` | Docker build-arg fallback for the same value |

If neither is set, dev uses `/api` (proxied) and a production build falls back to
`http://localhost:8000`.

---

## API reference

Base URL: `http://localhost:8000`. Interactive schema at `/docs`, raw at
`/openapi.json`. There are **51 routes** including the docs endpoints.

All JSON errors are normalised by `JsonErrorMiddleware`. Gate refusals return
`422` with `{"detail": {"reasons": [...]}}`; malformed UUIDs return `404`.

### Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |

### Chat — `app/routers/chat.py`

| Method | Path | Body / behaviour |
|---|---|---|
| POST | `/chat` | `{conversation_id?, content}` → `{conversation_id, reply, strategy_id?, strategy_name?, strategy_description?}`. Creates a conversation when `conversation_id` is omitted. Requires `GROQ_API_KEY`. |

### Conversations & projects — `app/routers/conversations.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/conversations` | List the caller's conversations |
| POST | `/conversations` | `{title?, project_id?}` |
| GET | `/conversations/{id}` | Conversation with messages |
| PATCH | `/conversations/{id}` | Rename / update |
| DELETE | `/conversations/{id}` | Delete |
| POST | `/conversations/{id}/archive` | Archive |
| POST | `/conversations/{id}/restore` | Restore |
| POST | `/conversations/{id}/move` | `{project_id}` |
| GET | `/conversations/projects` | List projects |
| POST | `/conversations/projects` | `{name, description?}` |
| PATCH | `/conversations/projects/{id}` | Update |
| DELETE | `/conversations/projects/{id}` | Delete |

Ownership is enforced by the fixed local user; a row owned by another identity
404s exactly like a missing one.

### Strategies — `app/routers/strategies.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/strategies/` | List strategies (note the trailing slash — `redirect_slashes=False`) |
| POST | `/strategies/builder` | Structured generation (see [builder](#structured-strategy-builder)) |
| GET | `/strategies/{id}` | Detail + generated code + spec |
| POST | `/strategies/{id}/backtest` | Run sandboxed backtest |
| GET | `/strategies/{id}/backtest-results` | All stored runs, newest first |
| POST | `/strategies/{id}/approve` | Gate evaluation; no body |
| POST | `/strategies/{id}/reject` | `{reason}` |
| POST | `/strategies/{id}/deploy` | `{cash, commission_pct, sizer_percents, slippage_pct?}` |
| POST | `/strategies/{id}/stop` | `{reason?}` |
| GET | `/strategies/{id}/deployments` | Deployment history |
| POST | `/strategies/{id}/paper-tick` | Advance one simulated bar |
| GET | `/strategies/{id}/paper-account` | Virtual account snapshot |
| GET | `/strategies/{id}/paper-positions` | Open positions |
| GET | `/strategies/{id}/paper-orders` | Order ledger |
| GET | `/strategies/{id}/paper-trades` | Closed trades |
| GET | `/strategies/{id}/market-bars` | Processed OHLC bars (read-only) |

**Capital parameters** (`CapitalParams`, shared by backtest/deploy):

| Field | Default | Meaning |
|---|---|---|
| `cash` | `100000` | Starting capital, `> 0` |
| `commission_pct` | `0.1` | Commission per order, **percent** in `(0, 100)` |
| `sizer_percents` | `95.0` | Percent of cash per entry, `(0, 100)` |
| `slippage_pct` | `0.0` | Slippage per order, percent in `[0, 100)` |

`BacktestRequest` adds optional `data_path` (defaults to the cached market CSV).

**Backtest response** (`BacktestResultOut`) includes: `total_return_pct`,
`benchmark_return_pct`, `win_rate_pct`, `max_drawdown_pct`, `num_trades`,
`sharpe`, `sortino`, `cagr_pct`, `profit_factor`, `avg_win`, `avg_loss`,
`avg_trade_pnl`, `expectancy`, `start_date`, `end_date`, `trades`,
`trades_truncated`, `equity_curve`, `drawdown_curve`, `warnings`, `raw_metrics`.

**Paper-tick request** (`PaperTickIn`): `bar_date?` (`YYYY-MM-DD`, must be
exactly the next unprocessed bar) and `deployment_id?` (pins the tick; defaults
to the active deployment). Response (`PaperTickOut`) reports both the strategy's
`signal` (BUY/SELL/HOLD) and the simulated `action`, plus fill price, quantity,
order status, trade id, cash, equity and realised PnL.

### Paper-trading hub — `app/routers/paper.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/paper/deployments` | All deployments with live snapshot numbers |
| GET | `/paper/deployments/active` | Active deployments only |
| GET | `/paper/deployments/{id}/equity-snapshots` | Equity history |

### Market (public) — `app/routers/market.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/market/nifty-live` | Latest 1-minute `^NSEI` bar. Returns **503** when the market is closed or Yahoo is unreachable |
| GET | `/market/nifty-history` | Recent 1-minute bars for the landing-page chart |

These endpoints deliberately require no login; the landing page falls back to a
local simulator when they fail.

### Dashboard / market intelligence — `app/routers/dashboard.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/dashboard/market/overview` | Six Indian indices with quote data |
| GET | `/dashboard/market/quote/{symbol}` | Single symbol quote |
| GET | `/dashboard/market/chart/{symbol}` | Historical chart, multiple timeframes |
| GET | `/dashboard/market/indicators/{symbol}` | Technical indicators |
| GET | `/dashboard/market/pulse` | Gainers / losers / most active |
| GET | `/dashboard/market/news` | Aggregated market news |
| POST | `/dashboard/ai/briefing` | `{mode: concise\|detailed\|explain, force?}`. Falls back to a labelled rule-based briefing when the LLM is unavailable. 120-second in-process cache |
| GET | `/dashboard/simulation` | Monitor over existing paper deployments (recomputes win rate / Sharpe from the ledger; does not run a second engine) |
| GET | `/dashboard/performance/summary` | Aggregate paper performance |
| GET | `/dashboard/strategies` | Strategy counts/status for the dashboard |
| GET | `/dashboard/paper/portfolio` | Aggregated paper portfolio |
| GET | `/dashboard/activity/recent` | Recent activity feed |

No dashboard endpoint invents a price: when Yahoo has no usable row the caller
gets an explicit `unavailable`/empty result.

### Market News Hub — `app/routers/news.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/news/` | List stored articles. Filters: `region`, `category`, `source_type`, `content_type`, `sentiment`, `ticker`, `q`, `min_credibility`, `hours`, `sort`, `limit`, `offset`. Read-only; never triggers ingestion. Trailing slash required |
| GET | `/news/overview` | Hub header: counts (total, high impact, official, community), top stories, sentiment, freshness |
| GET | `/news/trending` | Most-mentioned tickers with mention momentum vs prior window |
| GET | `/news/sentiment` | Aggregate sentiment, split for official vs community sources |
| GET | `/news/sources` | Source registry, credibility scale and the credentials still needed |
| GET | `/news/sources/{key}` | One source's registry entry |
| POST | `/news/refresh` | Run one ingestion pass over enabled providers (`force`, optional `providers` list) |

**Data rules:** only headlines, short source snippets and links are stored —
never full article text or publisher images. `is_verified` is true only for
official/primary sources; publisher and newswire articles are reported, not
independently verified. Community (Reddit) posts are sentiment signals, never
verified news. Sentiment is a deterministic lexicon unless a keyed provider
supplies its own score; the method is stored on every article.

---

## Strategy lifecycle

```
                 POST /strategies/builder
                 (or chat + extract)
                          │
                          ▼
                       ┌───────┐   POST /backtest    ┌────────────┐
                       │ draft │ ──────────────────► │ backtested │
                       └───────┘                     └────┬───────┘
                            │                             │
             POST /reject   │                 POST /approve (quality gate)
                            ▼                             ▼
                       ┌──────────┐                  ┌──────────┐
                       │ rejected │                  │ approved │
                       └──────────┘                  └────┬─────┘
                                                          │ POST /deploy
                                                          ▼
                                                   ┌───────────────┐
                                                   │ paper_trading │
                                                   └───────┬───────┘
                                                           │ POST /stop
                                                           ▼
                                                     back to approved
```

### Approval gate (`services/deployment_gate.py`)

`check_approval` returns a list of human-readable blocking reasons; empty means
allowed. Rules are **hardcoded**:

1. Strategy status must be `backtested`.
2. A latest backtest must exist.
3. **At least 10 closed trades.**
4. At least **2 of 4** criteria must pass:
   - max drawdown `< 25%`
   - at least 10 closed trades
   - Sharpe `> 0.5`
   - win rate `> 40%`

On success the passing backtest id is stored in `strategies.approved_backtest_id`
so approval is tied to a specific run.

### Deploy / stop

- `check_deploy` re-validates status (`approved`), re-runs the **AST guardrails**
  against the current code, and refuses a second active deployment.
- Deploying creates a `paper_deployments` row whose virtual account starts with
  the full requested cash, zero PnL, no processed bar.
- Stopping marks the deployment `stopped`, stores the reason, and returns the
  strategy to `approved`. Strategy status notes are cleared on gate transitions.

---

## Chat and strategy extraction

`services/llm_service.py` calls Groq's OpenAI-compatible chat endpoint using
`httpx`. The system prompt tells the model to:

1. Ask clarifying questions while the request is vague.
2. Emit a strict, machine-parseable block once the strategy is fully defined —
   no disclaimers, headers, or install instructions.

`services/strategy_extractor.py` then:

- detects a final strategy (`looks_like_final_strategy`),
- extracts the code fence and metadata (`extract_strategy`),
- cleans the reply for display (`clean_reply_for_display`),
- collapses free-form code blocks to placeholders so partial attempts never get
  mistaken for a finished strategy.

`services/finalize_service.py` persists the parsed strategy, name and
description, and links it to the conversation. Missing credentials raise
`LLMNotConfiguredError`, which routers map to **503** with an actionable message
(never echoing the key).

---

## Structured strategy builder

`POST /strategies/builder` accepts a fully validated `StrategyBuilderRequest`:

```json
{
  "market": "NIFTY50",
  "trading_style": "swing",
  "timeframe": "1d",
  "indicators": [
    { "name": "RSI", "parameters": { "period": 14 } },
    { "name": "EMA", "parameters": { "period": 50 } }
  ],
  "entry_conditions": ["RSI crosses below 30 and price is above EMA50"],
  "exit_conditions": ["RSI crosses above 70"],
  "risk_management": {
    "stop_loss_percent": 2,
    "take_profit_percent": 6,
    "trailing_stop_percent": null,
    "max_trades_per_day": 2
  }
}
```

Validation enforced by `schemas.py`:

| Field | Allowed |
|---|---|
| `market` | `NIFTY50`, `BANKNIFTY`, `SENSEX`, `OTHER` — but only `NIFTY50` passes the data check |
| `trading_style` | `scalping`, `intraday`, `swing`, `positional` |
| `timeframe` | `5m`, `15m`, `30m`, `1h`, `1d` |
| style → timeframe | scalping `5m/15m`; intraday `5m/15m/30m/1h`; swing `1h/1d`; positional `1d` |
| indicators | `EMA`, `SMA`, `RSI`, `MACD`, `Bollinger Bands`, `Volume` (flexible spellings fold to canonical names; duplicates rejected) |
| conditions | at least one non-empty entry and exit condition |

`services/strategy_builder.py` builds a controlled prompt, calls the LLM, then
runs static code checks (`validate_generated_code`): required
`import backtrader as bt`, `class GeneratedStrategy`, `def next`, buy/sell calls,
position checks, and forbidden APIs (slippage overrides, bracket orders, manual
`size` on `buy()` with risk params, signal-bar close assignment). Errors are
returned as `422 {"detail": {"errors": [...]}}`; warnings are surfaced but do
not block.

The generated strategy is stored as a normal `Strategy` row in the caller's
`Strategy Builder` conversation, so the backtest/approval/deploy pipeline is
identical to the chat path.

---

## Backtest pipeline

1. **Resolve data.** `market_data.ensure_market_data("NIFTY50")` downloads 2
   years of daily `^NSEI` OHLCV from Yahoo via yfinance and caches
   `backend/data/NIFTY50.csv`. The cache is refreshed only when older than
   `MARKET_DATA_REFRESH_DAYS`.
2. **Guardrails.** `strategy_runner.check_guardrails(code)` parses the code with
   `ast` and refuses:
   - imports outside `backtrader`, `pandas`, `numpy`, `math`, `datetime`
   - calls to `exec`, `eval`, `open`, `input`, `compile`, `globals`, `locals`,
     `vars`, `breakpoint`, `getattr`, `setattr`, `delattr`, `__import__`
   - escape-hatch dunder attributes/names (`__class__`, `__subclasses__`,
     `__globals__`, `__builtins__`, `__reduce__`, …)
3. **Isolated worker.** `backtest_service.run_backtest_sandboxed` spawns
   `python strategy_runner.py` as a subprocess (launched as a file, not `-m`, so
   package imports cannot swallow startup failures). The strategy code goes in
   on **stdin**; paths and numeric knobs go in argv. A wall-clock timeout
   (`TIMEOUT_DEFAULT_SECONDS = 120`) kills the whole process tree. On POSIX the
   worker also gets `RLIMIT_AS` (`SANDBOX_MEMORY_MB`) and optional `RLIMIT_CPU`.
4. **Execute.** Backtrader runs the strategy with a `PercentSizer`, commission
   and slippage converted from percentages to fractions. Analyzers:
   Sharpe, Sortino, DrawDown, TradeAnalyzer, Returns, TimeReturn and a custom
   `ClosedTradeCollector`. Missing analyzers degrade gracefully.
5. **Collect.** The worker prints one sentinel line
   `__BT_RESULT__ {json}`. The parent parses it, derives CAGR, sanitises
   NaN/inf to `null`, caps the equity curve at 400 points, and truncates trades
   with a `trades_truncated` count and `no_trades` warning.
6. **Persist.** A `BacktestResult` row stores the headline metrics and the full
   JSON payload; the strategy becomes `backtested`.
7. **Optional QCB.** A best-effort background evaluation is enqueued (log-only;
   never affects the response).

Failure mapping: timeout → `504`; `BacktestError`/worker failure → `422`;
missing market data → `503`; unexpected errors → `400`/`500`.

---

## Paper-trading engine

`services/paper_engine.py` is a deterministic **simulator**, not a broker
client.

- Each `paper-tick` advances **one** cached NIFTY bar (the oldest unprocessed
  one, unless an exact `bar_date` is supplied; skips are rejected).
- It replays the **deployment's own generated code** over the slice
  `[first bar .. current bar]` in the same sandboxed worker used by backtests,
  then reads the end-of-slice broker position as the signal.
- Execution rules: long-only, integer quantities, no leverage/margin/shorting,
  one open position per deployment/symbol, commission on every fill, fill price
  always the processed bar's **close**.
- `HOLD` creates no order, trade or chart marker. Rejected orders are stored as
  rejected and never rendered as fills.
- Every processed bar appends/updates one **idempotent**
  `paper_equity_snapshots` row (`UNIQUE(deployment_id, bar_date)`).
- `paper_bars.load_bars` and the chart read the **same** CSV; nothing there
  downloads or fabricates a bar.

No scheduler exists: paper trading advances only when someone calls the tick
endpoint. The virtual account lives in `paper_deployments` plus the ledger
tables; `GET /strategies/{id}/paper-account` is the authoritative snapshot the
UI displays verbatim.

---

## Market intelligence (dashboard)

`services/market_data_extended.py` powers the dashboard with data from Yahoo
Finance and public NSE/index sources:

- six Indian indices (NIFTY 50, BANK NIFTY, SENSEX, FINNIFTY, INDIA VIX, NIFTY IT)
- intraday/daily chart series for multiple timeframes
- top gainers / losers / most active over a fixed, documented universe
- sector performance from real NSE sector indices
- market breadth
- market news aggregation
- technical indicators

There is a small in-process TTL cache so concurrent dashboard sections do not
hammer the upstream provider. Failures return explicit `unavailable`/empty
shapes rather than invented numbers. The AI briefing merges LLM narrative with
rule-derived facts and caches each mode for 120 seconds; without an LLM key it
returns a clearly labelled rule-based briefing.

## Market News Hub

The News Hub (`/news`) aggregates market news from Indian, US, China, Europe
and Japan sources plus Reddit community sentiment, with a credibility-aware
classification layer.

**Source groups**
- Indian publishers: Moneycontrol, Economic Times, Mint, CNBC-TV18, Business
  Standard, Financial Express, BusinessLine, NDTV Profit, ET Now, Zee Business,
  BQ Prime, Business Today, Zerodha Pulse
- Official Indian sources: NSE, BSE, SEBI, RBI, Ministry of Finance, PIB,
  NITI Aayog, AMFI, Union Budget (credibility 5 / verified)
- US / Wall Street: Reuters, Bloomberg, AP, CNBC, WSJ, MarketWatch, Barron's,
  FT (newswire credibility 4; publisher credibility 3)
- US official: Federal Reserve, SEC, Nasdaq, NYSE, Treasury, BLS, BEA
- China: Xinhua, China Daily, PBOC, SSE, SZSE
- Europe: ECB, Euronext, Deutsche Börse, Bank of England, European Commission,
  LSE
- Japan / APAC: Nikkei, Nikkei Asia, JPX, MAS, ASX, HKEX
- Other intelligence: CoinDesk, Cointelegraph, Decrypt, Investing.com, Yahoo
  Finance, Seeking Alpha, TradingView, Kobeissi Letter, Glassnode, Kitco,
  OilPrice
- Community: Reddit (IndianStockMarket, IndiaInvestments, IndianStreetBets,
  NSEbets, WallStreetBets, stocks, investing, SecurityAnalysis, options,
  StockMarket, Forex, CryptoCurrency)

**Ingestion** (keyless by default)
- Google News RSS `site:` queries over publisher and official domains
- Direct official RSS/Atom feeds (RBI, PIB, Federal Reserve, SEC, BLS, ECB)
- Reddit public JSON (sentiment only)
- Optional free API keys: Marketaux, Finnhub, Alpha Vantage — report what's
  still needed via `GET /news/sources`

**Credibility scale** (assigned by the local taxonomy, never by a provider)
- 5 Official / primary — verified fact
- 4 Newswire — reported, not independently verified
- 3 Established publisher — reported, not independently verified
- 2 Aggregator / secondary
- 1 Community / unverified — speculation only

**What is stored:** headline, short source snippet, source URL, timestamp and
classification metadata. Full article text and publisher images are never
copied. AI summaries are never shown; every snippet is the source's own text.

**API:** `GET /news/` (filtered list), `GET /news/overview`, `GET /news/trending`,
`GET /news/sentiment`, `GET /news/sources`, `POST /news/refresh`. See the
[API reference](#market-news-hub---approutersnews-py) for the full contract.

Credentials needed for optional providers are listed by `GET /news/sources` and
documented in [Configuration](#configuration) under `MARKETAUX_API_KEY`,
`FINNHUB_API_KEY` and `ALPHA_VANTAGE_API_KEY`. Check each provider's
redistribution terms before commercial display.

---

## Sandbox and security model

What the sandbox **does** protect against:

- arbitrary imports outside the allow-list
- `exec`/`eval`/file/network primitives
- Python class-hierarchy escape hatches
- runaway runtime (wall-clock timeout + process-tree kill)
- memory blow-ups (POSIX `RLIMIT_AS`, default 2048 MB)

What it **does not** do:

- provide authentication or authorization (see below)
- run the worker as a non-root user in Docker
- isolate the filesystem/network at the OS level (no container/seccomp per
  backtest)

> ⚠️ **No API authentication.** `app/auth.py` returns a fixed local identity
> (`dev@local`, id `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`) for every request.
> The frontend's `admin@local` / `admin` login is client-side only and stores a
> `localStorage` flag. Anyone who can reach the API can read and write all data.
> Do not expose this service publicly without adding real auth.

Ownership checks still exist relative to the fixed identity, so rows created
under a different id do not leak into the current user's lists.

---

## QuantCode-Bench integration

After every successful backtest, `strategies.py` maps the strategy to a
QuantCode-Bench `task_info` (`qcb_mapper.py`) and enqueues
`evaluate_strategy(...)` (`qcb_evaluator.py`) as a FastAPI background task.

- The evaluator runs in an isolated subprocess with a per-evaluation temp
  directory, a timeout, and process-tree termination (Windows Job Objects on
  Windows, `os.killpg` on POSIX).
- Results are **only logged**. They are not persisted or shown in the UI.
- Location is resolved from `QCB_PATH` (defaults: `D:\QuantCode-Bench` on
  Windows, `/mnt/d/QuantCode-Bench` on Linux) and `AI_QUANT_BACKEND` supplies
  this repo on `PYTHONPATH`.
- If the path is missing, the evaluator logs a warning and the backtest response
  is unaffected.

`docker-compose.yml` bind-mounts `D:/QuantCode-Bench` to
`/opt/quantcode-bench`. That directory is not part of this repository; if it is
absent, remove or fix the mount before using compose.

---

## Database and migrations

Postgres 16 (or Neon). Alembic owns the schema; the app never calls
`create_all` in production (only the test harness does).

**12 tables**

| Table | Purpose |
|---|---|
| `users` | Single local identity (kept for FK integrity) |
| `projects` | Grouping for conversations |
| `conversations` | Chat threads, status, timestamps |
| `messages` | User/assistant turns |
| `strategies` | Name, description, code, spec, status, status note, approved backtest id |
| `backtest_results` | Metrics + full JSON payload per run |
| `paper_deployments` | Virtual account and deployment lifecycle |
| `paper_positions` | Open positions |
| `paper_orders` | Every simulated order (filled/rejected) |
| `paper_trades` | Closed round-trips with net PnL |
| `paper_equity_snapshots` | Equity history for charts |
| `news_articles` | Market News Hub feed: headline, snippet, link, credibility |

**Migrations:** 10 revisions, single head `d5e6f7a8b9c0`. The latest revision
adds the `news_articles` table on top of the previous 9.

```powershell
cd backend
alembic upgrade head          # apply
alembic current               # expected head: d5e6f7a8b9c0
alembic downgrade -1          # one step back
```

`docker-compose.yml` starts Postgres with `quant_user` / `quant_pass` /
`quant_trading`; CI uses the same credentials in a service container. A Neon
connection string must include `sslmode=require` if your project requires TLS.

---

## Frontend guide

### Routes (`src/App.jsx`)

| Route | Page | Access |
|---|---|---|
| `/` | Landing page (public marketing + simulated live chart) | public |
| `/welcome` | Redirect to `/` | public |
| `/login` | Cosmetic login (`admin@local` / `admin`) | public |
| `/studio` | AI Strategy Studio with conversation sidebar | public |
| `/chat` | Alias of the Studio | guarded |
| `/strategies` | Strategy library | public |
| `/studio/builder` | Structured strategy builder | guarded |
| `/strategies/:id` | Strategy overview | guarded |
| `/strategies/:id/backtest` | Backtest runner + charts | guarded |
| `/strategies/:id/approval` | Gate criteria and decision | guarded |
| `/strategies/:id/deployment` | Paper-trading account and tick controls | guarded |
| `/backtests` | Backtest hub | guarded |
| `/analytics` | Analytics over stored runs | guarded |
| `/paper-trading` | Paper-trading hub | guarded |
| `/dashboard` | Market terminal | guarded |
| `/news` | Market News Hub: multi-source feed, filters, sentiment, trending tickers | guarded |
| `/settings` | Local preferences and system info | guarded |
| `/docs` | In-app documentation | guarded |
| `*` | Not found | guarded |

"Guarded" means `<ProtectedRoute>` checks the `localStorage` login flag — a
convenience guard, **not** security.

### Data flow

- `src/lib/api.js` is the single API client; every shape is taken from the
  backend schemas.
- Dev requests go to `/api` and are proxied by Vite; production calls the
  absolute URL from `VITE_API_BASE_URL` / `VITE_API_BASE`.
- Charts use `lightweight-charts` (price, equity, drawdown, paper trade markers).
- `AuthContext` keeps the fake login flag and display name in `localStorage`.
- `storage.js` scopes cached strategy/UI data to the local user key.

### Styling

Light theme with CSS custom properties in `src/styles/tokens.css` (lavender
surface, dark text), plus page/component stylesheets (`landing-page.css`,
`pages.css`, `components.css`, `sidebar.css`, `auth.css`). There is no CSS
framework and no Tailwind.

### Build notes

`npm run build` currently emits a **single ~772 kB JS chunk** (230 kB gzipped)
and warns about chunk size and an ineffective dynamic import in
`src/lib/storage.js`. Lint is oxlint; `npm run lint` passes with five warnings
(unused vars in `toast.js`, fast-refresh export in `AuthContext.jsx`, two
`exhaustive-deps` warnings).

---

## Testing

```powershell
cd backend
..\venv\Scripts\python.exe -m pytest -q
```

Current status: **337 checks — 331 passed, 6 skipped, 0 failed.**

The 6 skips are Linux-only QCB process-group cleanup tests that do not apply on
Windows.

### Timing reality

The suite is **not** fast when it points at a hosted database. DB-backed modules
round-trip to Neon for every test:

| Module | Result | Wall time |
|---|---|---|
| `test_deployment_gate.py` | 26 passed | 7m 46s |
| `test_conversations.py` | 24 passed | 2m 58s |
| `test_llm_credentials.py` | 22 passed | 2m 38s |
| `test_backtest_api.py` | 8 passed | 2m 06s |
| `test_builder_integration.py` | 9 passed | 1m 49s |
| `test_id_validation.py` | 56 passed | 1m 26s |
| `test_migration_conversations_updated_at.py` | 4 passed | 1m 00s |
| `test_approval_gate_new.py` | 10 passed | 58s |
| `test_paper_trading.py` | 35 passed | 8.4s |
| `test_paper_equity_snapshots.py` | 9 passed | 8.8s |
| `test_runner.py` | 24 passed | 4.6s |
| `test_backtest_service.py` | 18 passed | 2.6s |
| `test_qcb_integration.py` | 11 passed, 6 skipped | 1.2s |
| `test_guardrails.py` | 15 passed | 1.1s |
| `test_display.py` | 5 passed | 1.1s |
| `test_strategy_builder_unit.py` | 29 passed | 1.1s |
| `test_error_handling.py` | 4 passed | 1.2s |
| `test_dashboard_market.py` | 16 passed | 1.2s |
| `test_dashboard_api.py` | 6 passed | 1.2s |

Total observed runtime: roughly **19 minutes** against hosted Neon. Pure-logic
modules (`guardrails`, `display`, `runner`, `paper_trading`) finish in seconds.

### Important caveat: tests are not hermetic

`backend/tests/conftest.py` calls `Base.metadata.create_all()` against the
database in `backend/.env` and deletes the rows it added during teardown. If
`backend/.env` points at a hosted Neon database, local test runs **write to and
clean up a real shared database** and are dominated by network latency. CI does
this correctly (local Postgres service), so local and CI behaviour differ. Point
`DATABASE_URL` at a disposable local database for fast, safe runs.

Test fixtures live in `backend/tests/fixtures/` (strategy files plus a 740-row
`nifty50.csv`).

---

## CI

`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests.

**Backend job**

1. Starts a `postgres:16-alpine` service with the compose credentials.
2. Adds a 4 GB swapfile (the backtest worker needs memory headroom).
3. Installs Python 3.11 dependencies from `backend/requirements.txt`.
4. Runs `alembic upgrade head` to prove migrations apply cleanly.
5. Runs `python -m pytest -q`.

**Frontend job**

1. Node 22, `npm ci`.
2. `npm run lint`.
3. `npm run build`.

---

## Deployment

The repository is wired for **Neon + Render + Vercel**, with Docker Compose as
the local/self-hosted option.

### Neon (database)

1. Create a Neon project and copy the direct connection string.
2. Set it as `DATABASE_URL` in `backend/.env` (local) or the Render service env.
3. The app migrates automatically on startup; `alembic upgrade head` also works
   manually.

### Render (backend)

- Build: `pip install -r requirements.txt` (root directory `backend`)
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Env: `DATABASE_URL`, `GROQ_API_KEY`, `GROQ_MODEL`, `ALLOWED_ORIGINS`
  (comma-separated frontend origins, e.g. `https://your-app.vercel.app`), plus
  `SANDBOX_MEMORY_MB=2048` if the instance is memory-constrained.

### Vercel (frontend)

- Root directory `frontend`; `vercel.json` rewrites all paths to `/` so the SPA
  router works on refresh.
- Set `VITE_API_BASE_URL` to the Render URL at build time.

### Docker Compose (self-hosted)

```powershell
docker compose up --build
```

- `db` → Postgres 16 with a named volume and healthcheck.
- `backend` → built from `backend/Dockerfile`, reads `backend/.env`, exposes
  `8000`, and bind-mounts `D:/QuantCode-Bench` read-only.
- `frontend` → multi-stage build served by nginx on port `3000`, with
  `VITE_API_BASE` / `VITE_API_BASE_URL` passed as build args.

Caveats: the backend container runs as **root** (no `USER` in the Dockerfile),
and the QCB bind mount requires `D:/QuantCode-Bench` to exist on the host.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Chat returns `503` "LLM not configured" | `GROQ_API_KEY` is empty. Add a key to `backend/.env` and restart. |
| Backtest returns `503` "Could not load market data" | Yahoo unreachable and no cached CSV. Check `backend/data/NIFTY50.csv` / network. |
| Backtest returns `422` | Guardrail refusal or the strategy has no generated code. Read `detail`. |
| Backtest returns `504` | The worker exceeded its 120 s timeout. Simplify the strategy or raise the limit in `strategy_runner.py`. |
| Worker dies with "failed to map segment from shared object" | `SANDBOX_MEMORY_MB` is below the ~1.5 GB needed just to import pandas/numpy/backtrader. Keep it at 2048+. |
| Approval returns `422` with reasons | Expected gate refusal. The reasons list every failed criterion. |
| Paper tick returns `422` | `bar_date` was not exactly the next unprocessed bar, or no active deployment exists. |
| Frontend gets CORS errors | Add the frontend origin to `ALLOWED_ORIGINS` (or use the Vite proxy in dev). |
| `docker compose up` fails on the backend volume | `D:/QuantCode-Bench` does not exist. Remove the bind mount or create the directory. |
| `alembic` fails on startup after 10 retries | Database unreachable or migrations diverged. Check `DATABASE_URL`, then run `alembic current` / `alembic upgrade head` manually. |
| Tests are extremely slow | They are talking to hosted Neon. Point `DATABASE_URL` at a local Postgres. |
| `GET /strategies` 404s | Use `/strategies/` — the app runs with `redirect_slashes=False`. |

---

## Roadmap and known gaps

Verified gaps in the current tree (roughly in priority order):

1. **No real authentication.** The API is open; the fixed `dev@local` identity
   and the cosmetic `admin@local` / `admin` login provide no protection. Add
   real auth (and real per-user ownership) before any public deployment.
2. **Tests are not isolated.** `conftest.py` creates tables and cleans rows on
   whatever `DATABASE_URL` points at; with the shipped env that is hosted Neon.
   Use a disposable database and gate the fixtures behind it.
3. **The backend container runs as root**, contradicting the security posture
   of the sandbox. Add a non-root `USER` and drop capabilities.
4. **QuantCode-Bench is effectively dead code.** `D:\QuantCode-Bench` does not
   exist here; the compose bind mount points at a missing path; evaluation is
   log-only and never persisted or displayed. Either wire it up properly or
   remove the hook and mount.
5. **Approval thresholds are hardcoded.** `APPROVAL_MIN_TRADES` /
   `APPROVAL_MAX_DRAWDOWN_PCT` are configuration dead ends, and
   `.env.example` still ships the stale `APPROVAL_MIN_TRADES=1`.
6. **No scheduler for paper trading.** Ticks only happen when a user clicks.
   A real loop needs a worker/cron and idempotency guarantees.
7. **Market coverage is NIFTY 50 only.** `BANKNIFTY`, `SENSEX` and `OTHER` are
   accepted by the enum but rejected by the data validator.
8. **Frontend test coverage is zero.** There is lint + build in CI, no unit or
   E2E tests.
9. **Bundle size.** One ~772 kB chunk; route-level code splitting is not set up.
10. **Repository hygiene.** Stale `__pycache__` entries for deleted tests
    (`test_welcome_email`, `test_user_isolation`), a stray
    `backend/node_modules` + `.package-lock.json`, an unused `openai`
    dependency, and unused Supabase/SMTP env vars in local `.env` files.
11. **Analytics page is read-only.** It renders cached backtest runs and
    recalculates nothing.

---

**Status:** backend imports cleanly (51 routes), frontend lints and builds,
migrations apply, and all 337 collected checks pass (6 environment skips). The
main work left is authentication, test isolation, container hardening, and
deciding what to do with the QCB hook.
