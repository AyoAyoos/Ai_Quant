import { useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BACKTEST_TIMEOUT_MS, runBacktest } from '../lib/api.js'
import { canPerform, explainUnavailable } from '../lib/actions.js'
import { humanizeWarning } from '../lib/format.js'
import { removeCachedBacktest, setCachedBacktest } from '../lib/storage.js'
import { useCachedBacktest, useStrategyDetail } from '../lib/useStrategy.js'
import { useElapsedTimer } from '../lib/useElapsedTimer.js'
import BenchmarkVerdict from '../components/BenchmarkVerdict.jsx'
import Disclosure from '../components/Disclosure.jsx'
import DrawdownChart from '../components/DrawdownChart.jsx'
import EquityChart from '../components/EquityChart.jsx'
import MetricGrid from '../components/MetricGrid.jsx'
import Note from '../components/Note.jsx'
import StrategyTabs from '../components/StrategyTabs.jsx'
import TradeTable from '../components/TradeTable.jsx'
import ElapsedTimer from '../components/ElapsedTimer.jsx'
import LoadingBlock, { SkeletonBlock, SkeletonMetrics, SkeletonTitle } from '../components/Skeletons.jsx'

const DEFAULTS = { cash: 100000, commissionPct: 0.1, sizerPercent: 95, slippagePct: 0 }

/**
 * Validates against the backend's Field constraints before spending a call.
 * commission/sizer are percentages in the open range (0, 100) — the same
 * units the backend's `Field(gt=0, lt=100)` expects — so 0.2 is 0.2% and 20
 * is 20%. Rejecting `''` here (Number.isFinite('') is false) also keeps an
 * emptied input from reaching the API as a string and 422-ing there.
 */
function validate(values) {
  const errors = {}
  if (!Number.isFinite(values.cash) || values.cash <= 0) errors.cash = 'Cash must be greater than 0.'
  if (!Number.isFinite(values.commissionPct) || values.commissionPct <= 0 || values.commissionPct >= 100) {
    errors.commissionPct = 'Commission must be a percentage greater than 0 and less than 100.'
  }
  if (!Number.isFinite(values.sizerPercent) || values.sizerPercent <= 0 || values.sizerPercent >= 100) {
    errors.sizerPercent = 'Position size must be a percentage greater than 0 and less than 100.'
  }
  if (!Number.isFinite(values.slippagePct) || values.slippagePct < 0 || values.slippagePct >= 100) {
    errors.slippagePct = 'Slippage must be a percentage between 0 and 100.'
  }
  return errors
}

function NumberField({ id, label, hint, suffix, value, error, onChange }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div className={`field__control${error ? ' field__control--error' : ''}`}>
        <input
          id={id}
          className="field__input"
          type="number"
          inputMode="decimal"
          step="any"
          min="0"
          value={value}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={error ? `${id}-error` : `${id}-hint`}
          onChange={(event) => onChange(event.target.value)}
        />
        {suffix && <span className="field__suffix">{suffix}</span>}
      </div>
      {error ? (
        <span className="field__error" id={`${id}-error`}>
          {error}
        </span>
      ) : (
        <span className="field__hint" id={`${id}-hint`}>
          {hint}
        </span>
      )}
    </div>
  )
}

export default function BacktestPage() {
  const { id } = useParams()
  const { detail, status, loading, notFound } = useStrategyDetail(id)
  const cached = useCachedBacktest(id)

  const [values, setValues] = useState(DEFAULTS)
  const [touched, setTouched] = useState({})
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [ranAt, setRanAt] = useState(cached?.ranAt ?? null)
  const [showRaw, setShowRaw] = useState(false)

  const abortRef = useRef(null)
  const elapsed = useElapsedTimer(running)

  const errors = useMemo(() => validate(values), [values])
  const invalid = Object.keys(errors).length > 0

  function setField(key, raw) {
    setTouched((current) => ({ ...current, [key]: true }))
    setValues((current) => ({ ...current, [key]: raw === '' ? '' : Number(raw) }))
  }

  function handleExport() {
    const data = shown
    if (!data) return
    const metrics = [
      ['Metric','Value'],
      ['Total Return %', data.total_return_pct],
      ['Benchmark Return %', data.benchmark_return_pct],
      ['CAGR %', data.cagr_pct],
      ['Max Drawdown %', data.max_drawdown_pct],
      ['Sharpe', data.sharpe],
      ['Sortino', data.sortino],
      ['Win Rate %', data.win_rate_pct],
      ['Num Trades', data.num_trades],
      ['Profit Factor', data.profit_factor],
      ['Avg Win', data.avg_win],
      ['Avg Loss', data.avg_loss],
      ['Avg Trade PnL', data.avg_trade_pnl],
      ['Expectancy', data.expectancy],
    ]
    const trades = data.trades || []
    const tradeHeader = ['Entry Date','Exit Date','Direction','Size','Entry Price','Exit Price','Bars Held','PnL Net','Won']
    const tradeRows = trades.map(t => [
      t.entry_date, t.exit_date, t.direction, t.size, t.entry_price, t.exit_price, t.bars_held, t.pnl_net, t.won
    ])
    const csv = [metrics.map(r=>r.join(',')).join('\n'), '\n\nTrades\n'+[tradeHeader.join(',')].concat(tradeRows.map(r=>r.join(','))).join('\n')].join('\n')
    const blob = new Blob([csv], {type: 'text/csv'})
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `backtest-${id}-${new Date().toISOString().slice(0,10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleRun() {
    if (running || invalid) return
    setRunning(true)
    setError(null)
    setShowRaw(false)

    const controller = new AbortController()
    abortRef.current = controller
    const timer = setTimeout(() => controller.abort(), BACKTEST_TIMEOUT_MS)

    try {
      const data = await runBacktest(id, values, { signal: controller.signal })
      setResult(data)
      setRanAt(new Date().toISOString())
      setCachedBacktest(id, data)
    } catch (err) {
      if (err?.name === 'AbortError') {
        setError(
          'The backtest exceeded the backend 120-second limit and was cancelled. The strategy may be doing too much work per bar — simplify the generated code and try again.',
        )
      } else {
        setError({ message: err?.message ?? 'Request failed.', reasons: err?.reasons ?? [] })
      }
    } finally {
      clearTimeout(timer)
      abortRef.current = null
      setRunning(false)
    }
  }

  function handleCancel() {
    abortRef.current?.abort()
  }

  function handleDiscard() {
    removeCachedBacktest(id)
    setResult(null)
    setRanAt(null)
    setError(null)
  }

  if (loading) {
    return (
      <div className="page">
        <LoadingBlock label="Loading strategy">
          <div className="stack">
            <SkeletonTitle />
            <SkeletonBlock height={90} />
          </div>
        </LoadingBlock>
      </div>
    )
  }

  if (notFound || !detail) {
    return (
      <div className="page">
        <Note tone="danger" title="Strategy not found">
          <span>The backend has no strategy with id {id}.</span>
        </Note>
        <div>
          <Link className="btn" to="/strategies">
            Back to library
          </Link>
        </div>
      </div>
    )
  }

  const allowed = canPerform(status, 'backtest')
  const shown = result ?? cached?.result ?? null
  const shownAt = ranAt ?? cached?.ranAt ?? null
  const isCached = !result && Boolean(cached?.result)
  const warnings = shown?.warnings ?? []
  const noTradesWarning = warnings.some((w) => w === 'no_trades')

  const monthlyReturns = (() => {
    const curve = shown?.equity_curve
    if (!Array.isArray(curve) || curve.length < 2) return []
    const byMonth = new Map()
    curve.forEach(([date, value]) => {
      if (!date || typeof value !== 'number') return
      const d = new Date(date)
      if (isNaN(d)) return
      const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
      if (!byMonth.has(key)) byMonth.set(key, { start: value, end: value })
      const cur = byMonth.get(key)
      cur.end = value
    })
    return Array.from(byMonth.entries()).map(([month, v]) => {
      const ret = v.start ? ((v.end / v.start) - 1) * 100 : 0
      return { month, ret }
    })
  })()

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/strategies">Strategies</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/strategies/${id}`}>{detail.name}</Link>
        <span aria-hidden="true">/</span>
        <span>Backtest</span>
      </nav>

      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">Backtest</h1>
          <p className="page-lede">
            Run the generated Backtrader code against NIFTY 50 daily history the backend fetches and
            caches. Results are kept in this browser only — the backend exposes no endpoint to read a
            stored run back.
          </p>
        </div>
        <StrategyTabs strategyId={id} />
      </div>

      {!allowed && <Note tone="warning" title={`Not available at status "${status}"`}>{explainUnavailable(status, 'backtest')}</Note>}

      <section className="panel" aria-labelledby="params-heading">
        <div className="panel__head">
          <h2 className="section-title" id="params-heading">
            Parameters
          </h2>
          {running && <ElapsedTimer seconds={elapsed} />}
        </div>

        <form className="form-grid" onSubmit={(event) => event.preventDefault()}>
          <NumberField
            id="cash"
            label="Starting cash"
            hint="Simulated portfolio capital in rupees."
            suffix="₹"
            value={values.cash}
            error={touched.cash ? errors.cash : undefined}
            onChange={(raw) => setField('cash', raw)}
          />
          <NumberField
            id="commission"
            label="Commission"
            hint="Percent charged on every order: 0.2 means 0.2%, 20 means 20%. Must stay under 100."
            suffix="%"
            value={values.commissionPct}
            error={touched.commissionPct ? errors.commissionPct : undefined}
            onChange={(raw) => setField('commissionPct', raw)}
          />
          <NumberField
            id="sizer"
            label="Position size"
            hint="Percent of available cash committed per entry (1–99)."
            suffix="%"
            value={values.sizerPercent}
            error={touched.sizerPercent ? errors.sizerPercent : undefined}
            onChange={(raw) => setField('sizerPercent', raw)}
          />
          <NumberField
            id="slippage"
            label="Slippage"
            hint="Simulated execution slippage per order. 0 for none."
            suffix="%"
            value={values.slippagePct}
            error={touched.slippagePct ? errors.slippagePct : undefined}
            onChange={(raw) => setField('slippagePct', raw)}
          />
        </form>

        <div className="page-actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleRun}
            disabled={running || invalid || !allowed}
          >
            {running && <span className="btn__spinner" aria-hidden="true" />}
            {running ? 'Running…' : shown ? 'Re-run backtest' : 'Run backtest'}
          </button>
          {running && (
            <button type="button" className="btn" onClick={handleCancel}>
              Cancel
            </button>
          )}
          {isCached && !running && (
            <button type="button" className="btn btn--ghost" onClick={handleDiscard}>
              Discard saved result
            </button>
          )}
        </div>

        <p className="disclaimer-text">
          The worker is capped at 120 seconds. If it overruns, the backend returns a gateway timeout and this
          request is cancelled rather than left running.
        </p>
      </section>

      {error && (
        <Note tone="danger" title="Backtest failed" reasons={error.reasons}>
          <span>{error.message}</span>
        </Note>
      )}

      {running && !shown && (
        <LoadingBlock label="Running backtest">
          <div className="panel">
            <div className="running-state" role="status" aria-live="polite">
              <span className="spinner-inline" aria-hidden="true" />
              <span>
                Simulating trades on NIFTY 50 daily data. This usually takes 10–40 seconds.
              </span>
              <ElapsedTimer seconds={elapsed} />
            </div>
            <SkeletonMetrics />
            <SkeletonBlock height={180} />
          </div>
        </LoadingBlock>
      )}

      {!running && shown && (
        <section className="stack" aria-labelledby="results-heading">
          <div className="panel__head">
            <h2 className="section-title" id="results-heading">
              Results
            </h2>
            <span className="disclaimer-text">
              {isCached ? 'Saved in this browser' : 'Fresh run'} ·{' '}
              {shownAt ? new Date(shownAt).toLocaleString() : 'unknown time'}
            </span>
          </div>

          {isCached && (
            <Note tone="info" title="Showing a saved result">
              These numbers come from this browser&apos;s cache of your last run, not from a live call — the
              backend has no endpoint that returns a stored backtest. Re-run to refresh them.
            </Note>
          )}

          <MetricGrid result={shown} />

          {noTradesWarning && (shown?.total_return_pct ?? 0) !== 0 && (
            <Note tone="warning" title="Zero trades, non-zero return">
              The strategy placed no trades yet still reports a {shown.total_return_pct.toFixed(2)}% return.
              That is a position still open at the end of the window, not a realised profit. Treat this
              result as untested.
            </Note>
          )}

          {warnings.length > 0 && (
            <Note tone="warning" title={`${warnings.length} warning${warnings.length === 1 ? '' : 's'} from the run`}>
              <ul>
                {warnings.map((warning, index) => (
                  <li key={index}>{humanizeWarning(warning)}</li>
                ))}
              </ul>
            </Note>
          )}

          <BenchmarkVerdict result={shown} />

          <EquityChart points={shown.equity_curve} startDate={shown.start_date} endDate={shown.end_date} />

          <div className="panel" style={{ marginTop: 'var(--sp-4)' }}>
            <h3 className="section-title" style={{ marginBottom: 'var(--sp-2)' }}>Drawdown</h3>
            <DrawdownChart curve={shown?.drawdown_curve} />
            <p className="disclaimer-text" style={{ marginTop: 'var(--sp-2)' }}>
              Maximum drawdown: {shown?.max_drawdown_pct ? `${shown.max_drawdown_pct.toFixed(2)}%` : 'N/A'}.
            </p>
          </div>

          {monthlyReturns.length > 0 && (
            <div className="panel" style={{ marginTop: 'var(--sp-4)' }}>
              <h3 className="section-title" style={{ marginBottom: 'var(--sp-2)' }}>Monthly Returns</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>Month</th><th className="num">Return %</th></tr></thead>
                  <tbody>
                    {monthlyReturns.map(m => (
                      <tr key={m.month}>
                        <td>{m.month}</td>
                        <td className="num">{m.ret.toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <p className="disclaimer-text">
            Past performance does not guarantee future results. Educational prototype — paper trading only.
          </p>

          <Disclosure
            title="Trades"
            meta={shown.num_trades === 0 ? 'none recorded' : `${shown.num_trades ?? 0} closed`}
            defaultOpen
          >
            <TradeTable trades={shown.trades} truncated={shown.trades_truncated} />
          </Disclosure>

          {shown.raw_metrics && (
            <div>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setShowRaw((v) => !v)}>
                {showRaw ? 'Hide' : 'Show'} raw metrics JSON
              </button>
              {showRaw && (
                <pre className="code-viewer__pre raw-metrics" style={{ marginTop: 'var(--sp-3)' }}>
                  <code>{JSON.stringify(shown.raw_metrics, null, 2)}</code>
                </pre>
              )}
            </div>
          )}

          <div style={{ marginTop: 'var(--sp-3)' }}>
            <button type="button" className="btn btn--ghost" onClick={handleExport}>Export CSV</button>
          </div>

          <div className="page-actions">
            {status === 'backtested' ? (
              <Link className="btn btn--positive" to={`/strategies/${id}/approval`}>
                Continue to approval
              </Link>
            ) : (
              <Link className="btn btn--primary" to={`/strategies/${id}/approval`}>
                Review approval gate
              </Link>
            )}
            <Link className="btn btn--ghost" to={`/strategies/${id}`}>
              Back to overview
            </Link>
          </div>
        </section>
      )}

      {!running && !shown && allowed && (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">
            ▷
          </span>
          <span className="empty-state__title">No backtest run in this browser</span>
          <p className="empty-state__text">
            Set the parameters and run the backtest. The strategy becomes &quot;backtested&quot; when it
            finishes, which unlocks the approval gate.
          </p>
        </div>
      )}
    </div>
  )
}