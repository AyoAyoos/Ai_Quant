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

## What's NOT built yet (next phases)
- Phase 2: strategy code auto-extraction from LLM reply, workflow to detect "ready to backtest"
- Phase 3: Yahoo Finance data pull for NIFTY 50 constituents + Backtrader execution + metrics extraction
- Phase 4: results-translation UI, trade dashboard, risk disclaimers throughout
- Phase 5: paper trading deployment gate, guardrails against bad AI-generated code, Docker packaging for full stack

## Getting started

### 1. Get a free Groq API key
Sign up at https://console.groq.com and grab an API key (free tier).

### 2. Backend
```bash
cd backend
cp .env.example .env
# paste your GROQ_API_KEY into .env
docker compose up -d db          # from project root, starts Postgres only
python -m venv venv && source venv/bin/activate
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

### 4. Full stack via Docker (backend + db only for now)
```bash
docker compose up --build
```

## Architecture notes
- The AI model is only the "brain" — the backend controller (`app/routers/chat.py`) owns the workflow:
  receive message → store in Postgres → call LLM → store reply → return to frontend.
- `Strategy.generated_code` will hold the Python (Backtrader-style) code the LLM produces once Phase 2's
  extraction logic is added — right now the raw chat reply is just stored as a message.
- Swapping LLM providers later (e.g. to local Ollama) only requires changing `app/config.py` and
  `app/services/llm_service.py` — the rest of the app is provider-agnostic.

## Known guardrail gaps (flagged for Phase 5)
- No validation/sandboxing of AI-generated Python yet — do not execute it as-is in Phase 3 without
  restricting imports and running it in an isolated process.
- No auth yet — a single dev user is auto-created for now.
