# AI Conversational Quant Trading App

Chat with an AI, get a NIFTY 50 trading strategy generated, backtested, reviewed
through an approval gate, and recorded as a paper-trading deployment.

> ⚠️ **Educational prototype — paper trading only.** Nothing here places real
> orders, and past backtest performance does not predict future results.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Strategy lifecycle](#strategy-lifecycle)
- [Chat and strategy extraction](#chat-and-strategy-extraction)
- [Backtest pipeline](#backtest-pipeline)
- [Sandbox and security model](#sandbox-and-security-model)
- [Database and migrations](#database-and-migrations)
- [Frontend guide](#frontend-guide)
- [Testing](#testing)
- [CI](#ci)
- [Docker deployment](#docker-deployment)
- [Troubleshooting](#troubleshooting)
- [Roadmap and known gaps](#roadmap-and-known-gaps)

## Features

- **Conversational strategy design** — describe a strategy in plain language; the
  assistant asks clarifying questions until the idea is concrete, then produces a
  Backtrader strategy class.
- **Structured extraction** — a second, schema-constrained LLM call (with a regex
  fallback) turns free-form replies into clean `{name, description, code}` rows.
- **One-click backtests** — market data auto-downloads from Yahoo Finance and is
  cached locally; AI code executes in an isolated subprocess behind AST guardrails.
- **Full results surface** — return vs. buy & hold, CAGR, Sharpe, Sortino, max
  drawdown, win rate, profit factor, an SVG equity curve, and a per-trade table.
- **Paper-trading gate** — approve / reject / deploy / stop workflow with quality
  thresholds, guardrail re-validation, and a newest-first deployment audit trail.
- **76 collected backend checks, CI on every push** — guardrails, runner, worker
  CLI, orchestrator, API endpoints, gate transitions, and reply cleaning.

## Architecture

```
┌──────────────┐      ┌─────────────────────────────┐      ┌────────────┐
│  React chat  │─────▶│  FastAPI backend            │─────▶│  Postgres  │
│  (Vite)      │◀─────│  /chat  /strategies  /health │◀─────│  6 tables  │
└──────────────┘      └──────────────┬──────────────┘      └────────────┘
                                     │ spawns (stdin code in,
                                     │ sentinel JSON out)
                                     ▼
                              ┌──────────────┐     ┌──────────────┐
                              │  Backtest    │────▶│ Yahoo Finance│
                              │  worker      │     │ (CSV cache)  │
                              └──────────────┘     └──────────────┘
                                     ▲
                                     │ chat + finalize calls
                              ┌──────────────┐
                              │  Groq LLM    │
                              └──────────────┘
```

Two flows matter:

**Chat flow** (`app/routers/chat.py`): receive message → store in Postgres → call
LLM with history → store reply → detect a finished strategy → run the constrained
finalize call (or regex fallback) → persist a `strategies` row → return the reply
plus `strategy_id`/`strategy_name`/`strategy_description`. The model is only the
"brain"; the controller owns the workflow, so swapping providers means touching
only `app/config.py` and `app/services/llm_service.py`.

**Backtest flow** (`POST /strategies/{id}/backtest`): load `generated_code` →
ensure market data → spawn the worker subprocess with code on stdin → enforce the
timeout and output cap → parse the `__BT_RESULT__` sentinel line → compute CAGR in
the parent → persist a `backtest_results` row and flip the strategy to `backtested`.

## Project structure

```
Ai_Quant/
├── backend/
│   ├── alembic.ini                  # Alembic config (URL overridden from settings)
│   ├── alembic/
│   │   ├── env.py                   # wires Base.metadata + DATABASE_URL
│   │   └── versions/
│   │       ├── 2ee9e2c6346e_initial_schema.py
│   │       └── 8333ffdaacba_paper_deployments_and_status_notes.py
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, lifespan runs migrations
│   │   ├── config.py                # pydantic-settings (see Configuration)
│   │   ├── database.py              # engine / SessionLocal / Base / get_db
│   │   ├── schemas.py               # Pydantic request/response models
│   │   ├── models/
│   │   │   └── db_models.py         # User, Conversation, Message, Strategy,
│   │   │                            # BacktestResult, PaperDeployment + enums
│   │   ├── routers/
│   │   │   ├── chat.py              # POST /chat (7-step workflow)
│   │   │   └── strategies.py        # detail, backtest, approve/reject/deploy/stop
│   │   └── services/
│   │       ├── llm_service.py       # SYSTEM_PROMPT + Groq chat_completion()
│   │       ├── finalize_service.py  # narrow json_schema extraction call
│   │       ├── strategy_extractor.py# looks_like_final_strategy, extract_strategy,
│   │       │                        # clean_reply_for_display
│   │       ├── market_data.py       # yfinance download + CSV cache + offline reuse
│   │       ├── strategy_runner.py   # worker: guardrails, Backtrader run, metrics
│   │       ├── backtest_service.py  # orchestrator: spawn, timeout, tree-kill, CAGR
│   │       └── deployment_gate.py   # pure approve/deploy transition rules
│   ├── tests/
│   │   ├── conftest.py              # db_reachable() probe
│   │   ├── fixtures/                # buy_hold, alternating, swing_churn,
│   │   │                            # rsi_meanrev, probe_trades + nifty50.csv
│   │   │                            # (740 real OHLCV rows for offline tests)
│   │   ├── test_guardrails.py       # 12 escape-hatch rejections
│   │   ├── test_runner.py           # metrics, Sortino, trades, equity curve
│   │   ├── test_worker_cli.py       # sentinel protocol, timeouts, tree-kill
│   │   ├── test_backtest_api.py     # endpoint incl. 404/422 paths (needs Postgres)
│   │   ├── test_deployment_gate.py  # lifecycle transitions (needs Postgres)
│   │   └── test_display.py          # reply cleaning (no DB)
│   ├── Dockerfile                   # python:3.11-slim + uvicorn
│   ├── pytest.ini                   # testpaths=., pythonpath=.
│   └── requirements.txt
├── frontend/
│   ├── Dockerfile                   # node build → nginx serve
│   ├── src/
│   │   ├── main.jsx                 # createRoot entry
│   │   ├── App.jsx                  # chat + StrategyCard (metrics, equity chart,
│   │   │                            # trade table, code viewer, gate buttons)
│   │   ├── App.css / index.css      # hand-written dark theme
│   └── package.json                 # react 19, vite 8, oxlint
├── docker-compose.yml               # db + backend + frontend
├── .github/workflows/ci.yml         # backend pytest + frontend lint/build
└── test_prompt.txt                  # manual QA script for the chat flow
```

## Tech stack

| Layer | Choice | Notes |
| --- | --- | --- |
| UI | React 19.2, Vite 8.2, oxlint | Single-component chat, no router/state lib |
| API | FastAPI 0.115, uvicorn 0.30.6 | Lifespan handler runs migrations on startup |
| ORM / migrations | SQLAlchemy 2.0.35, Alembic 1.13.2 | psycopg2-binary driver |
| LLM | Groq OpenAI-compatible API (`httpx`, no SDK) | Default `openai/gpt-oss-120b`; `json_schema` response mode for extraction |
| Market data | yfinance 1.7.0 | NIFTY 50 (`^NSEI`), 2y daily, CSV cache |
| Backtests | backtrader 1.9.78.123, pandas 2.2.2, numpy 1.26.4 | Worker subprocess + AST guardrails |
| DB | Postgres 16 (Docker) | 6 tables; tests use the same engine |
| Tests | pytest 8.4.2 | 76 collected; DB-backed modules self-skip offline |
| Deploy | Docker Compose (db, backend, nginx frontend) | GitHub Actions CI on push/PR |

Python is 3.11 in Docker and 3.11 in CI; the local venv may differ — the code
targets 3.10+ syntax only.

## Prerequisites

- Python 3.11+ and `pip`
- Node 20+ and `npm` (22 used in Docker/CI)
- Docker Desktop (for Postgres, and for the full-stack compose)
- A free Groq API key: https://console.groq.com

## Getting started

### 1. Backend (local dev)

```bash
cd backend
cp .env.example .env        # then paste your GROQ_API_KEY into .env
cd .. && docker compose up -d db      # Postgres only, from the repo root
cd backend
python -m venv venv && venv\Scripts\Activate     # Windows (POSIX: source venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs at http://localhost:8000 — health check: `GET /health`.
On startup it applies pending Alembic migrations (`upgrade head`).

### 2. Frontend (local dev)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:5173 and calls the backend at `:8000`.
Point it elsewhere at build time with `VITE_API_BASE`
(e.g. `VITE_API_BASE=https://api.example.com npm run build`).

### 3. Full stack via Docker

```bash
docker compose up --build
```

Services: Postgres `:5432`, backend `:8000`, nginx frontend `:3000`.
**Important:** don't run a local `uvicorn` at the same time — both bind port
8000 and only one will receive your requests. Run `docker compose down` before
rebuilding after code changes so containers pick up fresh edits. To run only the
database locally: `docker compose up -d db`.

## Configuration

All settings live in `backend/app/config.py` (pydantic-settings) and can be set
via environment or `backend/.env` — copy `backend/.env.example` to start:

| Variable | Default | What it does |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://quant_user:quant_pass@localhost:5432/quant_trading` | Postgres connection. Compose overrides it to host `db` for the backend container |
| `GROQ_API_KEY` | *(empty)* | Required for `/chat`; without it chat calls fail |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Any model id Groq serves |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Swap providers by changing this + `llm_service.py` |
| `DEFAULT_MARKET` | `NIFTY50` | Only wired market; maps to `^NSEI` in `MARKET_TICKERS` |
| `MARKET_DATA_REFRESH_DAYS` | `1` | Days a cached `backend/data/{MARKET}.csv` stays fresh before re-download |
| `SANDBOX_MEMORY_MB` | `1024` | Worker address-space cap, **POSIX only** (no Windows equivalent) |
| `SANDBOX_CPU_SECONDS` | *(unset)* | Optional worker CPU-time cap, POSIX only |
| `APPROVAL_MIN_TRADES` | `1` | Minimum closed trades for the approval gate |
| `APPROVAL_MAX_DRAWDOWN_PCT` | `50.0` | Drawdown cap (%) for the approval gate |

Frontend build arg: `VITE_API_BASE` (default `http://localhost:8000`).

## API reference

Base URL `http://localhost:8000`. Interactive docs at `/docs` (Swagger UI).

### `POST /chat`

Send a message; get the assistant reply plus any strategy it produced.

```jsonc
// request
{ "conversation_id": null, "content": "medium-risk NIFTY 50 strategy, hold 2-5 days" }
// response
{
  "conversation_id": "…",
  "reply": "…",                       // display-cleaned (no STRATEGY_READY/code dumps)
  "strategy_id": "…",                 // null until a strategy is finalized
  "strategy_name": "…",
  "strategy_description": "…"
}
```

Pass `conversation_id` back on the next turn to keep memory. Unknown ids return
**404**. The stored history keeps the raw LLM reply (finalize + memory need it);
only the returned copy is cleaned.

### `GET /strategies/{id}`

Strategy detail for the code viewer — no LLM round-trip.

```jsonc
{
  "strategy_id": "…", "name": "…", "description": "…",
  "market": "NIFTY50", "status": "backtested", "status_note": null,
  "generated_code": "import backtrader as bt\n…"
}
```

Unknown ids return **404**.

### `POST /strategies/{id}/backtest`

Run the backtest. Body fields are all optional:

```jsonc
// request (defaults shown)
{ "data_path": null, "cash": 100000.0, "commission_pct": 0.1, "sizer_percents": 95.0 }
// response (abridged)
{
  "strategy_id": "…", "status": "backtested",
  "total_return_pct": -25.03, "benchmark_return_pct": -12.36,
  "win_rate_pct": 37.8, "max_drawdown_pct": 25.03, "num_trades": 82,
  "sharpe": -1.35, "sortino": -1.67, "cagr_pct": -13.41,
  "start_date": "2024-09-30", "end_date": "2026-09-30",
  "trades": [ { "entry_date": "…", "exit_date": "…", "entry_price": 0.0,
                "exit_price": 0.0, "size": 0, "direction": "long",
                "bars_held": 0, "pnl": 0.0, "pnl_net": 0.0, "won": false } ],
  "trades_truncated": 0,
  "equity_curve": [["2024-09-30", 100000.0], "..."],
  "warnings": [], "raw_metrics": { "…full dump…" }
}
```

Omit `data_path` to auto-fetch NIFTY 50 (cached CSV, reused stale if Yahoo is
down). Errors: **404** unknown strategy · **422** no code / guardrail rejection /
bad params · **503** market data unavailable · **504** worker timeout.

### `POST /strategies/{id}/approve`

`backtested → approved` when the quality gate passes (backtest exists, ≥
`APPROVAL_MIN_TRADES` trades, drawdown within `APPROVAL_MAX_DRAWDOWN_PCT`).
Failures return **422** with `{"reasons": [...]}`. Response: `GateOut`
`{strategy_id, status, status_note}`.

### `POST /strategies/{id}/reject`

`draft/backtested → rejected`. Body `{"reason": "..."}` (3–500 chars, required).
Rejecting a `paper_trading` strategy returns **422** — stop it first.

### `POST /strategies/{id}/deploy`

`approved → paper_trading`. Body `{cash, commission_pct, sizer_percents}`
(all defaulted like backtest params). Re-runs the AST guardrails over the current
code and refuses duplicate active deployments (**422** with reasons). Records a
`paper_deployments` row and returns it.

### `POST /strategies/{id}/stop`

Closes the active deployment (`→ approved`), recording `stopped_at` and the
optional reason. **422** when nothing is active.

### `GET /strategies/{id}/deployments`

Newest-first deployment history for audit.

### `GET /health`

`{"status": "ok"}`.

## Strategy lifecycle

```
draft → backtested → approved → paper_trading
  \         \                       ^
   \-> rejected                      \-> approved (on stop)
```

- A strategy is born `draft` when the chat pipeline finalizes one.
- A backtest flips it to `backtested` and stores the metrics row the gate reads.
- Approval is a quality gate, not a profitability filter: it blocks strategies
  with no backtest, no real trading activity, or catastrophic drawdown.
- Deployment re-validates the guardrails (cheap, static) and enforces a single
  active deployment per strategy.
- Every reject/stop carries an optional-or-mandatory reason (`status_note` /
  `stop_reason`) so the UI and audit trail explain *why*, not just *what*.

## Chat and strategy extraction

Early attempts relied on prompting the model into a strict `STRATEGY_READY`
format. Against Groq's hosted models this failed consistently — disclaimers,
markdown headers, and runnable-script boilerplate (`if __name__`, `cerebro.plot()`,
CSV loading) survived two rounds of prompt tightening. Conclusion: prose
formatting instructions are not a data pipeline.

The two-stage approach instead:

1. `app/routers/chat.py` lets the model chat freely — no format constraints on the
   visible conversation.
2. `strategy_extractor.looks_like_final_strategy()` — cheap heuristic (starts with
   `STRATEGY_READY`, or a ` ```python ` block with a `bt.Strategy` subclass)
   deciding whether a second call is worth it.
3. `finalize_service.finalize_strategy()` — a narrow LLM call returning JSON
   against an exact schema (`name`, `description`, `code`) via Groq's
   `response_format: json_schema`, so the API validates the shape, not the prompt.
4. On any failure (unsupported mode, network, malformed JSON), regex-based
   `extract_strategy()` runs as fallback — forcing the class name to
   `GeneratedStrategy` and stripping `__main__`/plotting/CSV boilerplate.
5. Either path persists a `strategies` row linked to the conversation.

Display cleaning (`clean_reply_for_display`) strips the marker, `Name:` /
`Description:` headers, and code fences from the client-facing copy, keeping any
surrounding prose — or a short "ready, run a backtest below" confirmation when
nothing readable remains. History keeps the original.

## Backtest pipeline

`POST /strategies/{id}/backtest` runs `generated_code` through three layers:

1. **Guardrails** (`strategy_runner.check_guardrails`) — an `ast` walk refusing
   anything outside `ALLOWED_IMPORTS` (backtrader, pandas, numpy, math, datetime)
   and the usual escape hatches (`exec`, `eval`, `open`, `__import__`,
   `__class__`, `__globals__`, …). Static rejection, before anything runs.
2. **Subprocess** (`backtest_service.run_backtest_sandboxed`) — the worker runs as
   `python -m app.services.strategy_runner`, takes code on **stdin** (avoids
   Windows argv quoting/length limits), and emits one sentinel line
   `__BT_RESULT__ {json}` on stdout. The parent enforces the timeout, kills the
   process tree on expiry, and caps captured output at 256KB.
3. **Metrics** — analyzers attach by name to survive backtrader version drift.
   Three outputs are computed, not read off an analyzer:
   - **CAGR** — annualised in the parent from value span and date span, as a
     *percentage* consistent with the other `*_pct` fields.
   - **Sortino** — backtrader 1.9.78.123 ships no `SortinoRatio_A`, so it derives
     from the `TimeReturn` daily series: mean return over *downside* deviation,
     annualised with factor 252 (matching backtrader's Sharpe). Upside volatility
     is not penalised.
   - **Trade list + equity curve** — a `ClosedTradeCollector` analyzer records one
     row per closed trade (paired by `trade.ref`, since backtrader delivers a
     different object on close than on open; exit price is the execution bar's
     open, verified against pnl/size math). The equity curve compounds the
     `TimeReturn` series from starting cash and lands exactly on the broker value.
     Payloads cap at 500 trades / 400 points.

## Sandbox and security model

Be explicit about what protects what:

| Threat | Mitigation | Location |
| --- | --- | --- |
| Malicious imports / builtins | AST pre-check, static refusal | `strategy_runner.check_guardrails` |
| Dumb/accidental bad code | Same pre-check fails fast and cheap | `strategy_runner` + `test_guardrails.py` |
| Infinite loops / hangs | 120s wall-clock timeout (default) | `backtest_service` |
| Orphaned child processes | Tree kill: `killpg` on own process group (POSIX) / `taskkill /T` (Windows) | `backtest_service._kill_tree` |
| Memory bombs | `RLIMIT_AS` cap, default 1GB (`SANDBOX_MEMORY_MB`), POSIX only | `preexec_fn` child hook |
| CPU spin within timeout | Optional `RLIMIT_CPU` (`SANDBOX_CPU_SECONDS`), POSIX only | same hook |
| Log/output bombs | 256KB stdout cap; trade/equity payload caps | orchestrator + runner |
| Prompt-injected exfiltration | No network/file/syscall access in `ALLOWED_IMPORTS`; subprocess has no secrets in env beyond the app's own | guardrails + process boundary |

What this is **not**: a container or cgroup sandbox. A sufficiently clever
payload running *inside* the worker could still misbehave within its OS-user
privileges — treat the worker host accordingly and never run it as root.

## Database and migrations

Tables: `users`, `conversations`, `messages`, `strategies` (+ `status_note`),
`backtest_results`, `paper_deployments`. Strategy ↔ results/deployments are
one-to-many with delete-orphan cascades; all PKs are UUID strings.

The schema is owned by Alembic (`backend/alembic/`). The app runs
`upgrade head` on startup; nothing calls `create_all` outside tests.
Workflow for schema changes:

```bash
cd backend
# 1. edit app/models/db_models.py
# 2. generate against an EMPTY database (a populated dev DB diffs to nothing!)
python -m alembic revision --autogenerate -m "describe the change"
# 3. verify the cycle, then stamp/upgrade dev
python -m alembic upgrade head
```

Two Postgres lessons baked into the revisions: autogenerate against an empty
database, and drop ENUM types explicitly on downgrade (they survive
`DROP TABLE` and break re-upgrade otherwise).

## Frontend guide

Multi-page React app routed from `frontend/src/App.jsx`:

| Route | Screen |
| --- | --- |
| `/` | Landing page — capabilities, lifecycle, sample metrics, sandbox table, quickstart |
| `/chat` | Strategy Studio: chat window, input, and a `StrategyCard` rendered under any reply that produced a strategy |
| `/strategies`, `/strategies/:id` | Local strategy registry and per-strategy overview |
| `/strategies/:id/backtest`, `/approval`, `/deployment` | Backtest runner, approval gate, deployment log |

The `StrategyCard` shows the description, a status badge (`draft → backtested →
approved → paper_trading / rejected`), and context actions — backtest button,
approve/deploy/stop/reject (with inline reason form) — driven by live
`GET /strategies/{id}` detail so it never goes stale after a transition.

Results render a metrics grid beside the buy & hold benchmark with a beat/lagged
verdict, an SVG equity curve (no chart dependency), a collapsible per-trade table
with win/loss tinting, and a lazy-loaded code viewer. Risk disclaimers sit in the
persistent header, on every results card, and across the landing page.

Light Material 3 theme, layered CSS: `styles/tokens.css` (design tokens, reset,
typography, Material Symbols ligature setup), `styles/components.css`,
`styles/pages.css` and `styles/landing.css` (landing page only, scoped under
`.landing`). Scripts: `npm run dev` (Vite :5173), `npm run build`, `npm run
preview`, `npm run lint` (oxlint). No test runner is configured for the frontend.

`frontend/nginx.conf` adds the SPA fallback (`try_files $uri /index.html`) so
direct loads and refreshes on `/chat` and `/strategies/:id` resolve in React
Router instead of returning an nginx 404.

## Testing

```bash
cd backend
python -m pytest            # full suite, ~13s
python -m pytest tests/test_runner.py -q
python -m pytest -k sortino -q
```

| File | What it covers | Needs DB? |
| --- | --- | --- |
| `test_guardrails.py` | Clean code accepted; 12 escape hatches rejected statically | No |
| `test_runner.py` | Metrics incl. Sortino properties, trade list ↔ aggregates, equity curve ends on broker value | No |
| `test_worker_cli.py` | Sentinel protocol, timeout kill, tree-kill incl. orphan check, POSIX memory cap | No |
| `test_backtest_api.py` | Endpoint incl. 404/422 paths, DB persistence | Yes (self-skips) |
| `test_deployment_gate.py` | Full approve/reject/deploy/stop lifecycle, 13 cases | Yes (self-skips) |
| `test_display.py` | Reply cleaning: marker/headers/fences stripped, prose kept | No |

Fixtures in `tests/fixtures/`: four strategy fixtures plus `nifty50.csv`
(740 real OHLCV rows, 2023-09-18 → 2026-09-18) so everything except the two API
modules runs offline. `probe_trades.py` is a debug-only fixture importing
`traceback` — it would fail the guardrail and is referenced by no test.

DB-backed modules skip themselves when Postgres is unreachable
(`docker compose up -d db` to enable). A manual chat-flow QA script lives in
`test_prompt.txt` at the repo root.

## CI

`.github/workflows/ci.yml` runs on push to `main` and all PRs:

- **backend**: Python 3.11 + Postgres 16 service → `pip install` →
  `alembic upgrade head` (migrations must apply cleanly) → `pytest -q`
- **frontend**: Node 22 → `npm ci` → `npm run lint` → `npm run build`

## Docker deployment

```bash
docker compose up --build
```

| Service | Image | Port |
| --- | --- | --- |
| `db` | `postgres:16-alpine`, volume `pgdata` | `5432` |
| `backend` | built from `backend/` (`python:3.11-slim` + uvicorn) | `8000` |
| `frontend` | multi-stage `node:22-alpine` build → `nginx:1.27-alpine` | `3000` |

The browser calls the backend directly, so the published `:8000` is what the
nginx UI uses by default; bake a different API host with
`--build-arg VITE_API_BASE=…` on the frontend build. The backend container gets
`DATABASE_URL` pointing at host `db` (overriding `.env`) and runs migrations on
startup.

## Troubleshooting

- **`/chat` fails / LLM errors** — `GROQ_API_KEY` missing or invalid in
  `backend/.env`; check the backend logs. Everything except chat works without it.
- **Backtest API tests skip** — Postgres isn't up: `docker compose up -d db`
  from the repo root, then re-run pytest.
- **Port 8000 already in use** — a local `uvicorn` and `docker compose up backend`
  conflict; stop one. (Also note: on Windows the venv launcher shows as a
  parent + child `python.exe` pair — kill the parent and both go.)
- **`alembic revision --autogenerate` produces an empty migration** — you diffed
  against a database that already has the tables. Generate against an empty DB.
- **`type … already exists` on re-upgrade** — a downgrade left a Postgres ENUM
  behind; new revisions must drop custom types explicitly (see existing ones).
- **Frontend shows "Error reaching the backend"** — backend not running, or CORS:
  dev (`:5173`) and compose (`:3000`) origins are allow-listed in `app/main.py`.
- **Yahoo Finance rate-limits** — backtests reuse the stale CSV cache instead of
  failing, so this surfaces only as older `start_date`s, plus a 503 when no cache
  exists at all.

## Roadmap and known gaps

- **No auth** — a single `dev@local` user is auto-created per conversation.
- **No live trading loop** — deployments are validated and recorded; no scheduler
  or broker feed executes them against live markets.
- **Single-position sizing** — `PercentSizer` assumes one position at a time.
- **Sandbox, not a container** — see the security table above for exact boundaries.
- **No frontend tests** — backend is at 76 collected checks; the UI has lint +
  build only.