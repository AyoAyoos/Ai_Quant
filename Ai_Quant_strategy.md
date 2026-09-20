# OpenAlgo "Strategy" Section — End-to-End Working Documentation

A comprehensive technical walkthrough of how the Strategy section of OpenAlgo works:
every surface, every code path, every database table, and every file that participates.

> This document is a **map with detail**, not a fork of the canonical docs. The
> authoritative per-feature documentation lives under `docs/` and `strategies/`;
> this file ties them together for the Strategy developer/operator and lists every
> file the feature touches so it can be traced end to end.

---

## Table of Contents

1. [Overview](#1-overview)
2. [The Six Strategy Surfaces](#2-the-six-strategy-surfaces)
3. [End-to-End Execution Flow](#3-end-to-end-execution-flow)
4. [Complete File Inventory](#4-complete-file-inventory)
5. [Database Schema](#5-database-schema)
6. [Configuration (.env)](#6-configuration-env)
7. [Registration and Lifecycle](#7-registration-and-lifecycle)
8. [Existing Documentation Map](#8-existing-documentation-map)

---

## 1. Overview

OpenAlgo is a production algorithmic trading platform: a Flask backend with a
React 19 frontend, running a single broker session per self-hosted instance.
The **"Strategy" section** is not one feature — it is the automation umbrella of
the platform. Anything that runs an automated trading rule and places orders is a
"strategy" here.

All strategy surfaces share:

- **One broker session** per deployment (a single login for the whole instance).
- **One order placement path**: most strategies funnel into the same
  `/api/v1/placeorder` / `/api/v1/placesmartorder` API → service layer → broker
  order API.
- **The event bus** (`order.placed`, `order.update`, `multiorder.completed`,
  `basket.completed`, `split.completed`, `options.completed`) which feeds the
  **Strategy Book** — a per-strategy position/P&L ledger kept because the broker
  itself only nets positions by `(symbol, exchange, product)` and drops the
  strategy label.
- **Auto square-off**: intraday strategies schedule an APScheduler job
  (`squareoff_{strategy_id}`) that flattens positions at the configured
  `squareoff_time`.
- **Telegram / WhatsApp alerts** for strategy events.

### The one-line architecture

```
Signal in (webhook / scheduled job / subprocess / price alert / order update)
        │
        v
  Entry point (CSRF-exempt, rate-limited, auth-checked)
        │
        v
  Strategy executor / order queue (throttled)
        │
        v
  /api/v1/placeorder (or placesmartorder)  →  place_order_service
        │
        v
  Broker order API (import_broker_module)
        │
        v
  Event bus (order.placed / order.update)
        │
        v
  Strategy Book (strategy_order_tags -> apply_fill -> strategy_positions)
        │
        v
  P&L (strategy_pnl_service), dashboards, Flow strategyPnl node
```

### The six surfaces

| # | Surface | Route | Backend entry | Frontend entry |
|---|---------|-------|---------------|----------------|
| 1 | Webhook Strategies (TradingView, Amibroker, Excel, MCP, ...) | `/strategy` | `blueprints/strategy.py` | `frontend/src/pages/strategy/*` |
| 2 | Chartink Strategies | `/chartink` | `blueprints/chartink.py` | `frontend/src/pages/chartink/*` |
| 3 | Python Strategy Host | `/python` | `blueprints/python_strategy.py` | `frontend/src/pages/python-strategy/*` |
| 4 | Flow (No-Code Builder) | `/flow` | `blueprints/flow.py` + `services/flow_*` | `frontend/src/pages/flow/*` |
| 5 | Strategy Builder (Options) | `/strategybuilder` | `blueprints/strategy_chart.py`, `blueprints/strategy_portfolio.py` | `frontend/src/pages/StrategyBuilder.tsx`, `StrategyPortfolio.tsx` |
| 6 | Strategy Book (P&L ledger) | internal | `subscribers/strategy_book_subscriber.py`, `database/strategy_book_db.py` | consumed by Flow's `strategyPnl` node |

---

## 2. The Six Strategy Surfaces

### 2.1 Webhook Strategies — `/strategy` (`blueprints/strategy.py`)

The core "strategy" feature. External signal platforms (TradingView, Amibroker,
Chartink, GoCharting, Excel, Python SDKs, MCP servers) POST to a private webhook
URL and OpenAlgo converts the signal into broker orders.

**Database** — `database/strategy_db.py`:

- `Strategy` (table `strategies`): `id`, `name`, `webhook_id` (UUID, unique, the
  private URL token), `user_id`, `platform` (default `tradingview`), `is_active`,
  `is_intraday`, `trading_mode` (`LONG`/`SHORT`/`BOTH`), `start_time`,
  `end_time`, `squareoff_time` (HH:MM strings), timestamps.
- `StrategySymbolMapping` (table `strategy_symbol_mappings`): `strategy_id` FK,
  `symbol`, `exchange`, `quantity`, `product_type` (`MIS`/`CNC`). Multi-symbol
  strategies resolve the incoming signal's symbol into configured quantities and
  exchanges.

**Webhook flow** (`POST /strategy/webhook/<webhook_id>`):

1. Flask-Restx routing (the webhook route is CSRF-exempt — registered at
   `app.py` lines 427–434).
2. Rate-limited by `@limiter.limit(WEBHOOK_RATE_LIMIT)` (default `"100 per
   minute"`) plus `@limiter.limit(STRATEGY_RATE_LIMIT)` (default `"200 per
   minute"`).
3. Strategy looked up via `get_strategy_by_webhook_id` (TTL-cached 5000 / 300s).
4. The incoming (platform-specific) symbol is counter-mapped through the symbol
   mappings to a broker symbol + exchange + quantity via
   `database/symbol.enhanced_search_symbols`.
5. Orders are pushed onto one of **two threading queues**, not executed inline:
   - `regular_order_queue` → builds a `placeorder` payload → POSTs it to
     `${BASE_URL}/api/v1/placeorder` — throttled, honoring the `10 per second`
     order rate limit.
   - `smart_order_queue` → builds a `placesmartorder` payload → POSTs it to
     `${BASE_URL}/api/v1/placesmartorder`.
   - The strategy name rides along as the `strategy` key in the payload.
6. **Square-off**: if `is_intraday`, an APScheduler job `squareoff_{strategy_id}`
   (timezone `Asia/Kolkata`, `max_instances=1`, `coalesce=True`,
   `misfire_grace_time=300`) calls `squareoff_positions` at `squareoff_time`.

Endpoints exposed (paraphrased): strategy CRUD (`create/save/delete/toggle/
update`), symbol mappings (add / bulk / delete), `get_webhook_url`,
`get_strategies`, `get_strategy/<id>`.

Frontend: `frontend/src/pages/strategy/` (list, create, view, configure symbols via
command search or CSV bulk upload).

### 2.2 Chartink Strategies — `/chartink` (`blueprints/chartink.py`)

A dedicated surface for ChartInk's scanner alerts. Lives entirely in
`blueprints/chartink.py` + `database/chartink_db.py` (its own tables, not shared
with the generic `strategies` table).

**Database** — `database/chartink_db.py`:

- `ChartinkStrategy` (table `chartink_strategies`): same shape as `Strategy`
  minus `trading_mode`/`platform`; adds `is_intraday` + per-strategy
  `start_time`/`end_time`/`squareoff_time` time controls.
- `ChartinkSymbolMapping` (table `chartink_symbol_mappings`): stores
  `chartink_symbol` (the ChartInk name), `exchange` (`NSE`/`BSE` only, per
  `VALID_EXCHANGES`), `quantity`, `product_type` (`MIS`/`CNC`).

**Webhook flow** (`POST /chartink/webhook/<webhook_id>`):

1. ChartInk cannot set custom HTTP headers, so auth is a **query-param secret**
   (`?secret=`), validated on the webhook route.
2. Strategy is looked up by `webhook_id`.
3. The ChartInk symbol is counter-mapped to the OpenAlgo symbol/exchange/
   quantity (`chartink_symbol` → `symbol`).
4. Orders enqueued — smart orders at line ~99, regular orders at line ~137, both
   carrying `strategy=<name>`.
5. **Square-off**: APScheduler job `squareoff_{strategy_id}` honoring
   `squareoff_time` (time-based trading only within `start_time`–`end_time`).

Frontend: `frontend/src/pages/chartink/*` (list, create with strategy_type
`intraday`, view, configure symbols).

### 2.3 Python Strategy Host — `/python` (`blueprints/python_strategy.py`)

Runs user-uploaded Python strategy scripts as **isolated subprocesses**, scheduled
on IST times, with live logs streamed over SSE.

**Process model:**

- Each strategy = `subprocess.Popen` tracked in module state
  `RUNNING_STRATEGIES = {strategy_id: {...}}`.
- Stop sequence: terminate → 3s poll → kill → 2s (uses `psutil`, eventlet-safe).
- A reaper job `reap_dead_strategies` runs ~every 60s to `cleanup_dead_processes()`.
- Writes are guarded by `_PROCESS_LOCK` (an `RLock`, reentrant for nested stop).
- The scheduler is an `BackgroundScheduler` in `Asia/Kolkata` with three recurring
  jobs:
  - `daily_trading_day_check` (00:01 IST) — stops strategies on weekends/holidays,
    sets `paused_reason`.
  - `market_hours_enforcer` (every minute) — auto-resume when an exchange reopens.
  - `reap_dead_strategies` (every 60s).

**Resource & log limits** (env-configurable, see §6):

- `RLIMIT_AS` via `STRATEGY_MEMORY_LIMIT_MB` (default 1024, Unix/macOS only,
  applied with `preexec_fn`).
- Logs at `strategies/logs/{strategy_id}_{IST}_IST.log`, capped by
  `STRATEGY_LOG_MAX_FILES`, `STRATEGY_LOG_MAX_SIZE_MB`, `STRATEGY_LOG_RETENTION_DAYS`.

**Exchange-aware scheduling** — powered by `database/market_calendar_db.py`:

- `SUPPORTED_EXCHANGES = ["NSE","BSE","NFO","BFO","MCX","BCD","CDS","NCO","CRYPTO"]`.
- TTLCaches: `_timings_cache` (500, 3600s), `_holidays_cache` (50, 3600s).
- Functions: `get_effective_session_window`, `get_market_hours_status`,
  `get_special_session`, `is_market_holiday`, `is_market_open`.
- MCX/CRYPTO ignore NSE holidays; CRYPTO never closes; `normalize_exchange()`
  falls back to NSE.

**Per-strategy environment injection** (surfaced to the script via env vars):

- `STRATEGY_ID`, `STRATEGY_NAME`, `OPENALGO_STRATEGY_EXCHANGE` (from config).
- `OPENALGO_API_KEY` (decrypted from DB).
- `OPENALGO_HOST`, `HOST_SERVER`, `WEBSOCKET_URL` (so the script can place orders
  and subscribe through the `openalgo` SDK).

**Config persistence**: `strategies/strategy_configs.json` (atomic write;
`load_strategy_configs`/`save_strategy_configs`; backfills `exchange`).

**Key routes**: `/python` (index), `/new` (GET/POST uploading a `.py` via
`secure_filename`), `/api/events` (SSE with per-sub `queue.Queue(maxsize=100)`,
30s heartbeat), `/api/strategy/<id>`, `/api/strategy/<id>/content`,
`/api/logs/<id>` and `/api/logs/<id>/<log_name>`, `/edit/<id>`, `/export/<id>`,
`/save/<id>`, `/start/<id>`, `/stop/<id>`, `/restart/<id>`, `/delete/<id>`,
`/schedule/<id>`, `/unschedule/<id>`.

**Lifecycle**: `restore_strategy_states()` (gated on master-contract readiness),
`check_and_start_pending_strategies()`, `restore_strategies_after_login()`
(called by `database/master_contract_cache_hook.py` after a master-contract
download), `initialize_with_app_context()` (boot), `cleanup_on_exit` via
`atexit`.

Frontend: `frontend/src/pages/python-strategy/*` (index, new/upload, edit,
logs, schedule, 1407-line user guide).

### 2.4 Flow (No-Code Builder) — `/flow`

A node-graph automation builder: market data → indicators → conditions → order
execution. The deepest surface (Flow executor is ~3,137 lines).

**Blueprints** — `blueprints/flow.py`:

- **Workflow CRUD**: `/api/workflows` GET/POST, `/api/workflows/<id>`
  GET/PUT/DELETE.
- **Activation** (`POST /api/workflows/<id>/activate`) dispatches by trigger node:
  - `start` + schedule → `services/flow_scheduler_service.FlowScheduler`,
    `add_workflow_job(...)`, then `set_schedule_job_id`.
  - `priceAlert` → `services/flow_price_monitor_service.FlowPriceMonitor.add_alert`.
  - `orderUpdateTrigger` → `services/flow_order_update_monitor_service.add_watch`
    (raises `ValueError` → HTTP 400 on bad config).
  - Every activation/execution gates on `_execution_blocked(workflow)` (strict
    `validate_workflow`).
- **Webhooks**: `/flow/webhook/<token>` and `/flow/webhook/<token>/<symbol>`;
  HMAC `hmac.compare_digest` secret check for `url` vs `payload` auth; API key
  resolved by priority: encrypted `get_workflow_api_key(workflow)` → session →
  `OPENALGO_API_KEY` env; 403 when webhook disabled or workflow inactive.
- **Webhook config**: `/api/workflows/<id>/webhook` GET, enable/disable,
  regenerate (token + secret), regenerate-secret, auth-type.
- **Import/Replace**: `/import` (migrate legacy node fields + strict validate);
  `/replace` keeps `id`/webhook/api_key/active state, detects trigger change and
  tells the user to reactivate.
- **Status/meta**: `/api/monitor/status`, `/api/index-symbols` (lot sizes from the
  `SymToken` master contract for NSE/BSE index underlyings).

**Services** — `services/flow_*`:

- `flow_openalgo_client.py` — `FlowOpenAlgoClient(api_key)`; in-process calls into
  `services.*` (orders, quotes, depth, history, option chain, account, alerts);
  factory `get_flow_client(api_key)`.
- `flow_workflow_validator.py` — `VALID_NODE_TYPES` (~57, kept in lockstep with
  `frontend/src/components/flow/nodes/index.ts`, parity enforced by
  `test/test_flow_workflow_validator.py`); `validate_workflow(strict=...)`,
  `migrate_legacy_node_data`, `trigger_config`.
- `flow_scheduler_service.py` — `FlowScheduler` singleton; APScheduler
  `BackgroundScheduler` + `SQLAlchemyJobStore` (table `flow_apscheduler_jobs` in
  the `flow` DB); triggers `interval`/`once`/`daily`/`weekly`; market-hours gate
  `is_within_market_hours()` resolving via the exchange calendar
  (`get_effective_session_window`), default exchange `NSE`.
- `flow_price_monitor_service.py` — `PriceAlert` + `FlowPriceMonitor` singleton;
  background polling thread; condition aliases normalized; expiration window;
  `_trigger_workflow`.
- `flow_order_update_monitor_service.py` — `OrderUpdateWatch` +
  `FlowOrderUpdateMonitor`; subscribes to event bus `order.update`; `_matches` /
  `_fire` (once vs always); `restore_order_update_watches()` at boot.
- `flow_executor_service.py` — the execution engine (§3.3).

Frontend: `frontend/src/pages/flow/*`, `frontend/src/components/flow/*`,
`frontend/src/stores/flowWorkflowStore.ts`, `frontend/src/lib/flow/constants.ts`,
`frontend/src/api/flow.ts`, `frontend/src/types/flow.ts`.

### 2.5 Strategy Builder (Options) — `/strategybuilder`

An options-strategy designer (payoff/greeks/PnL analysis) plus a **portfolio
saved per watchlist** (1/2).

- **Frontend only for analysis**, backed by:
  - `blueprints/strategy_chart.py` — `/strategybuilder/api/strategy-chart` (POST,
    combined-premium price series), `/strategybuilder/api/multi-strike-oi`,
    `/strategybuilder/api/intervals`; rate-limited `STRATEGY_CHART_LIMIT` ("30 per
    minute"); delegating to `services/strategy_chart_service`.
  - `blueprints/strategy_portfolio.py` — `/api/strategy-portfolio` GET/POST,
    `/api/strategy-portfolio/<id>` GET/PUT/DELETE; reads/writes
    `database/strategy_portfolio_db`; limits `STRATEGY_PORTFOLIO_READ_LIMIT`
    ("60 per minute") / `STRATEGY_PORTFOLIO_WRITE_LIMIT` ("20 per minute").
- **Option chain** is loaded via `optionChainApi`; math is in
  `frontend/src/lib/strategyMath.ts` (Black-Scholes) with 38 templates in
  `frontend/src/lib/strategyTemplates.ts`.
- The builder supports 9 bullish + 9 bearish + 20 non-directional templates
  (iron condors, butterflies, straddles, strangles, vertical/calendar/diagonal
  spreads, `double_fly`, `batman_strategy`, ...).

Frontend: `frontend/src/pages/StrategyBuilder.tsx` (1413 lines),
`frontend/src/pages/StrategyPortfolio.tsx`, `frontend/src/components/strategy-builder/*`.

### 2.6 Strategy Book (Per-Strategy P&L) — internal

Because the broker nets positions by `(symbol, exchange, product)` — dropping the
strategy tag — OpenAlgo keeps its **own parallel ledger**, fed only from the
event bus (`order.placed` is the only point the tag is known).

- `subscribers/strategy_book_subscriber.py` — `on_order_placed` →
  `record_order_tag`, `on_order_update` → `apply_fill`. Registered in `app.py`
  with `register_strategy_book(_bus)` (3-attempt retry, `app.py` ~760–772),
  **before** `db_ready` is set so no order is ever untagged.
- `database/strategy_book_db.py` — three tables (§5), idempotent fills via
  `applied_quantity` / `applied_notional` watermarks, pending-fill buffering to
  absorb fill-before-tag races, `threading.RLock()` serialization.
- `services/strategy_pnl_service.py` — `pnl_from_book` (realized from the book,
  unrealized marked to position-book `ltp`), `get_strategy_pnl(client, strategy)`.
- **Consumer**: the Flow `strategyPnl` data node, and dashboards.

---

## 3. End-to-End Execution Flow

### 3.1 Webhook / external-platform path

```
TradingView | Amibroker | Chartink | Excel | Python | MCP
        │  POST signal  ("{{strategy.order.action}}", symbol, qty)
        v
/strategy/webhook/<webhook_id>   (CSRF-exempt, rate-limited 100/200 per min)
        │
        v
get_strategy_by_webhook_id (TTL cache)  +  is_active check
        │
        v
Symbol counter-mapping (StrategySymbolMapping -> enhanced_search_symbols)
        │
        v
regular_order_queue ──throttle──> payload {strategy: name}
                          │
                          v
                ${BASE_URL}/api/v1/placeorder
                          │
                          v
        place_order_service.place_order(order_data, api_key)
                          │
                import_broker_module(broker_name)
                order_schema.load, constants validation
                Action Center pending-order hook (analyze mode)
                          │
                          v
                broker.<broker>.api.order_api.place_order_api
                          │
                          v
        Event bus: OrderPlacedEvent / OrderFailedEvent / AnalyzerErrorEvent
                          │
                          v
                strategy_book_subscriber.record_order_tag
                + Flow order-update monitor + Square-off scheduler
```

### 3.2 Python Strategy Host path

```
User uploads strategy.py  ->  /python/new (secure_filename)
        │  saved under strategies/scripts/
        v
strategy_configs.json (persisted config, schedule, exchange)
        │
        v
IST BackgroundScheduler (daily_trading_day_check / market_hours_enforcer)
        │  exchange-aware via market_calendar_db (holidays, session window)
        v
subprocess.Popen  (+ RLIMIT_AS cap, injected env:
        STRATEGY_ID, STRATEGY_NAME, OPENALGO_STRATEGY_EXCHANGE,
        OPENALGO_API_KEY, OPENALGO_HOST, HOST_SERVER, WEBSOCKET_URL)
        │
        v
script places orders through the openalgo SDK against /api/v1/placeorder
        │
        v
logs streamed to strategies/logs/{id}_{IST}_IST.log
  + live-tiled over SSE (/python/api/events)
  + reaper job cleans dead processes
```

### 3.3 Flow execution path

```
Flow node graph (nodes + edges JSON in flow_workflows)
        │
        v
User activates -> activate_workflow:
        ├── start + schedule   -> FlowScheduler.add_workflow_job
        ├── priceAlert        -> FlowPriceMonitor.add_alert
        └── orderUpdateTrigger-> FlowOrderUpdateMonitor.add_watch
   (each gated by _execution_blocked = strict validate_workflow)
        │
        v
Trigger fires (schedule / price match / order.update / webhook / Run Now)
        │
        v
execute_workflow(workflow_id, webhook_data, api_key)
   in services/flow_executor_service.py:
        workflow lock (already_running guard)
        strict validate_workflow -> create_execution("running")
        find trigger node, build edge maps
        execute_node_chain:
              depth-first walk, MAX_NODE_DEPTH=100, MAX_NODE_VISITS=500
              condition edges filtered via TRUE_HANDLES/FALSE_HANDLES
              gate nodes wait for every wired input (combinational)
        node handlers: order nodes (place/smart/options/multi/
              basket/split/modify/cancel/cancel-all/close-positions)
              via FlowOpenAlgoClient -> services.* (in-process)
              data nodes, condition nodes, streaming nodes, utility nodes
        # defaults: strategy tag = workflow name across order nodes
        v
update_execution_status + execution logs persisted + SSE/SocketIO
```

---

## 4. Complete File Inventory

Every file the Strategy section uses, grouped by layer. Paths are relative to the
repository root (`D:\OpenAlgo\openalgo`).

### 4.1 Backend — Blueprints (Flask routes)

| File | Role |
|---|---|
| `blueprints/strategy.py` | Webhook strategies blueprint (`/strategy`). Webhook route, dual order queues, square-off scheduler, strategy + symbol-mapping CRUD. |
| `blueprints/chartink.py` | Chartink blueprint (`/chartink`). Query-param secret auth, symbol counter-mapping, time-based trading, square-off. |
| `blueprints/python_strategy.py` | Python Strategy Host (`/python`). Subprocess management, IST scheduler, SSE events, upload/edit/log/schedule routes (~2,983 lines). |
| `blueprints/flow.py` | Flow blueprint (`/flow`). Workflow CRUD, activation dispatch to scheduler/price/order-update monitors, webhook execution + auth, import/replace, monitor status, index-symbol lot sizes. |
| `blueprints/strategy_chart.py` | Strategy Builder chart endpoints: `/strategybuilder/api/strategy-chart`, `/multi-strike-oi`, `/intervals`. |
| `blueprints/strategy_portfolio.py` | Strategy Builder portfolio CRUD (`/api/strategy-portfolio`). |
| `blueprints/react_app.py` | React fallback routes for `/strategy`, `/strategy/<id>`, `/strategy/<id>/configure`, `/python/<id>/*`, `/chartink/<id>`, `/chartink/<id>/configure`. |
| `blueprints/tv_json.py` | TradingView `mode="strategy"` JSON -- maps `{{strategy.order.action}}`, `{{strategy.order.contracts}}`, `{{strategy.position_size}}`, label "TradingView Strategy". |
| `blueprints/orders.py` | UI trades tagged `strategy: "UI Exit Position"`, GTT modify tagged `"GTT Modify"`. |
| `restx_api/place_order.py` | `/api/v1/placeorder` resource; `@limiter.limit(ORDER_RATE_LIMIT)` (default "10 per second"); delegates to `services/place_order_service`. |
| `restx_api/place_smart_order.py` | `/api/v1/placesmartorder` resource (smart orders). |

### 4.2 Backend — Service Layer

| File | Role |
|---|---|
| `services/place_order_service.py` | Core order placement. `import_broker_module` -> broker order API, `order_schema.load`, constants validation, analyze-mode / Action Center hook, publishes `OrderPlacedEvent`/`OrderFailedEvent`/`AnalyzerErrorEvent`. |
| `services/place_smart_order_service.py` | Smart-order placement (`place_smart_order`). |
| `services/place_options_order_service.py` | Options order placement (single-leg). |
| `services/options_multiorder_service.py` | Multi-leg options order placement (`options_multiorder_service`). |
| `services/flow_executor_service.py` | Flow execution engine (`WorkflowContext`, `NodeExecutor`, `execute_workflow`, `execute_node_chain`, all node handlers, lotsize/expiry resolution). ~3,137 lines. |
| `services/flow_openalgo_client.py` | In-process OpenAlgo API wrapper for Flow nodes (`get_flow_client(api_key)`). |
| `services/flow_workflow_validator.py` | Structural validation + legacy migration of workflow graphs; `VALID_NODE_TYPES` parity with the frontend node registry. |
| `services/flow_scheduler_service.py` | Flow scheduling singleton (APScheduler + `flow_apscheduler_jobs` jobstore, market-hours gating). |
| `services/flow_price_monitor_service.py` | Price-alert trigger monitor (polling). |
| `services/flow_order_update_monitor_service.py` | Order-update trigger monitor (event-bus push). |
| `services/strategy_pnl_service.py` | Per-strategy P&L aggregation from the strategy book, marked to live LTP. |
| `services/strategy_chart_service.py` | Combined-premium time series for the Strategy Builder chart. |
| `services/indicator_service.py` | Indicator catalog used by the Flow `indicator` node (kept in sync with `frontend/src/lib/flow/constants.ts`). |

### 4.3 Backend — Database Layer

| File | Role |
|---|---|
| `database/strategy_db.py` | `Strategy` + `StrategySymbolMapping` models, CRUD, TTL webhook/user caches, `init_db()`. |
| `database/chartink_db.py` | `ChartinkStrategy` + `ChartinkSymbolMapping` models and CRUD, `init_db()`. |
| `database/strategy_book_db.py` | Strategy Book: `StrategyOrderTag`, `StrategyPendingFill`, `StrategyPosition` models; `record_order_tag`, `apply_fill`, `get_strategy_legs`, `list_strategies`, `reset_strategy`, migrations, TTL pruning. |
| `database/strategy_portfolio_db.py` | Strategy Builder portfolio + entries persistence (`strategy_portfolio` table). |
| `database/flow_db.py` | `FlowWorkflow` + `FlowWorkflowExecution` models; workflow/webhook/execution CRUD; Fernet-encrypted `api_key`. |
| `database/market_calendar_db.py` | Exchange-aware trading calendar: session windows, special sessions, holidays, `is_market_open`. Powers Python-host and Flow market-hours gating. |
| `database/symbol.py` | `enhanced_search_symbols` (symbol resolution/counter-mapping), `SymToken` master-contract lookups, lot sizes. |
| `database/engine_factory.py` | `create_db_engine()` (NullPool) for all SQLite engines. |
| `database/db_init_helper.py` | `init_db_with_logging()` shared table-creation helper. |
| `database/auth_db.py` | `safe_decrypt_token`/`encrypt_token` -- encrypts `flow_workflows.api_key`. |
| `database/action_center_db.py` | `PendingOrder` -- approval gate when Action Center is active. |
| `database/apilog_db.py` | `async_log_order` -- orders log. |
| `database/analyzer_db.py` | `async_log_analyzer` -- analyzer events. |
| `database/master_contract_cache_hook.py` | After a master-contract download, calls `restore_strategies_after_login()`. |
| `utils/db_sessions.py` | Registers strategy-book session cleanup in the teardown registry. |

### 4.4 Backend — Subscribers, Schedulers, Executors

| File | Role |
|---|---|
| `subscribers/strategy_book_subscriber.py` | Event-bus subscriber: `order.placed` -> `record_order_tag`, `order.update` -> `apply_fill`, plus batch topics (`multiorder.completed`, `basket.completed`, `split.completed`, `options.completed`). |
| `sandbox/squareoff_thread.py` | Sandbox daily square-off/reset (APScheduler daemon thread). |
| `websocket_proxy/server.py` | WebSocket proxy (`ZMQ_PORT` 5555 / proxy 8765) that carries the live feed strategies and Flow streaming nodes consume. |

### 4.5 Backend — Runtime Files (gitignored, created at runtime)

| File | Role |
|---|---|
| `strategies/strategy_configs.json` | Persisted Python-strategy configs (keyed by `strategy_id`, backfilled `exchange`). |
| `strategies/scripts/*.py` | Uploaded Python strategy scripts. |
| `strategies/logs/{strategy_id}_{IST}_IST.log` | Per-strategy logs (under `log/strategies/`; its own `.gitignore`). |
| `strategies/strategy_env.json` / `.secure_env` | Per-strategy env vars / secrets placeholders. |
| `flow` DB `flow_apscheduler_jobs` | APScheduler job store table auto-created at runtime by `SQLAlchemyJobStore`. |

### 4.6 Backend — Static Support Files

| File | Role |
|---|---|
| `app.py` | Registers all strategy blueprints, DB init, strategy-book bus registration, `init_python_strategy()`, `init_flow_scheduler()`, `restore_order_update_watches()`. |
| `strategies/README.md` | Full user/architecture doc for the Python Strategy Host. |
| `strategies/RESOURCE_LIMITS.md` | RLIMIT + log-limits doc for the strategy subprocesses. |
| `strategies/.gitignore` | Ignores runtime artifacts (`strategy_configs.json`, `strategy_env.json`, `.secure_env`, `scripts/*.py`). |
| `strategies/scripts/.gitignore` | Keeps `scripts/` in git but ignores uploaded `*.py`. |
| `strategies/examples/simple_ema_strategy.py` | Example EMA-crossover strategy using the `openalgo` SDK. |
| `strategies/examples/python/emacrossover_strategy_python.py` | Configurable EMA bot (WebSocket LTP + SL/Target exits). |
| `upgrade/migrate_flow.py` | Idempotent Flow tables migration (SQLite + PostgreSQL DDL, 5 indexes). |
| `upgrade/migrate_all.py` | Registers `migrate_flow.py` in the `MIGRATIONS` list (line 64). |
| `upgrade/rotate_pepper.py` | Re-encrypts `flow_workflows.api_key` on pepper rotation. |
| `upgrade/init_db.py` | Fresh-install DB bootstrap. |
| `utils/env_check.py` | Audits `flow_workflows.api_key` encryption health. |
| `examples/python/straddle_scheduler.py`, `straddle_with_stops.py` | Example scheduled strategies using APScheduler internally. |
| `mcp/mcpserver.py` | MCP orders default to strategy name `"python mcp"`. |

### 4.7 Frontend — Pages

| File | Role |
|---|---|
| `frontend/src/App.tsx` | Route table for `/strategy`, `/strategy/new`, `/strategy/:strategyId`, `/strategy/:strategyId/configure`, `/strategybuilder`, `/strategybuilder/portfolio`, `/tools/strategy*`, `/python*`, `/chartink*`, `/flow*`. |
| `frontend/src/pages/strategy/index.ts` | Barrel for the webhook-strategy pages. |
| `frontend/src/pages/strategy/StrategyIndex.tsx` | Strategy list; webhook URL copy; host config. |
| `frontend/src/pages/strategy/NewStrategy.tsx` | Create form (name, platform, trading mode). |
| `frontend/src/pages/strategy/ViewStrategy.tsx` | Strategy detail; enable/disable; delete; symbol mapping list. |
| `frontend/src/pages/strategy/ConfigureSymbols.tsx` | Two-tab symbol config (command search / CSV bulk). |
| `frontend/src/pages/python-strategy/index.ts` | Barrel. |
| `frontend/src/pages/python-strategy/PythonStrategyIndex.tsx` | Hosted-strategy cards + statuses. |
| `frontend/src/pages/python-strategy/NewPythonStrategy.tsx` | Upload form (name/file/exchange/schedule). |
| `frontend/src/pages/python-strategy/EditPythonStrategy.tsx` | Edit config (exchange, schedule). |
| `frontend/src/pages/python-strategy/PythonStrategyLogs.tsx` | Live logs (polls `/python/api/strategy/:id/logs`). |
| `frontend/src/pages/python-strategy/SchedulePythonStrategy.tsx` | Schedule editor (days, IST window, exchange). |
| `frontend/src/pages/python-strategy/PythonStrategyGuide.tsx` | 1,407-line user guide. |
| `frontend/src/pages/chartink/index.ts` | Barrel. |
| `frontend/src/pages/chartink/ChartinkIndex.tsx` | Chartink strategy list + webhook copy. |
| `frontend/src/pages/chartink/NewChartinkStrategy.tsx` | Create form (`strategy_type` intraday, times). |
| `frontend/src/pages/chartink/ViewChartinkStrategy.tsx` | Detail + toggle + delete + webhook copy. |
| `frontend/src/pages/chartink/ConfigureChartinkSymbols.tsx` | Symbol config for Chartink (NSE/BSE). |
| `frontend/src/pages/StrategyBuilder.tsx` | Options strategy builder (payoff/greeks/chart/OI/positions/PnL tabs). |
| `frontend/src/pages/StrategyPortfolio.tsx` | Saved strategies per watchlist; payoff thumbnail cards. |
| `frontend/src/pages/flow/FlowEditor.tsx` | Node-graph editor (drag-drop, save/activate/run/export). |
| `frontend/src/pages/flow/FlowIndex.tsx` | Workflow list; create/import; webhook config dialogs. |
| `frontend/src/pages/flow/FlowKeyboardShortcuts.tsx` | Shortcuts reference page. |

### 4.8 Frontend — API Modules

| File | Role |
|---|---|
| `frontend/src/api/strategy.ts` | `strategyApi`: CRUD, toggle, symbol mappings, search, webhook URL builder. |
| `frontend/src/api/python-strategy.ts` | `pythonStrategyApi`: upload, update, start/stop, logs/content, schedule. |
| `frontend/src/api/chartink.ts` | `chartinkApi`: CRUD, toggle, mappings, search, webhook URL. |
| `frontend/src/api/flow.ts` | Flow API: workflows, activate/deactivate, execute, executions, webhook config, export/import/replace, index-symbols; `flowQueryKeys`. |
| `frontend/src/api/strategy-chart.ts` | Strategy Builder chart endpoints (combined premium, intervals). |
| `frontend/src/api/strategy-portfolio.ts` | `strategyPortfolioApi.list` + `Watchlist` type. |

### 4.9 Frontend — Types, Lib, Stores

| File | Role |
|---|---|
| `frontend/src/types/strategy.ts` | `Strategy`, `StrategyPlatform`, `StrategySymbolMapping`, `SymbolSearchResult`, `AddSymbolRequest`; `STRATEGY_PLATFORMS`, `EXCHANGES`, `getProductTypes`, `TRADING_MODES`. |
| `frontend/src/types/python-strategy.ts` | `PythonStrategy` (+statuses), `PythonStrategyContent`, `LogFile`, `LogContent`, `STRATEGY_EXCHANGES`, `SCHEDULE_DAYS`. |
| `frontend/src/types/chartink.ts` | `ChartinkStrategy`, `ChartinkSymbolMapping`, `CHARTINK_EXCHANGES`, `CHARTINK_PRODUCTS`. |
| `frontend/src/types/flow.ts` | All node-data interfaces (triggers/actions/conditions/data/streaming/risk/utility), `NODE_TYPES`, `CustomNode`, `WorkflowState`, `SettingsState`. |
| `frontend/src/lib/strategyMath.ts` | Black-Scholes, payoff math, `probabilityOfProfit`, `payoffPriceRange`. |
| `frontend/src/lib/strategyMath.test.ts` | Vitest suite for the payoff math. |
| `frontend/src/lib/strategyTemplates.ts` | 38 option-strategy templates. |
| `frontend/src/lib/templateResolution.ts` | Expiry/strike/contract resolution for template legs. |
| `frontend/src/lib/flow/constants.ts` | Exchanges, product/price/action types, strike offsets, option strategies, indicators (116-catalog), node definitions, `DEFAULT_NODE_DATA`. |
| `frontend/src/stores/flowWorkflowStore.ts` | Zustand store for the Flow editor state. |
| `frontend/src/hooks/usePageTitle.ts` | Route-to-title map (incl. `/strategy*` entries). |

### 4.10 Frontend — Strategy Builder Components

All under `frontend/src/components/strategy-builder/`:

`TemplateGrid.tsx`, `TemplateDialog.tsx` (+ `.test.tsx`), `SymbolHeader.tsx`,
`StrategyChartTab.tsx`, `Simulators.tsx`, `SaveStrategyDialog.tsx`,
`PositionsPanel.tsx`, `PnLTab.tsx`, `PayoffChart.tsx` (+ `.test.tsx`),
`MultiStrikeOITab.tsx`, `ManualLegBuilder.tsx`, `GreeksTab.tsx`,
`EditLegDialog.tsx` (+ `.test.ts`).

### 4.11 Frontend — Flow Components

- **Panels** (`frontend/src/components/flow/panels/`): `index.ts` (barrel),
  `ConfigPanel.tsx` (3,840-line per-node config forms for all 63 node types),
  `ExecutionLogPanel.tsx`, `NodePalette.tsx`.
- **Edges** (`frontend/src/components/flow/edges/`): `index.ts`,
  `InsertableEdge.tsx` (midpoint "+" node insertion).
- **Nodes** (`frontend/src/components/flow/nodes/`): `index.ts` (registry) +
  `BaseNode.tsx` + 63 node components — StartNode, PriceAlertNode,
  WebhookTriggerNode, OrderUpdateTriggerNode, PlaceOrderNode, SmartOrderNode,
  OptionsOrderNode, OptionsMultiOrderNode, BasketOrderNode, SplitOrderNode,
  ModifyOrderNode, CancelOrderNode, CancelAllOrdersNode, ClosePositionsNode,
  PositionCheckNode, FundCheckNode, PriceConditionNode, VarConditionNode,
  TimeWindowNode, TimeConditionNode, And/Oх/NotGateNodes,
  GetQuoteNode, GetDepthNode, HistoryNode, IndicatorNode, StrategyPnlNode,
  PriorPeriodOhlcNode, BarOffsetNode, OpenPositionNode, GetOrderStatusNode,
  ExpiryNode, IntervalsNode, SymbolNode, OptionSymbolNode, OptionChainNode,
  SyntheticFutureNode, OrderBookNode, TradeBookNode, PositionBookNode,
  HoldingsNode, FundsNode, MarginNode, CalendarNode, TimingsNode, HolidaysNode,
  MultiQuotesNode, SubscribeLTPNode, SubscribeQuoteNode, SubscribeDepthNode,
  UnsubscribeNode, TelegramAlertNode, WhatsappAlertNode, DelayNode,
  WaitUntilNode, LogNode, VariableNode, MathExpressionNode, HttpRequestNode,
  GroupNode.

### 4.12 Frontend — Incidental (tag/label only)

- `frontend/src/lib/trading/terminal.ts:1715` — `OpenAlgoTradeFeed({ strategy: STRATEGY })`.
- `frontend/src/components/trading/PlaceOrderDialog.tsx` — `strategy` label default `'OptionChain'`.
- `frontend/src/components/trading/GttTab.tsx` — `strategy: 'GTT Modify'`.

### 4.13 Tests

| File | Role |
|---|---|
| `test/test_python_strategy_exchange_aware.py` | Calendar matrix, special sessions, crypto 24x7, MCX evening. |
| `test/test_python_strategy_edge_cases.py` | 25 edge cases: muhurat, manual-stop, per-exchange, restore, env, session boundary. |
| `test/test_flow_workflow_validator.py` | Node-type parity between backend and frontend. |
| `test/test_save_strategy.html` | Strategy save handbook/test page. |
| `frontend/src/lib/strategyMath.test.ts` | Strategy payoff math unit tests. |
| `frontend/src/components/strategy-builder/{TemplateDialog,PayoffChart,EditLegDialog}.test.*` | Builder component tests. |

---

## 5. Database Schema

All strategy tables live in the main **`openalgo.db`** except the Flow job store,
which lives in the **`flow`** database.

### `strategies` (`database/strategy_db.py`)
`id`, `name`, `webhook_id` (UUID unique), `user_id`, `platform`,
`is_active`, `is_intraday`, `trading_mode`, `start_time`, `end_time`,
`squareoff_time`, `created_at`, `updated_at`.

### `strategy_symbol_mappings` (`database/strategy_db.py`)
`id`, `strategy_id` (FK), `symbol`, `exchange`, `quantity`, `product_type`.

### `chartink_strategies` (`database/chartink_db.py`)
`id`, `name`, `webhook_id` (UUID unique), `user_id`, `is_active`,
`is_intraday`, `start_time`, `end_time`, `squareoff_time`, `created_at`,
`updated_at`.

### `chartink_symbol_mappings` (`database/chartink_db.py`)
`id`, `strategy_id` (FK), `chartink_symbol`, `exchange`, `quantity`,
`product_type`.

### `strategy_order_tags` (`database/strategy_book_db.py`)
`orderid` (unique) -> `user_id`, `strategy`, `symbol`, `exchange`, `product`,
`applied_quantity`, `applied_notional` (fill watermarks), timestamps.
Retention `STRATEGY_TAG_RETENTION_DAYS` (default 30).

### `strategy_pending_fills` (`database/strategy_book_db.py`)
Buffers fills arriving before their order tag (analyze-mode race). TTL
`STRATEGY_PENDING_FILL_TTL_MIN` (default 10 min), pruned by age.

### `strategy_positions` (`database/strategy_book_db.py`)
One row per `(user_id, strategy, symbol, exchange, product)` —
`quantity` (signed), `average_price`, `realized_pnl`, `today_realized_pnl`,
`trade_date` (IST session date). Unique constraint `uq_strategy_leg`.

### `strategy_portfolio` (`database/strategy_portfolio_db.py`)
`watchlist` (`mytrades`/`simulation`), `name`, `underlying`, `exchange`,
`expiry`, `legs_json`, `notes`. Single-user (no `user_id`).

### `flow_workflows` (`database/flow_db.py`)
`id`, `name`, `description`, `nodes` (JSON), `edges` (JSON), `is_active`,
`schedule_job_id`, `webhook_token` (unique), `webhook_secret`,
`webhook_enabled`, `webhook_auth_type` (`payload`/`url`), `api_key`
(Fernet-encrypted).

### `flow_workflow_executions` (`database/flow_db.py`)
`id`, `workflow_id` (FK), `status` (`pending`/`running`/`completed`/`failed`),
`started_at`, `completed_at`, `logs` (JSON node trace), `error`.

### `flow_apscheduler_jobs` (non-ORM, `flow` DB)
Auto-created by `SQLAlchemyJobStore` in `flow_scheduler_service.py` for
persistent scheduled Flow jobs.

---

## 6. Configuration (.env)

Strategy-related variables (from `.env` / `.sample.env` and code defaults):

| Variable | Default | Purpose |
|---|---|---|
| `WEBHOOK_RATE_LIMIT` | `"100 per minute"` | `/strategy/webhook` throttle. |
| `STRATEGY_RATE_LIMIT` | `"200 per minute"` | Strategy create/delete/webhook throttle. |
| `ORDER_RATE_LIMIT` | `"10 per second"` | `/api/v1/placeorder` throttle (webhook queue honors it). |
| `STRATEGY_LOG_MAX_FILES` | `10` | Max log files per Python strategy. |
| `STRATEGY_LOG_MAX_SIZE_MB` | `50` | Max total log size per strategy. |
| `STRATEGY_LOG_RETENTION_DAYS` | `7` | Delete logs older than N days. |
| `STRATEGY_MEMORY_LIMIT_MB` | `1024` | Subprocess virtual-memory cap (`RLIMIT_AS`, Unix/macOS). |
| `STRATEGY_TAG_RETENTION_DAYS` | `30` | Strategy-book order-tag retention. |
| `STRATEGY_PENDING_FILL_TTL_MIN` | `10` | Pending-fill buffer TTL. |
| `FLOW_PRICE_ALERT_WORKERS` | `4` | Price-monitor thread pool. |
| `FLOW_ORDER_UPDATE_WORKERS` | `4` | Order-update monitor worker pool. |
| `FLOW_MAX_HISTORY_BARS` | — | History-node bar cap. |
| `STRATEGY_CHART_LIMIT` | `"30 per minute"` | Strategy Builder chart throttle. |
| `STRATEGY_PORTFOLIO_READ_LIMIT` | `"60 per minute"` | Portfolio read throttle. |
| `STRATEGY_PORTFOLIO_WRITE_LIMIT` | `"20 per minute"` | Portfolio write throttle. |

---

## 7. Registration and Lifecycle

Boot wiring in `app.py` `setup_environment()` (~lines 700–799):

1. **DB init** (single-worker thread pool list): `init_strategy_db`,
   `init_flow_db` (via `chatink`/`strategy`/`flow`/`strategy_portfolio` inits).
2. **Strategy book boot**: 3-attempt `init_strategy_book_db()` +
   `register_strategy_book(bus)` **before** `app.db_ready.set()` so no order is
   untagged.
3. **`init_python_strategy()`** — starts the `/python` IST scheduler after DBs are
   ready.
4. **`init_flow_scheduler()`** — starts the Flow APScheduler (SQLAlchemy jobstore).
5. **`restore_order_update_watches()`** — re-arms Flow order-update triggers.

Blueprint registrations (`app.py` 304–338): `chartink_bp`, `strategy_bp`,
`python_strategy_bp`, `strategy_chart_bp`, `flow_bp`, `strategy_portfolio_bp`.

CSRF exemptions (`app.py` ~427–434): `strategy_bp.webhook`, `chartink_bp.webhook`,
`flow.trigger_webhook`, `flow.trigger_webhook_with_symbol`.

Runtime invariants that protect all strategy surfaces:

- **SQLite `NullPool`** everywhere (#1 connector-safety rule); every DB engine via
  `database/engine_factory.create_db_engine()`.
- **Eventlet/gunicorn in production**: no `asyncio` in strategy code; threading
  queues and APScheduler background threads are the pattern.
- **`upsert_auth` teardown gating**: a same-day 2nd-device login must NOT tear down
  the shared broker feed that live strategies (`/python`, Flow streaming) consume.

---

## 8. Existing Documentation Map

Canonical per-feature docs (edit those, not this file, for authoritative detail):

- Design: `docs/design/39-strategy-module/README.md`, `docs/design/10-flow-architecture/README.md`, `docs/design/13-chartink/README.md`, `docs/design/53-event-bus/README.md`, `docs/design/01-frontend/README.md`, `docs/design/42-action-center/README.md`
- PRDs: `docs/prd/flow.md`, `flow-execution.md`, `flow-node-reference.md`, `flow-node-creation.md`, `flow-ui-components.md`, `python-strategies.md`, `python-strategies-scheduling.md`, `python-strategies-process-management.md`, `python-strategies-api-reference.md`
- BDD: `docs/bdd/flow_workflows.feature`, `docs/bdd/automation_webhooks.feature`
- API / rate limits: `docs/api/rate-limiting.md`, `docs/api/order-management/basketorder.md`, `cancelallorder.md`, `cancelgttorder.md`, order-information docs
- Import format: `docs/prompt/flow-import-format.md`, `docs/prompt/services_documentation.md`
- Runtime host docs: `strategies/README.md`, `strategies/RESOURCE_LIMITS.md`
- Release notes: `docs/CHANGELOG.md`
- Master index: `docs/INDEX.md`