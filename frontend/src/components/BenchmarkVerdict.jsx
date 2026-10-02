import { formatPercent } from '../lib/format.js'

/**
 * Verdict against buy & hold.
 *
 * Green is only ever shown when the strategy also made money — the backend
 * happily reports "beat the benchmark" for a losing strategy, and colouring
 * that green would be misleading.
 */
export default function BenchmarkVerdict({ result }) {
  const total = result?.total_return_pct
  const bench = result?.benchmark_return_pct
  if (typeof total !== 'number' || typeof bench !== 'number') return null

  const delta = total - bench
  const points = formatPercent(Math.abs(delta), 2)
  const profitable = total > 0

  let tone = 'none'
  let text = `Buy & hold returned ${formatPercent(bench, 2)} over the same period.`

  if (profitable && delta >= 0) {
    tone = 'positive'
    text = `Beat buy & hold by ${points}`
  } else if (profitable && delta < 0) {
    tone = 'caution'
    text = `Lagged buy & hold by ${points}`
  } else if (delta >= 0) {
    tone = 'neutral'
    text = `Lost less than buy & hold by ${points}`
  } else {
    tone = 'negative'
    text = `Lost more than buy & hold by ${points}`
  }

  return (
    <span className={`verdict verdict--${tone}`}>
      <span aria-hidden="true">
        {tone === 'positive' ? '▲' : tone === 'negative' ? '▼' : tone === 'caution' ? '△' : '■'}
      </span>
      {text}
    </span>
  )
}