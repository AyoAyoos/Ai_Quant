import {
  benchmarkVerdict,
  formatInt,
  formatPercent,
  formatRatio,
  metricTone,
} from '../lib/format.js'
import BenchmarkVerdict from './BenchmarkVerdict.jsx'

function Metric({ label, value, tone, benchmark = false }) {
  return (
    <div className={`metric${benchmark ? ' metric--benchmark' : ''}`}>
      <span className={`metric__value metric__value--${tone}`}>{value}</span>
      <span className="metric__label">{label}</span>
    </div>
  )
}

/**
 * The eight-metric grid.
 *
 * `max_drawdown_pct` is a POSITIVE severity number from the backend, so it is
 * coloured through metricTone('drawdown', …) rather than a "< 0" test.
 */
export default function MetricGrid({ result }) {
  const verdict = benchmarkVerdict(result)

  return (
    <div className="stack stack--tight">
      <div className="metrics-grid">
        <Metric
          label="Total return"
          value={formatPercent(result?.total_return_pct, 2)}
          tone={metricTone('return', result?.total_return_pct)}
        />
        <Metric
          label="Buy & hold"
          value={formatPercent(result?.benchmark_return_pct, 2)}
          tone={metricTone('benchmark', result?.benchmark_return_pct)}
          benchmark
        />
        <Metric
          label="CAGR"
          value={formatPercent(result?.cagr_pct, 2)}
          tone={metricTone('cagr', result?.cagr_pct)}
        />
        <Metric
          label="Max drawdown"
          value={formatPercent(result?.max_drawdown_pct, 2)}
          tone={metricTone('drawdown', result?.max_drawdown_pct)}
        />
        <Metric label="Sharpe" value={formatRatio(result?.sharpe)} tone={metricTone('ratio', result?.sharpe)} />
        <Metric label="Sortino" value={formatRatio(result?.sortino)} tone={metricTone('ratio', result?.sortino)} />
        <Metric label="Win rate" value={formatPercent(result?.win_rate_pct, 1)} tone="neutral" />
        <Metric label="Trades" value={formatInt(result?.num_trades)} tone="neutral" />
      </div>

      <div className="row row--between">
        <span className="tabular" style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)' }}>
          {result?.start_date && result?.end_date
            ? `${String(result.start_date).slice(0, 10)} → ${String(result.end_date).slice(0, 10)}`
            : 'Period unavailable'}
        </span>
        <BenchmarkVerdict result={result} />
      </div>

      {verdict.tone === 'neutral' && (
        <p className="disclaimer-text" style={{ marginTop: 'calc(-1 * var(--sp-2))' }}>
          The strategy lost money while the benchmark fell further — that is a smaller loss, not a win.
        </p>
      )}
    </div>
  )
}