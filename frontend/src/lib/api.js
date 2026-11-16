/**
 * API client for the Ai_Quant FastAPI backend (auth removed — open API).
 *
 * Every response shape here is taken verbatim from the backend contract:
 *   app/routers/chat.py, app/routers/strategies.py, app/schemas.py
 * Nothing in this file invents an endpoint — if the backend does not expose
 * it, the UI does not call it.
 */

// Dev server: go through the Vite proxy (/api -> localhost:8000), which
// sidesteps CORS entirely. Production build: hit the API directly (CORS
// allows the deployed frontend origin).
// VITE_API_BASE_URL is the deploy-time override (Vercel/Render);
// VITE_API_BASE is the Dockerfile build-arg name.

export const API_BASE = (() => {
  const raw =
    import.meta.env.VITE_API_BASE_URL ||
    import.meta.env.VITE_API_BASE ||
    (import.meta.env.DEV ? '/api' : 'http://localhost:8000')
  // Normalize to avoid double /api prefixes in production deployments.
  // Only strip trailing /api for absolute URLs; keep relative '/api' for Vite dev proxy.
  if (typeof raw === 'string' && /^https?:\/\//i.test(raw)) {
    return raw.replace(/\/api\/?$/, '')
  }
  return raw
})()

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

function buildHeaders(body) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  return headers
}

async function doFetch(path, { method, body, signal }) {
  return fetch(`${API_BASE}${path}`, {
    method,
    signal,
    headers: buildHeaders(body),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

async function request(path, { method = 'GET', body, signal } = {}) {
  let response
  try {
    response = await doFetch(path, { method, body, signal })
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
  const slippagePct = Number(params?.slippagePct ?? 0)

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
  if (!Number.isFinite(slippagePct) || slippagePct < 0 || slippagePct >= 100) {
    throw new ApiError('Slippage must be a percentage between 0 and 100.', { status: 422 })
  }

  return { cash, commission_pct: commissionPct, sizer_percents: sizerPercent, slippage_pct: slippagePct }
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

/**
 * POST /strategies/{id}/approve. The backend derives the decision from the
 * stored backtest and declares no body parameter, so we send none — no
 * Content-Type either, which is correct for a bodyless POST. A refusal comes
 * back as 422 { detail: { reasons: [...] } } and is rendered by describeError.
 */
export function approveStrategy(strategyId, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/approve`, {
    method: 'POST',
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

/** GET /strategies — list strategies for current user. */
export function fetchStrategies({ signal } = {}) {
  return request('/strategies/', { signal })
}

/** GET /strategies/{id}/deployments — newest first. */
export function fetchDeployments(strategyId, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/deployments`, { signal })
}

/* ------------------------------------------------ paper trading (simulated) */

/** GET /paper/deployments — every deployment across strategies, active first. */
export function fetchAllPaperDeployments({ signal } = {}) {
  return request('/paper/deployments', { signal })
}

/** GET /strategies/{id}/paper-account — authoritative virtual-account snapshot. */
export function fetchPaperAccount(strategyId, { deploymentId, signal } = {}) {
  const query = deploymentId ? `?deployment_id=${encodeURIComponent(deploymentId)}` : ''
  return request(`/strategies/${encodeURIComponent(strategyId)}/paper-account${query}`, {
    signal,
  })
}

/** GET /strategies/{id}/paper-positions — open simulated positions. */
export function fetchPaperPositions(strategyId, { deploymentId, signal } = {}) {
  const query = deploymentId ? `?deployment_id=${encodeURIComponent(deploymentId)}` : ''
  return request(`/strategies/${encodeURIComponent(strategyId)}/paper-positions${query}`, {
    signal,
  })
}

/** GET /strategies/{id}/paper-orders — simulated order ledger, rejected included. */
export function fetchPaperOrders(strategyId, { deploymentId, signal } = {}) {
  const query = deploymentId ? `?deployment_id=${encodeURIComponent(deploymentId)}` : ''
  return request(`/strategies/${encodeURIComponent(strategyId)}/paper-orders${query}`, {
    signal,
  })
}

/** GET /strategies/{id}/paper-trades — completed simulated round-trips. */
export function fetchPaperTrades(strategyId, { deploymentId, signal } = {}) {
  const query = deploymentId ? `?deployment_id=${encodeURIComponent(deploymentId)}` : ''
  return request(`/strategies/${encodeURIComponent(strategyId)}/paper-trades${query}`, {
    signal,
  })
}

/** GET /strategies/{id}/market-bars — processed-period OHLC, oldest first, read-only. */
export function fetchMarketBars(strategyId, { deploymentId, signal } = {}) {
  const query = deploymentId ? `?deployment_id=${encodeURIComponent(deploymentId)}` : ''
  return request(`/strategies/${encodeURIComponent(strategyId)}/market-bars${query}`, {
    signal,
  })
}

/** GET /paper/deployments/{id}/equity-snapshots — chronological portfolio equity snapshots. */
export function fetchPaperEquitySnapshots(deploymentId, { signal } = {}) {
  return request(`/paper/deployments/${encodeURIComponent(deploymentId)}/equity-snapshots`, { signal })
}

/**
 * POST /strategies/{id}/paper-tick — advance exactly the next cached bar
 * through the deployed strategy's simulation. `deploymentId` pins the tick
 * to one deployment so one row can never advance another. No LLM, no broker.
 * (The backend retains an optional `barDate` for tests only; the normal UI
 * never sends it so chronology cannot be skipped.)
 */
export function runPaperTick(strategyId, { deploymentId, signal } = {}) {
  const body = {}
  if (deploymentId) body.deployment_id = deploymentId
  return request(`/strategies/${encodeURIComponent(strategyId)}/paper-tick`, {
    method: 'POST',
    body,
    signal,
  })
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

export function fetchBacktestResults(strategyId, { signal } = {}) {
  return request(`/strategies/${encodeURIComponent(strategyId)}/backtest-results`, { signal })
}

/** True when the server could not be reached at all. */
export function isNetworkError(err) {
  return err instanceof ApiError && err.status === 0
}

/** Kept for old imports — the open API never answers 401/403. */
export function isAuthError() {
  return false
}

/* ------------------------------------------------ conversations & projects */

/** GET /conversations/projects — list all projects for current user. */
export function fetchProjects({ signal } = {}) {
  return request('/conversations/projects', { signal })
}

/** POST /conversations/projects — create a new project. */
export function createProject({ name, description }, { signal } = {}) {
  return request('/conversations/projects', {
    method: 'POST',
    body: { name, description },
    signal,
  })
}

/** PATCH /conversations/projects/{id} — update a project. */
export function updateProject(projectId, { name, description }, { signal } = {}) {
  return request(`/conversations/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH',
    body: { name, description },
    signal,
  })
}

/** DELETE /conversations/projects/{id} — delete a project. */
export function deleteProject(projectId, { moveConversations = true }, { signal } = {}) {
  const query = moveConversations ? '?move_conversations=true' : '?move_conversations=false'
  return request(`/conversations/projects/${encodeURIComponent(projectId)}${query}`, {
    method: 'DELETE',
    signal,
  })
}

/** GET /conversations — list all conversations for current user. */
export function fetchConversations({ projectId, status, signal } = {}) {
  const params = new URLSearchParams()
  if (projectId) params.set('project_id', projectId)
  if (status) params.set('status', status)
  const query = params.toString() ? `?${params.toString()}` : ''
  return request(`/conversations${query}`, { signal })
}

/** POST /conversations — create a new conversation. */
export function createConversation({ title, projectId }, { signal } = {}) {
  return request('/conversations', {
    method: 'POST',
    body: { title, project_id: projectId },
    signal,
  })
}

/** GET /conversations/{id} — get a conversation with full message history. */
export function fetchConversation(conversationId, { signal } = {}) {
  return request(`/conversations/${encodeURIComponent(conversationId)}`, { signal })
}

/** PATCH /conversations/{id} — update a conversation (title, project, status). */
export function updateConversation(conversationId, { title, projectId, status }, { signal } = {}) {
  return request(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'PATCH',
    body: { title, project_id: projectId, status },
    signal,
  })
}

/** POST /conversations/{id}/move — move a conversation to a different project. */
export function moveConversation(conversationId, { projectId }, { signal } = {}) {
  return request(`/conversations/${encodeURIComponent(conversationId)}/move`, {
    method: 'POST',
    body: { project_id: projectId },
    signal,
  })
}

/** DELETE /conversations/{id} — delete a conversation. */
export function deleteConversation(conversationId, { signal } = {}) {
  return request(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
    signal,
  })
}

/** POST /conversations/{id}/archive — archive a conversation. */
export function archiveConversation(conversationId, { signal } = {}) {
  return request(`/conversations/${encodeURIComponent(conversationId)}/archive`, {
    method: 'POST',
    signal,
  })
}

/** POST /conversations/{id}/restore — restore an archived conversation. */
export function restoreConversation(conversationId, { signal } = {}) {
  return request(`/conversations/${encodeURIComponent(conversationId)}/restore`, {
    method: 'POST',
    signal,
  })
}

/* ------------------------------------------------ dashboard */

/** GET /dashboard/market/overview — major Indian indices + market status. */
export function fetchMarketOverview({ signal } = {}) {
  return request('/dashboard/market/overview', { signal })
}

/** GET /dashboard/market/quote/{symbol} — detailed quote for one index. */
export function fetchMarketQuote(symbol, { signal } = {}) {
  return request(`/dashboard/market/quote/${encodeURIComponent(symbol)}`, { signal })
}

/** GET /dashboard/market/indicators/{symbol} — technical indicators for a symbol. */
export function fetchMarketIndicators(symbol, { timeframe = '1d', limit = 500, signal } = {}) {
  const params = new URLSearchParams({ timeframe, limit: String(limit) })
  return request(`/dashboard/market/indicators/${encodeURIComponent(symbol)}?${params}`, { signal })
}

/** GET /dashboard/market/chart/{symbol} — historical chart data. */
export function fetchMarketChart(symbol, { timeframe = '1d', limit = 500, signal } = {}) {
  const params = new URLSearchParams({ timeframe, limit: String(limit) })
  return request(`/dashboard/market/chart/${encodeURIComponent(symbol)}?${params}`, { signal })
}

/** GET /dashboard/market/pulse — gainers, losers, active, sectors, breadth. */
export function fetchMarketPulse({ signal } = {}) {
  return request('/dashboard/market/pulse', { signal })
}

/** GET /dashboard/market/news — Indian financial market news. */
export function fetchMarketNews({ limit = 20, signal } = {}) {
  return request(`/dashboard/market/news?limit=${limit}`, { signal })
}

/** POST /dashboard/ai/briefing — structured AI-generated market briefing. */
export function fetchAIBriefing({ mode = 'concise', force = false, signal } = {}) {
  return request('/dashboard/ai/briefing', { method: 'POST', body: { mode, force }, signal })
}

/** GET /dashboard/simulation — truthful monitor of the existing paper engine. */
export function fetchDashboardSimulation({ signal } = {}) {
  return request('/dashboard/simulation', { signal })
}

/** GET /dashboard/performance/summary — trading performance metrics. */
export function fetchPerformanceSummary({ signal } = {}) {
  return request('/dashboard/performance/summary', { signal })
}

/** GET /dashboard/strategies — user strategies with backtest/deployment info. */
export function fetchDashboardStrategies({ status, signal } = {}) {
  const params = status ? `?status_filter=${encodeURIComponent(status)}` : ''
  return request(`/dashboard/strategies${params}`, { signal })
}

/** GET /dashboard/paper/portfolio — consolidated paper trading portfolio. */
export function fetchPaperPortfolio({ signal } = {}) {
  return request('/dashboard/paper/portfolio', { signal })
}

/** GET /dashboard/activity/recent — recent user activity. */
export function fetchRecentActivity({ limit = 20, signal } = {}) {
  return request(`/dashboard/activity/recent?limit=${limit}`, { signal })
}

// ============================================================
// Market News Hub — /news
// ============================================================

function newsQuery(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** GET /news/ — stored articles with filters. Never triggers ingestion. */
export function fetchNews(
  {
    region,
    category,
    sourceType,
    sentiment,
    ticker,
    q,
    minCredibility,
    hours = 168,
    sort = 'recent',
    limit = 40,
    offset = 0,
    signal,
  } = {},
) {
  const params = newsQuery({
    region,
    category,
    source_type: sourceType,
    sentiment,
    ticker,
    q,
    min_credibility: minCredibility,
    hours,
    sort,
    limit,
    offset,
  })
  return request(`/news/${params}`, { signal })
}

/** GET /news/overview — counts, top stories and sentiment for the header. */
export function fetchNewsOverview({ hours = 48, signal } = {}) {
  return request(`/news/overview${newsQuery({ hours })}`, { signal })
}

/** GET /news/trending — most-mentioned tickers with a trend direction. */
export function fetchNewsTrending({ hours = 24, limit = 10, signal } = {}) {
  return request(`/news/trending${newsQuery({ hours, limit })}`, { signal })
}

/** GET /news/sentiment — aggregate sentiment, split for official vs community. */
export function fetchNewsSentiment({ hours = 48, signal } = {}) {
  return request(`/news/sentiment${newsQuery({ hours })}`, { signal })
}

/** GET /news/sources — registry, credibility scale and missing credentials. */
export function fetchNewsSources({ signal } = {}) {
  return request('/news/sources', { signal })
}

/** POST /news/refresh — run one ingestion pass. */
export function refreshNews({ force = true, providers, signal } = {}) {
  const params = newsQuery({ force, providers })
  return request(`/news/refresh${params}`, { method: 'POST', signal })
}

