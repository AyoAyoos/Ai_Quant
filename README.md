# AI Conversational Quant Trading App — MVP

Chat with an AI, get a NIFTY 50 trading strategy generated, backtested, and prepared for paper trading.

## MVP scope (Phase 1)
- Single market: **NIFTY 50**
- Paper trading only (no live money)
- Stack: React (frontend) + FastAPI (backend) + PostgreSQL + Groq-hosted open-source LLM (Llama 3.1 / Qwen2.5)

## What's built so far
- ✅ Repo structure (backend + frontend)
- ✅ Postgres schema: `users`, `conversations`, `messages`, `strategies`, `backtest_results`
- ✅ FastAPI backend with `/chat` endpoint wired to Groq LLM
- ✅ React chat UI (talks to `/chat`)
- ✅ Docker Compose for local dev (Postgres + backend)
- ✅ **Strategy code extraction pipeline** (Phase 2, step 1 — see below)

## What's NOT built yet (next phases)
- Phase 2 (remaining): workflow polish around "ready to backtest" detection
- Phase 3: Yahoo Finance data pull for NIFTY 50 constituents + Backtrader execution + metrics extraction
- Phase 4: results-translation UI, trade dashboard, risk disclaimers throughout, friendlier chat rendering of finalized strategies
- Phase 5: paper trading deployment gate, guardrails against bad AI-generated code, Docker packaging for the frontend

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

## Architecture notes
- The AI model is only the "brain" — the backend controller (`app/routers/chat.py`) owns the workflow:
  receive message → store in Postgres → call LLM → store reply → detect + extract finalized strategy →
  store in `strategies` table → return reply to frontend.
- Swapping LLM providers later (e.g. to local Ollama) only requires changing `app/config.py` and
  `app/services/llm_service.py` — the rest of the app is provider-agnostic.

## Strategy extraction pipeline (Phase 2, step 1 — DONE)

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
`GeneratedStrategy(bt.Strategy)` class — no boilerplate, ready to be handed to a backtest runner
in Phase 3.

## Known guardrail gaps (flagged for Phase 5)
- No validation/sandboxing of AI-generated Python yet — do not execute `generated_code` as-is in
  Phase 3 without restricting imports and running it in an isolated subprocess with a timeout.
- No auth yet — a single dev user is auto-created for now.
- The chat bubble currently displays the raw LLM reply (including the `STRATEGY_READY` marker text
  when the model does use it) rather than a clean "✅ Strategy created" message — a Phase 4 UX task.
- Debug logging (`print()` statements) added during extraction debugging should be removed or
  converted to proper `logging` calls before this goes further — check `chat.py` and
  `finalize_service.py` for leftover prints.