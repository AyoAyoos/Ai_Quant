# AI Conversational Quant Trading App — MVP

Chat with an AI, get a NIFTY 50 trading strategy generated, backtested, and prepared for paper trading.

## MVP scope (Phase 1)
- Single market: **NIFTY 50**
- Paper trading only (no live money)
- Stack: React (frontend) + FastAPI (backend) + PostgreSQL + Groq-hosted open-source LLM (Llama 3.1 / Qwen2.5)

## Status

| Phase | Scope | State |
| --- | --- | --- |
| 1 | Repo, Postgres schema, `/chat` → Groq, chat UI, Docker Compose | ✅ done |
| 2 | Strategy detection + structured extraction pipeline | ✅ done |
| 3 | Market data, sandboxed Backtrader execution, metrics | ✅ done |
| 4 | Results UI, trade dashboard, cleaned replies, risk disclaimers | ✅ done |
| 5 | Migrations, CI, sandbox hardening, paper-trading gate, frontend Docker | ✅ done |

### What's built
- ✅ Repo structure (backend + frontend)
- ✅ Postgres schema: `users`, `conversations`, `messages`, `strategies`, `backtest_results`
- ✅ FastAPI backend with `/chat` endpoint wired to Groq LLM
- ✅ React chat UI (talks to `/chat`)
- ✅ Docker Compose for local dev (Postgres + backend)
- ✅ **Strategy extraction pipeline** — see below
- ✅ **Market data** — daily OHLCV pulled from Yahoo Finance and cached to
  `backend/data/{MARKET}.csv`; a stale cache is reused if a refresh fails, so
  backtests still work offline
- ✅ **Sandboxed backtesting** — AI-generated code runs in an isolated subprocess
  behind an AST guardrail and a 120s timeout
- ✅ **Metrics** — total return, buy & hold benchmark, CAGR, Sharpe, Sortino,
  max drawdown, win rate, profit factor, avg win/loss, trade counts, warnings
- ✅ **Backtest UI** — a strategy card appears under the reply that generated it,
  with a "Run backtest" button and a metrics grid beside the benchmark
- ✅ **Trade dashboard** — an SVG equity curve, a per-trade table (entry/exit,
  side, size, prices, net P&L, bars held), and a lazy-loaded code viewer
- ✅ **Clean chat rendering** — the client sees a short confirmation instead of
  the raw `STRATEGY_READY` marker and code dumps; the stored history keeps the
  original for the finalize call and conversation memory
- ✅ **Test suite** — 60 tests covering the guardrails, the runner, the worker
  CLI, the subprocess orchestrator, the API endpoints, and reply cleaning

### Not built yet (beyond MVP)
- **Live trading loop** — the gate records deployments; no scheduler or broker
  feed executes them against live markets yet.
- **Auth** — still a single auto-created dev user.
- Multi-position sizing (the PercentSizer assumes a single position).

## Getting started

### 1. Get a free Groq API key
Sign up at https://console.groq.com and grab an API key (free tier).

### 2. Backend
```bash
cd backend
cp .env.example .env
# paste your GROQ_API_KEY into .env
docker compose up -d db          # from project root, starts Postgres only
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\Activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Backend runs at http://localhost:8000 (health check: `/health`).

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend runs at http://localhost:5173 and talks to the backend at :8000.

### 4. Full stack via Docker (backend + db)
```bash
docker compose up --build
```
**Important:** if you're running Docker, don't also run a local `uvicorn --reload` process at the
same time — both will try to bind port 8000, and only one will actually be receiving your requests
(usually Docker). Always run `docker compose down` before `docker compose up --build` after code
changes, to guarantee the container picks up your latest edits.

### 5. Tests
```bash
cd backend
python -m pytest            # requires Postgres: docker compose up -d db
cd ../frontend && npm run lint
```
The `tests/test_backtest_api.py` and `tests/test_deployment_gate.py` modules skip
themselves when Postgres is unreachable; everything else runs offline against a
committed OHLCV fixture. CI (`.github/workflows/ci.yml`) runs the same steps on
every push/PR: Postgres service → `alembic upgrade head` → pytest, plus a clean
`npm ci` + lint + build for the frontend.

## Paper-trading gate (Phase 5)

The strategy lifecycle, driven from the card in the chat UI or the API:

```
draft → backtested → approved → paper_trading
  \         \                       ^
   \-> rejected                      \-> approved (on stop)
```

- **Approve** (`POST /strategies/{id}/approve`) — requires a backtest with at
  least `approval_min_trades` closed trades inside the `approval_max_drawdown_pct`
  cap (both configurable). Failures return the blocking reasons.
- **Reject** (`POST …/reject {reason}`) — from draft/backtested, reason mandatory.
- **Deploy** (`POST …/deploy {cash, commission_pct, sizer_percents}`) — requires
  approved status, re-runs the AST guardrails over the current code, and refuses
  duplicate active deployments. Records a row in `paper_deployments`.
- **Stop** (`POST …/stop {reason?}`) — closes the deployment, returns to approved.
- **History** (`GET …/deployments`) — newest-first audit trail.

This is the gate, not a live engine: it validates and records, but places no
orders anywhere. A scheduler + broker feed executing active deployments against
live markets is the next project, not the next commit.

## Architecture notes
- The AI model is only the "brain" — the backend controller (`app/routers/chat.py`) owns the workflow:
  receive message → store in Postgres → call LLM → store reply → detect + extract finalized strategy →
  store in `strategies` table → return reply to frontend.
- Swapping LLM providers later (e.g. to local Ollama) only requires changing `app/config.py` and
  `app/services/llm_service.py` — the rest of the app is provider-agnostic.

## Strategy extraction pipeline (Phase 2)

**The problem:** early attempts relied entirely on prompting the LLM to reply in a strict
`STRATEGY_READY` format on every final answer. In testing against Groq's hosted model, this failed
consistently — the model kept wrapping code in disclaimers, markdown headers, and runnable-script
boilerplate (`if __name__`, `cerebro.plot()`, CSV loading) despite explicit instructions not to.
Two rounds of prompt tightening did not fix it. Conclusion: prose-based formatting instructions
are not reliable enough to build a data pipeline on top of.

**The solution — a two-stage approach:**
1. `app/routers/chat.py` still lets the model chat freely and naturally on every turn — no format
   constraints on the visible conversation.
2. `app/services/strategy_extractor.py` — `looks_like_final_strategy()` — a cheap heuristic that
   checks whether a reply is *probably* a finished strategy (either starts with `STRATEGY_READY`,
   or contains a ` ```python ` block with a `bt.Strategy` subclass). This decides whether it's worth
   making the second call at all.
3. `app/services/finalize_service.py` — `finalize_strategy()` — a **separate, narrow-purpose LLM
   call** that takes the full conversation and asks the model to do ONE thing: return JSON matching
   an exact schema (`name`, `description`, `code`), using Groq's `response_format: json_schema` mode
   so the output is schema-validated by the API itself, not just requested via prompt.
4. If the structured call fails for any reason (model doesn't support `json_schema`, network error,
   malformed JSON) `strategy_extractor.py`'s regex-based `extract_strategy()` runs as a fallback —
   it forces the class name to `GeneratedStrategy` and strips runnable-script boilerplate even from
   a messy reply.
5. Either path's result is saved as a new row in the `strategies` table, linked to the conversation.

**Result, confirmed working:** strategies now save to Postgres with a clean `name`, a real
`description`, and `generated_code` containing only `import backtrader as bt` + a
`GeneratedStrategy(bt.Strategy)` class — no boilerplate, ready to be handed to the backtest runner.

## Backtest pipeline (Phase 3)

`POST /strategies/{id}/backtest` runs `generated_code` through three layers:

1. **Guardrails** (`strategy_runner.check_guardrails`) — an `ast` walk that refuses anything outside
   `ALLOWED_IMPORTS` (backtrader, pandas, numpy, math, datetime) and blocks the usual escape
   hatches (`exec`, `eval`, `open`, `__import__`, `__class__`, `__globals__`, …). This rejects bad
   code *statically*, before anything runs.
2. **Subprocess** (`backtest_service.run_backtest_sandboxed`) — the worker is spawned as
   `python -m app.services.strategy_runner`, receives the strategy code on **stdin** (avoids Windows
   argv quoting/length limits), and reports one sentinel line `__BT_RESULT__ {json}` on stdout. The
   parent enforces a 120s timeout and kills the worker on expiry, and caps captured output.
3. **Metrics** — analyzers are attached by name so the runner survives backtrader version drift.
   Three outputs are computed rather than read off an analyzer:
   - **CAGR** — annualised in the parent from the value span and date span. It is a *percentage*,
     consistent with the other `*_pct` fields.
   - **Sortino** — backtrader 1.9.78.123 ships no `SortinoRatio_A`, so it is derived from the
     `TimeReturn` daily series: mean return over *downside* deviation, each annualised with a
     factor of 252 (the same factor backtrader uses for Sharpe). Upside volatility does not
     penalise it.
   - **Trade list + equity curve** — a `ClosedTradeCollector` analyzer records one row per
     closed trade, and the equity curve is reconstructed by compounding the `TimeReturn`
     series from starting cash (it lands exactly on the broker value). Payloads are capped
     at 500 trades / 400 points so a hyperactive strategy cannot blow the 256KB stdout cap.

Error mapping: 404 unknown strategy, 422 no code / guardrail rejection / bad params,
503 market data unavailable, 504 timeout.

## Sandbox hardening (Phase 5)

Timeouts used to `proc.kill()` only the direct child, so a strategy that shelled
out would leave orphans. Now the worker starts in its own process group on POSIX
(`start_new_session`) and timeouts `killpg` the whole tree; on Windows
`taskkill /T` walks the child tree. POSIX workers additionally get `rlimit`
backstops (`sandbox_memory_mb`, default 1GB; optional `sandbox_cpu_seconds`).
Windows has no equivalent, so there the wall-clock timeout plus tree kill is the
documented boundary.

## Database migrations (Phase 5)

The schema is owned by Alembic (`backend/alembic/`); the app runs
`upgrade head` on startup and nothing calls `create_all` outside tests.
Two Postgres-specific lessons are baked into the revisions: autogenerate
against an empty database (a populated dev DB yields an empty diff), and
drop ENUM types explicitly on downgrade (they survive `DROP TABLE` and break
re-upgrade otherwise).

## Known gaps
- **The AST check is a guardrail, not a sandbox.** It stops accidental and dumb malicious code, but
  the real boundary is the isolated subprocess with tree-kill, memory caps (POSIX), and timeouts.
  True container/cgroup isolation is still future work.
- **No auth yet** — a single dev user is auto-created per conversation.
- **`PercentSizer` assumes a single position** — multi-position sizing is not handled.
- **Alembic is installed but unused** — the schema is created via `Base.metadata.create_all` on
  startup. Migrations should be wired up before the schema is depended on in production.
- **No CI** — the test suite runs locally only.
