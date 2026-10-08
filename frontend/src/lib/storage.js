/**
 * localStorage registry.
 *
 * The backend has NO list endpoint and NO endpoint to read back stored
 * backtest results or chat history, so this browser-local cache is the only
 * place that history can live. Everything is wrapped in try/catch because
 * localStorage throws in private-mode Safari, when the quota is full, and
 * when it is disabled entirely.
 */

const THREAD_KEY = 'aiq.thread.v1'
const STRATEGIES_KEY = 'aiq.strategies.v1'
const BACKTESTS_KEY = 'aiq.backtests.v1'
const SCOPED_KEYS = [THREAD_KEY, STRATEGIES_KEY, BACKTESTS_KEY]

/** Legacy prototype flags from before Supabase auth. */
const LEGACY_FLAGS = ['isLoggedIn', 'aiq.userName']

/**
 * Multi-tenant isolation: every key is namespaced by the active user's id
 * (`aiq.strategies.v1.<userId>`), so two accounts on the same browser can
 * never read each other's thread, strategy list, or cached backtests.
 * With no active user (logged out) reads return empty and writes are
 * dropped — nothing renders without an owner.
 */
let activeUserId = null

export function setActiveUserId(userId) {
  const next = userId || null
  if (next === activeUserId) return
  activeUserId = next
  if (next) migrateLegacyKeys()
}

export function getActiveUserId() {
  return activeUserId
}

function scopedKey(base) {
  return activeUserId ? `${base}.${activeUserId}` : null
}

/**
 * One-time upgrade: pre-isolation data lived under the bare keys. On the
 * first login after this change, adopt it into the new owner's namespace
 * instead of orphaning it, then delete the shared copy.
 */
function migrateLegacyKeys() {
  const store = storage()
  if (!store) return
  for (const base of SCOPED_KEYS) {
    try {
      if (store.getItem(scopedKey(base)) !== null) continue
      const legacy = store.getItem(base)
      if (legacy === null) continue
      store.setItem(scopedKey(base), legacy)
      store.removeItem(base)
    } catch {
      /* storage unavailable — scoped reads simply start empty */
    }
  }
}

function removeKey(key) {
  const store = storage()
  if (!store) return
  try {
    store.removeItem(key)
  } catch {
    /* ignore */
  }
}

/**
 * Logout wipe: delete the outgoing user's entire browser cache plus any
 * legacy shared keys/flags, so the next login — by anyone — starts from a
 * guaranteed-empty slate. Called by AuthContext.logout before sign-out.
 */
export function clearActiveUserData() {
  if (activeUserId) {
    for (const base of SCOPED_KEYS) removeKey(`${base}.${activeUserId}`)
  }
  for (const base of SCOPED_KEYS) removeKey(base)
  for (const flag of LEGACY_FLAGS) removeKey(flag)
  activeUserId = null
}

/** Chat transcript is trimmed to this many turns to survive tight quotas. */
const MAX_THREAD_MESSAGES = 200
/** Keep at most this many cached backtest payloads. */
const MAX_CACHED_BACKTESTS = 20

function storage() {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null
    return window.localStorage
  } catch {
    return null
  }
}

function readRaw(key) {
  const store = storage()
  if (!store) return null
  try {
    return store.getItem(key)
  } catch {
    return null
  }
}

function isQuotaError(err) {
  if (!err) return false
  return (
    err.name === 'QuotaExceededError' ||
    err.name === 'NS_ERROR_DOM_QUOTA_REACHED' ||
    err.code === 22 ||
    err.code === 1014
  )
}

function writeRaw(key, value) {
  const store = storage()
  if (!store) return false
  try {
    store.setItem(key, JSON.stringify(value))
    return true
  } catch (err) {
    if (isQuotaError(err)) return false
    return false
  }
}

/** Quota failures are non-fatal; callers fall back to in-memory state. */
export function isStorageAvailable() {
  const store = storage()
  if (!store) return false
  const probe = '__aiq_probe__'
  try {
    store.setItem(probe, '1')
    store.removeItem(probe)
    return true
  } catch {
    return false
  }
}

/* ------------------------------------------------------------------ thread */

function sanitizeMessage(raw) {
  if (!raw || typeof raw !== 'object') return null
  if (raw.role !== 'user' && raw.role !== 'assistant') return null
  if (typeof raw.content !== 'string') return null
  const message = {
    id: typeof raw.id === 'string' ? raw.id : Math.random().toString(36).slice(2),
    role: raw.role,
    content: raw.content,
    createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : new Date().toISOString(),
  }
  if (raw.strategy && typeof raw.strategy.strategy_id === 'string') {
    message.strategy = {
      strategy_id: raw.strategy.strategy_id,
      strategy_name:
        typeof raw.strategy.strategy_name === 'string' ? raw.strategy.strategy_name : 'Untitled Strategy',
      strategy_description:
        typeof raw.strategy.strategy_description === 'string' ? raw.strategy.strategy_description : null,
    }
  }
  return message
}

export function readThread() {
  const key = scopedKey(THREAD_KEY)
  if (!key) return { conversationId: null, messages: [] }
  const raw = readRaw(key)
  if (!raw) return { conversationId: null, messages: [] }
  try {
    const parsed = JSON.parse(raw)
    const messages = Array.isArray(parsed?.messages)
      ? parsed.messages.map(sanitizeMessage).filter(Boolean)
      : []
    return {
      conversationId: typeof parsed?.conversationId === 'string' ? parsed.conversationId : null,
      messages,
    }
  } catch {
    return { conversationId: null, messages: [] }
  }
}

export function writeThread(thread) {
  const key = scopedKey(THREAD_KEY)
  if (!key) return false
  const messages = (thread.messages ?? []).slice(-MAX_THREAD_MESSAGES)
  const ok = writeRaw(key, { conversationId: thread.conversationId ?? null, messages })
  if (ok) return true
  // Quota hit: retry once with the oldest half of the transcript dropped.
  return writeRaw(key, {
    conversationId: thread.conversationId ?? null,
    messages: messages.slice(Math.floor(messages.length / 2)),
  })
}

export function clearThread() {
  const key = scopedKey(THREAD_KEY)
  if (!key) return
  removeKey(key)
}

/* -------------------------------------------------------------- strategies */

function sanitizeStrategyEntry(raw) {
  if (!raw || typeof raw !== 'object') return null
  if (typeof raw.id !== 'string' || !raw.id) return null
  return {
    id: raw.id,
    name: typeof raw.name === 'string' && raw.name ? raw.name : 'Untitled Strategy',
    description: typeof raw.description === 'string' ? raw.description : null,
    createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : new Date().toISOString(),
  }
}

export function readStrategies() {
  const key = scopedKey(STRATEGIES_KEY)
  if (!key) return []
  const raw = readRaw(key)
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const seen = new Set()
    return parsed
      .map(sanitizeStrategyEntry)
      .filter((entry) => {
        if (!entry || seen.has(entry.id)) return false
        seen.add(entry.id)
        return true
      })
  } catch {
    return []
  }
}

/**
 * Records a strategy id created in this browser. Idempotent: re-registering a
 * known id only refreshes the cached name/description.
 */
export function registerStrategy({ id, name, description }) {
  if (!id) return readStrategies()
  const key = scopedKey(STRATEGIES_KEY)
  if (!key) return []
  const existing = readStrategies()
  const index = existing.findIndex((entry) => entry.id === id)
  const entry = {
    id,
    name: name || 'Untitled Strategy',
    description: description ?? null,
    createdAt: index >= 0 ? existing[index].createdAt : new Date().toISOString(),
  }
  const next = index >= 0 ? existing.map((e, i) => (i === index ? entry : e)) : [entry, ...existing]
  const ok = writeRaw(key, next)
  if (!ok) {
    // Retry after pruning cached backtests, which are the heaviest payload.
    pruneBacktests(5)
    writeRaw(key, next)
  }
  return next
}

export function removeStrategy(id) {
  const key = scopedKey(STRATEGIES_KEY)
  if (!key) return []
  const next = readStrategies().filter((entry) => entry.id !== id)
  writeRaw(key, next)
  return next
}

/* --------------------------------------------------------------- backtests */

/** raw_metrics is a full analyzer dump; it is dropped to save quota. */
function stripForCache(result) {
  const rest = { ...(result ?? {}) }
  delete rest.raw_metrics
  return {
    ...rest,
    trades: Array.isArray(rest.trades) ? rest.trades.slice(0, 500) : [],
    equity_curve: Array.isArray(rest.equity_curve) ? rest.equity_curve.slice(0, 400) : [],
    warnings: Array.isArray(rest.warnings) ? rest.warnings : [],
  }
}

function readBacktests() {
  const key = scopedKey(BACKTESTS_KEY)
  if (!key) return {}
  const raw = readRaw(key)
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed
  } catch {
    return {}
  }
}

/** Oldest first, so `keep` implies dropping the least recently run ones. */
function pruneBacktests(keep) {
  const key = scopedKey(BACKTESTS_KEY)
  if (!key) return
  const all = readBacktests()
  const ids = Object.keys(all).sort(
    (a, b) => new Date(all[a]?.ranAt ?? 0).getTime() - new Date(all[b]?.ranAt ?? 0).getTime(),
  )
  const next = {}
  for (const id of ids.slice(Math.max(0, ids.length - Math.max(0, keep)))) next[id] = all[id]
  writeRaw(key, next)
}

export function getCachedBacktest(strategyId) {
  if (!strategyId) return null
  const entry = readBacktests()[strategyId]
  if (!entry || typeof entry.ranAt !== 'string' || !entry.result) return null
  return entry
}

export function setCachedBacktest(strategyId, result) {
  if (!strategyId || !result) return false
  const key = scopedKey(BACKTESTS_KEY)
  if (!key) return false
  const all = readBacktests()
  const next = {
    ...all,
    [strategyId]: { ranAt: new Date().toISOString(), result: stripForCache(result) },
  }
  const ids = Object.keys(next)
  if (ids.length > MAX_CACHED_BACKTESTS) {
    const ordered = ids.sort(
      (a, b) => new Date(all[b]?.ranAt ?? 0).getTime() - new Date(all[a]?.ranAt ?? 0).getTime(),
    )
    for (const id of ordered.slice(MAX_CACHED_BACKTESTS)) delete next[id]
  }
  return writeRaw(key, next)
}

export function removeCachedBacktest(strategyId) {
  const key = scopedKey(BACKTESTS_KEY)
  if (!key) return
  const all = readBacktests()
  if (!(strategyId in all)) return
  delete all[strategyId]
  writeRaw(key, all)
}