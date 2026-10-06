import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchStrategy } from '../lib/api.js'
import { getCachedBacktest, readStrategies } from '../lib/storage.js'
import { formatDateTime } from '../lib/format.js'
import StatusBadge from '../components/StatusBadge.jsx'
import Note from '../components/Note.jsx'

/**
 * Backtesting hub — page 4 of the 7-page split.
 *
 * UI ORGANIZATION ONLY. This page runs no backtest itself and recalculates
 * nothing. It lists existing strategies with their cached-result state and
 * links into the unchanged per-strategy BacktestPage
 * (/strategies/:id/backtest), which keeps all existing run/parameter logic.
 */
export default function BacktestsHubPage() {
  const [entries, setEntries] = useState(() => readStrategies())
  const [statusById, setStatusById] = useState({})

  useEffect(() => {
    let cancelled = false
    const known = readStrategies()
    setEntries(known)
    Promise.all(
      known.map(async (entry) => {
        try {
          const data = await fetchStrategy(entry.id)
          return [entry.id, data?.status ?? null]
        } catch {
          return [entry.id, null]
        }
      }),
    ).then((pairs) => {
      if (cancelled) return
      const map = {}
      for (const [id, status] of pairs) map[id] = status
      setStatusById(map)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">Backtesting</h1>
          <p className="page-lede">
            Run a strategy and see the result. Pick a strategy below to open its backtest workspace —
            parameters, NIFTY 50 run, equity curve, metrics, trade table and approval gate link all
            live there, unchanged.
          </p>
        </div>
        <Link className="btn" to="/analytics">
          Analyze results
        </Link>
      </div>

      {entries.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">
            ▷
          </span>
          <span className="empty-state__title">No strategies to backtest</span>
          <p className="empty-state__text">
            Strategies are created by talking to the assistant. Once finalized, they appear here for
            backtesting.
          </p>
          <div className="empty-state__actions">
            <Link className="btn btn--primary" to="/studio">
              Open Strategy Studio
            </Link>
          </div>
        </div>
      ) : (
        <section className="panel" aria-labelledby="backtests-list">
          <div className="panel__head">
            <h2 className="section-title" id="backtests-list">
              Strategies ready for backtesting
            </h2>
            <span className="disclaimer-text">{entries.length} registered</span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">Strategies and their backtest state</caption>
              <thead>
                <tr>
                  <th scope="col">Strategy</th>
                  <th scope="col">Status</th>
                  <th scope="col">Cached result</th>
                  <th scope="col">Created</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const cached = getCachedBacktest(entry.id)
                  return (
                    <tr key={entry.id}>
                      <td>
                        <Link to={`/strategies/${entry.id}`}>{entry.name}</Link>
                      </td>
                      <td>
                        {statusById[entry.id] ? (
                          <StatusBadge status={statusById[entry.id]} />
                        ) : (
                          <StatusBadge label="status unavailable" />
                        )}
                      </td>
                      <td>{cached ? `Saved · ${formatDateTime(cached.ranAt)}` : '—'}</td>
                      <td className="tabular">{formatDateTime(entry.createdAt)}</td>
                      <td>
                        <Link className="btn btn--sm btn--primary" to={`/strategies/${entry.id}/backtest`}>
                          {cached ? 'Re-run backtest' : 'Run backtest'}
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Note tone="info" title="Where results live">
        <span>
          Backtest results are kept in this browser only — the backend exposes no endpoint to read a
          stored run back. The per-strategy backtest page explains this and keeps the same Run,
          Cancel and Discard controls as before.
        </span>
      </Note>

      <p className="disclaimer-text">
        Past performance does not guarantee future results. Educational prototype — paper trading
        only.
      </p>
    </div>
  )
}
