import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAllPaperDeployments, fetchBacktestResults, fetchStrategies } from '../lib/api.js'
import { formatMoney, formatPercent } from '../lib/format.js'
import BenchmarkVerdict from '../components/BenchmarkVerdict.jsx'
import Disclosure from '../components/Disclosure.jsx'
import DrawdownChart from '../components/DrawdownChart.jsx'
import EquityChart from '../components/EquityChart.jsx'
import MetricGrid from '../components/MetricGrid.jsx'
import Note from '../components/Note.jsx'
import TradeTable from '../components/TradeTable.jsx'

/**
 * Analytics — page 5 of the 7-page split.
 *
 * UI ORGANIZATION ONLY. "Understand and analyze the result" for an already-run
 * backtest. No calculation here: every number and chart below renders the
 * existing cached backtest payload with the existing MetricGrid, EquityChart,
 * BenchmarkVerdict and TradeTable components.
 */

function PaperAnalytics() {
  const [deployments, setDeployments] = useState([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    fetchAllPaperDeployments().then(ds => { if (!cancelled) { setDeployments(ds); setLoading(false) } }).catch(()=>{ if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])
  if (loading) return <p className="disclaimer-text">Loading deployments…</p>
  return (
    <section className="stack">
      <h2 className="section-title">Paper Trading Analytics</h2>
      <div className="panel">
        <p className="disclaimer-text">Summary from PaperDeployment, PaperPosition, PaperOrder and PaperTrade records.</p>
        {deployments.length === 0 ? (
          <p className="disclaimer-text">No paper deployments yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Strategy</th><th>Status</th><th>Equity</th><th>P&L</th><th>Return</th><th>Deployed</th></tr></thead>
              <tbody>
                {deployments.map(d=>(
                  <tr key={d.id}>
                    <td>{d.strategy_name ?? d.strategy_id}</td>
                    <td>{d.status}</td>
                    <td className="tabular">{d.equity != null ? `₹${formatMoney(d.equity)}` : '—'}</td>
                    <td className="tabular">{d.total_pnl ?? '—'}</td>
                    <td className="tabular">{d.return_pct != null ? formatPercent(d.return_pct) : '—'}</td>
                    <td>{d.deployed_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Link className="btn" to="/paper-trading">Go to Paper Trading</Link>
      </div>
    </section>
  )
}

export default function AnalyticsPage() {
  const [strategies, setStrategies] = useState([])
  const [strategiesLoading, setStrategiesLoading] = useState(true)
  const [strategiesError, setStrategiesError] = useState(null)
  const [mode, setMode] = useState('backtest')
  const availableStrategies = useMemo(() => strategies, [strategies])
  const [selectedId, setSelectedId] = useState(null)

  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    let cancelled = false
    setStrategiesLoading(true)
    setStrategiesError(null)
    fetchStrategies().then(list => {
      if (!cancelled) {
        setStrategies(Array.isArray(list) ? list : [])
        if (Array.isArray(list) && list.length > 0 && !selectedId) {
          setSelectedId(list[0].strategy_id)
        }
        setStrategiesLoading(false)
      }
    }).catch(err => {
      if (!cancelled) {
        setStrategiesError(err)
        setStrategiesLoading(false)
      }
    })
    return () => { cancelled = true }
  }, [])
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!selectedId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchBacktestResults(selectedId).then(data => {
      if (!cancelled) {
        setResults(Array.isArray(data) ? data : [])
        setLoading(false)
      }
    }).catch(err => {
      if (!cancelled) {
        setError(err)
        setResults([])
        setLoading(false)
      }
    })
    return () => { cancelled = true }
  }, [selectedId])

  const selectedStrategy = availableStrategies.find(s => s.strategy_id === selectedId) ?? null
  const result = results[0]?.raw_metrics ? {
    ...results[0],
    ...results[0].raw_metrics
  } : null

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head__text">
          <p className="page-lede">
            
          </p>
        </div>
        <div className="row">
          <div className="segmented" role="tablist" aria-label="Analytics mode">
            <button role="tab" aria-selected={mode==='backtest'} onClick={()=>setMode('backtest')} className={`segmented__item${mode==='backtest'?' segmented__item--active':''}`}>Backtest Analytics</button>
            <button role="tab" aria-selected={mode==='paper'} onClick={()=>setMode('paper')} className={`segmented__item${mode==='paper'?' segmented__item--active':''}`}>Paper Trading Analytics</button>
          </div>
          <Link className="btn" to="/backtests">
            Run a backtest
          </Link>
        </div>
      </div>

      {mode==='backtest' ? (
        strategiesLoading ? (
          <p className="disclaimer-text">Loading strategies…</p>
        ) : strategiesError ? (
          <div className="empty-state">
            <span className="empty-state__icon" aria-hidden="true">⚠</span>
            <span className="empty-state__title">Failed to load strategies</span>
            <p className="empty-state__text">{strategiesError.message}</p>
          </div>
        ) : availableStrategies.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon" aria-hidden="true">
              ◇
            </span>
            <span className="empty-state__title">No strategies yet</span>
            <p className="empty-state__text">
              Create a strategy first. Backtest results from the database will appear here.
            </p>
            <div className="empty-state__actions">
              <Link className="btn btn--primary" to="/strategies">
                Go to strategies
              </Link>
            </div>
          </div>
        ) : (
          <>
            <div className="filter-bar" role="group" aria-label="Select a strategy to analyze">
              {availableStrategies.map((s) => (
                <button
                  key={s.strategy_id}
                  type="button"
                  className={`filter-chip${s.strategy_id === selectedId ? ' filter-chip--active' : ''}`}
                  aria-pressed={s.strategy_id === selectedId}
                  onClick={() => setSelectedId(s.strategy_id)}
                >
                  {s.name}
                </button>
              ))}
            </div>

            {loading && <p className="disclaimer-text">Loading backtest results…</p>}
            {error && <p className="disclaimer-text">Failed to load results: {error.message}</p>}

             {selectedStrategy && result && (
              <section className="stack" aria-label={`Analysis of ${selectedStrategy.name}`}>
                <div className="panel__head">
                  <h2 className="section-title">
                    <Link to={`/strategies/${selectedStrategy.strategy_id}`}>{selectedStrategy.name}</Link>
                  </h2>
                  <Link className="btn btn--sm" to={`/strategies/${selectedStrategy.strategy_id}/backtest`}>
                    Open backtest
                  </Link>
                </div>

                <MetricGrid result={result} />
                <BenchmarkVerdict result={result} />
                <EquityChart curve={result.equity_curve} />
                <DrawdownChart curve={result.drawdown_curve} />

                <p className="disclaimer-text">
                  Past performance does not guarantee future results. Educational prototype — paper
                  trading only.
                </p>

                <Disclosure
                  title="Trade analysis"
                  meta={result.num_trades === 0 ? 'none recorded' : `${result.num_trades ?? 0} closed`}
                  defaultOpen
                >
                  <TradeTable trades={result.trades} truncated={result.trades_truncated} />
                </Disclosure>
              </section>
            )}
            {selectedStrategy && !loading && results.length === 0 && (
              <div className="panel">
                <p className="disclaimer-text">No backtest results found for this strategy. Run a backtest first.</p>
                <Link className="btn" to={`/strategies/${selectedStrategy.strategy_id}/backtest`}>Run backtest</Link>
              </div>
            )}
          </>
        )
      ) : (
        <PaperAnalytics />
      )}

      <Note tone="info" title="Backtesting vs analytics">
        <span>
          Backtesting answers “run this strategy and see the result”; analytics answers “understand
          and analyze the result”. Both read the same stored run — nothing is recalculated here.
        </span>
      </Note>
    </div>
  )
}
