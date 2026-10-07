import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCachedBacktest, readStrategies } from '../lib/storage.js'
import BenchmarkVerdict from '../components/BenchmarkVerdict.jsx'
import Disclosure from '../components/Disclosure.jsx'
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
export default function AnalyticsPage() {
  const [entries] = useState(() => readStrategies())
  const available = useMemo(
    () =>
      entries
        .map((entry) => ({ entry, cached: getCachedBacktest(entry.id) }))
        .filter((row) => row.cached?.result),
    [entries],
  )
  const [selectedId, setSelectedId] = useState(() => available[0]?.entry.id ?? null)

  useEffect(() => {
    if (!selectedId && available.length > 0) setSelectedId(available[0].entry.id)
  }, [available, selectedId])

  const selected = available.find((row) => row.entry.id === selectedId) ?? null
  const result = selected?.cached?.result ?? null

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head__text">
          <p className="page-lede">
           
          </p>
        </div>
        <Link className="btn" to="/backtests">
          Run a backtest
        </Link>
      </div>

      {available.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">
            ◇
          </span>
          <span className="empty-state__title">No analyzed results yet</span>
          <p className="empty-state__text">
            Run a backtest first. Results are cached in this browser and then appear here for
            deeper analysis.
          </p>
          <div className="empty-state__actions">
            <Link className="btn btn--primary" to="/backtests">
              Go to backtesting
            </Link>
          </div>
        </div>
      ) : (
        <>
          <div className="filter-bar" role="group" aria-label="Select a backtest to analyze">
            {available.map((row) => (
              <button
                key={row.entry.id}
                type="button"
                className={`filter-chip${row.entry.id === selectedId ? ' filter-chip--active' : ''}`}
                aria-pressed={row.entry.id === selectedId}
                onClick={() => setSelectedId(row.entry.id)}
              >
                {row.entry.name}
              </button>
            ))}
          </div>

          {selected && result && (
            <section className="stack" aria-label={`Analysis of ${selected.entry.name}`}>
              <div className="panel__head">
                <h2 className="section-title">
                  <Link to={`/strategies/${selected.entry.id}`}>{selected.entry.name}</Link>
                </h2>
                <Link className="btn btn--sm" to={`/strategies/${selected.entry.id}/backtest`}>
                  Open backtest
                </Link>
              </div>

              <MetricGrid result={result} />
              <BenchmarkVerdict result={result} />
              <EquityChart curve={result.equity_curve} />

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
        </>
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
