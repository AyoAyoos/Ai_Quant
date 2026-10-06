/**
 * API client for the Ai_Quant FastAPI backend.
 *
 * Every response shape here is taken verbatim from the backend contract:
 *   app/routers/chat.py, app/routers/strategies.py, app/schemas.py
 * Nothing in this file invents an endpoint — if the backend does not expose
 * it, the UI does not call it.
 */

// Dev server: go through the Vite proxy (/api -> localhost:8000), which
// sidesteps CORS entirely. Production build: hit the API directly (CORS
// allows the deployed frontend origin).
export const API_BASE =
  import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? '/api' : 'http://localhost:8000')

/** Backend caps the backtest worker at 120s wall clock (504 on expiry). */
export const BACKTEST_TIMEOUT_MS = 120_000
/** LLM chat is slow (30-90s typical); only give up past 150s. */
export const CHAT_TIMEOUT_MS = 150_000
/** How often the header polls /health. */
export const HEALTH_POLL_MS = 15_000

export class ApiError extends Error {
  constructor(message, { status, reasons } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status ?? 0
    this.reasons = reasons ?? []
  }
}

function joinReasons(detail) {
  if (detail && typeof detail === 'object' && Array.isArray(detail.reasons)) {
    return detail.reasons.filter((r) => typeof r === 'string' && r.trim())
  }
  return []
}

/**
 * THE shared error normaliser. 422 arrives in two shapes:
 *   - gate transitions  -> { detail: { reasons: [...] } }
 *   - backtest / params -> { detail: "refused import: os" }
 * Both must render readably, so every call funnels through here.
 */
export function describeError(body, status) {
  const reasons = joinReasons(body?.detail)
  if (reasons.length > 0) return { message: reasons.join('; '), reasons }

  const detail = body?.detail
  if (typeof detail === 'string' && detail.trim()) return { message: detail, reasons: [] }
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI request-validation errors: [{loc, msg, type}, ...]
    const msg = detail
      .map((d) => {
        const field = Array.isArray(d?.loc) ? d.loc.filter((x) => x !== 'body').join('.') : ''
        const text = typeof d?.msg === 'string' ? d.msg : 'invalid value'
        return field ? `${field}: ${text}` : text
      })
      .join('; ')
    if (msg) return { message: msg, reasons: [] }
  }
  return { message: `Request failed (${status})`, reasons: [] }
}

const NETWORK_MESSAGE = 'Error reaching the backend. Is it running?'

async function request(path, { method = 'GET', body, signal } = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      signal,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (err) {
    if (err?.name === 'AbortError') throw err
    throw new ApiError(NETWORK_MESSAGE, { status: 0 })
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const { message, reasons } = describeError(payload, response.status)
    throw new ApiError(message, { status: response.status, reasons })
  }
  return payload
}

/** GET /health -> { status: "ok" }. Used by the header connectivity dot. */
export async function fetchHealth({ signal } = {}) {
  return request('/health', { signal })
}

/**
 * POST /chat. First message of a thread sends conversation_id: null;
 * every later message echoes back the id the backend returned.
 */
export function postChat({ conversationId, content, signal }) {
  return request('/chat', {
    method: 'POST',
    body: { conversation_id: conversationId ?? null, content },
    signal,
  })
}

/** GET /strategies/{id} — the source of truth for status. */
export function fetchStrategy(strategyId, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}`, { signal })
}

/**
 * Build the JSON body for the two endpoints that take money knobs
 * (POST /strategies/{id}/backtest and /deploy).
 *
 * `commission_pct` and `sizer_percents` are PERCENTAGES in (0, 100), not
 * decimal ratios — 20 means 20% and 0.2 means 0.2% (the backend converts with
 * `pct / 100`). The backend schema is `Field(gt=0, lt=100)`, so anything
 * non-numeric, empty or out of range would come back as a 422; coerce and
 * check here instead so the caller gets a readable message.
 */
function capitalBody(params) {
  const cash = Number(params?.cash)
  const commissionPct = Number(params?.commissionPct)
  const sizerPercent = Number(params?.sizerPercent)

  if (!Number.isFinite(cash) || cash <= 0) {
    throw new ApiError('Starting cash must be a number greater than 0.', { status: 422 })
  }
  if (!Number.isFinite(commissionPct) || commissionPct <= 0 || commissionPct >= 100) {
    throw new ApiError('Commission must be a percentage greater than 0 and less than 100.', {
      status: 422,
    })
  }
  if (!Number.isFinite(sizerPercent) || sizerPercent <= 0 || sizerPercent >= 100) {
    throw new ApiError('Position size must be a percentage greater than 0 and less than 100.', {
      status: 422,
    })
  }

  return { cash, commission_pct: commissionPct, sizer_percents: sizerPercent }
}

/**
 * POST /strategies/{id}/backtest.
 * `data_path` is deliberately never sent: the UI has no use for it and the
 * backend auto-fetches + caches NIFTY 50 when it is omitted.
 */
export function runBacktest(strategyId, params, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/backtest`, {
    method: 'POST',
    body: capitalBody(params),
    signal,
  })
}

export function approveStrategy(strategyId, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/approve`, {
    method: 'POST',
    body: {},
    signal,
  })
}

export function rejectStrategy(strategyId, reason, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/reject`, {
    method: 'POST',
    body: { reason },
    signal,
  })
}

export function deployStrategy(strategyId, params, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/deploy`, {
    method: 'POST',
    body: capitalBody(params),
    signal,
  })
}

export function stopDeployment(strategyId, reason, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/stop`, {
    method: 'POST',
    body: { reason: reason ? reason : null },
    signal,
  })
}

/** GET /strategies/{id}/deployments — newest first. */
export function fetchDeployments(strategyId, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/deployments`, { signal })
}

/**
 * POST /strategies/builder - structured strategy builder endpoint.
 * Sends a complete strategy specification and receives a generated draft
 * strategy ({ strategy_id, generated_code, strategy_specification, ... }).
 */
export function generateStrategy(spec, { signal } = {}) {
  return request('/strategies/builder', {
    method: 'POST',
    body: spec,
    signal,
  })
}

/** True when the failure means "this strategy id no longer exists". */
export function isNotFound(err) {
  return err instanceof ApiError && err.status === 404
}

/** True when the server could not be reached at all. */
export function isNetworkError(err) {
  return err instanceof ApiError && err.status === 0
}