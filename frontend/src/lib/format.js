/**
 * Display formatters and metric semantics.
 *
 * Two backend quirks are encoded here on purpose (see README "Data-quality
 * rules"): max drawdown is reported as a POSITIVE severity number, and the
 * backend's `no_trades` warning is a machine token, not a sentence.
 */

const EM_DASH = '—'

function isNum(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

const int0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

/** Any null / undefined / NaN metric renders as an em dash, never "NaN". */
export function formatNumber(value, digits = 2) {
  if (!isNum(value)) return EM_DASH
  return value.toFixed(digits)
}

export function formatPercent(value, digits = 2) {
  if (!isNum(value)) return EM_DASH
  return `${value.toFixed(digits)}%`
}

export function formatRatio(value) {
  if (!isNum(value)) return EM_DASH
  return value.toFixed(2)
}

export function formatInt(value) {
  if (!isNum(value)) return EM_DASH
  return int0.format(value)
}

/** Prices, cash values and equity points: whole units, grouped. */
export function formatMoney(value) {
  if (!isNum(value)) return EM_DASH
  return int0.format(Math.round(value))
}

/** P&L: whole units with an explicit "+" on gains so the sign is unambiguous. */
export function formatSignedMoney(value) {
  if (!isNum(value)) return EM_DASH
  const rounded = Math.round(value)
  const body = int0.format(Math.abs(rounded))
  if (rounded > 0) return `+${body}`
  if (rounded < 0) return `-${body}`
  return body
}

/** Accepts '2024-09-30', a full ISO timestamp, or a Date. */
export function formatDate(value) {
  const date = toDate(value)
  if (!date) return EM_DASH
  return date.toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: '2-digit' })
}

export function formatDateIso(value) {
  const date = toDate(value)
  if (!date) return EM_DASH
  return date.toISOString().slice(0, 10)
}

/** Local wall-clock stamp, used for "Result from ..." and deployment times. */
export function formatDateTime(value) {
  const date = toDate(value)
  if (!date) return EM_DASH
  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

export function formatTime(value) {
  const date = toDate(value)
  if (!date) return EM_DASH
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function toDate(value) {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value !== 'string' || !value.trim()) return null
  // Bare 'YYYY-MM-DD' parses as UTC midnight and can slip a day in
  // negative-offset zones; build it in local time instead.
  const bare = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (bare) {
    return new Date(Number(bare[1]), Number(bare[2]) - 1, Number(bare[3]))
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatElapsed(seconds) {
  if (!isNum(seconds) || seconds < 0) return '0s'
  const whole = Math.floor(seconds)
  if (whole < 60) return `${whole}s`
  const minutes = Math.floor(whole / 60)
  return `${minutes}m ${String(whole % 60).padStart(2, '0')}s`
}

export function truncate(text, max) {
  if (typeof text !== 'string') return ''
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= max) return clean
  return `${clean.slice(0, Math.max(0, max - 1)).trimEnd()}…`
}

/* --------------------------------------------------------------- semantics */

/** The single place that decides metric colour. */
export function metricTone(kind, value) {
  if (!isNum(value)) return 'neutral'

  switch (kind) {
    case 'return':
    case 'cagr':
      if (value > 0) return 'positive'
      if (value < 0) return 'negative'
      return 'neutral'

    case // Drawdown arrives POSITIVE and grows with severity. Never test "< 0".
    'drawdown': {
      const severity = Math.abs(value)
      if (severity === 0) return 'neutral'
      if (severity <= 10) return 'caution'
      if (severity <= 25) return 'severe'
      return 'critical'
    }

    case 'benchmark':
      return 'neutral'

    case 'ratio':
    default:
      return 'neutral'
  }
}

/**
 * Buy & hold comparison. Green is only ever shown for a strategy that also
 * made money: beating a falling benchmark while losing is not a win.
 */
export function benchmarkVerdict(result) {
  const total = result?.total_return_pct
  const bench = result?.benchmark_return_pct
  if (!isNum(total) || !isNum(bench)) return { tone: 'none', text: null, delta: null }

  const delta = total - bench
  const points = formatPercent(Math.abs(delta), 2)
  const profitable = total > 0

  if (profitable && delta >= 0) {
    return { tone: 'positive', text: `Beat buy & hold by ${points}`, delta }
  }
  if (profitable && delta < 0) {
    return { tone: 'caution', text: `Lagged buy & hold by ${points}`, delta }
  }
  if (delta >= 0) {
    return { tone: 'neutral', text: `Lost less than buy & hold by ${points}`, delta }
  }
  return { tone: 'negative', text: `Lost more than buy & hold by ${points}`, delta }
}

/**
 * The approval gate counts CLOSED trades only. A non-zero return with zero
 * trades means an open position at the end of the data, so the UI says so
 * rather than quietly showing a flat "0 trades".
 */
export function hasUnclosedPosition(result) {
  const total = result?.total_return_pct
  const trades = result?.num_trades
  return trades === 0 && isNum(total) && Math.abs(total) > 0.0001
}

const WARNING_TEXT = {
  no_trades:
    'No closed trades were recorded. A position that was still open when the data ended does not count as a trade.',
  trades_truncated:
    'Only the first 500 closed trades are returned to the browser; the aggregate metrics cover every trade.',
  data_stale:
    'Market data could not be refreshed, so a cached CSV was reused. Check the reported period before drawing conclusions.',
}

export function humanizeWarning(warning) {
  if (typeof warning !== 'string' || !warning.trim()) return null
  const token = warning.trim()
  return WARNING_TEXT[token] ?? token
}

/** Gate thresholds mirror backend/.env defaults; used only for UI hints. */
export const GATE_LIMITS = {
  minTrades: 1,
  maxDrawdownPct: 50,
}