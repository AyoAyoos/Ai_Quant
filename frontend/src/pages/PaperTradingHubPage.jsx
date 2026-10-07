import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAllPaperDeployments, stopDeployment } from '../lib/api.js'
import { formatDateTime, formatMoney, formatPercent, formatSignedMoney } from '../lib/format.js'
import StatusBadge from '../components/StatusBadge.jsx'
import Note from '../components/Note.jsx'
import PaperDeploymentDetails from '../components/PaperDeploymentDetails.jsx'

/**
 * Paper Trading hub — simulated/paper deployment only. Aggregates the
 * backend's GET /paper/deployments (deployment records plus live snapshot
 * numbers), links into the unchanged per-strategy deployment pages for
 * deploy/stop actions, and expands each row into its virtual account,
 * positions, orders, trades, paper-tick control and NIFTY chart.
 * No live trading, no broker integration — the educational disclaimer stays.
 */
export default function PaperTradingHubPage() {
  const [deployments, setDeployments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState({})
  const [stopTarget, setStopTarget] = useState(null)
  const [stopReason, setStopReason] = useState('')
  const [stopBusy, setStopBusy] = useState(false)
  const [stopError, setStopError] = useState(null)

  const load = useCallback(async (signal) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchAllPaperDeployments({ signal })
      if (signal?.aborted) return
      setDeployments(Array.isArray(data) ? data : [])
    } catch (err) {
      if (err?.name === 'AbortError' || signal?.aborted) return
      setDeployments([])
      setError(err)
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  function toggle(deploymentId) {
    setExpanded((current) => ({ ...current, [deploymentId]: !current[deploymentId] }))
  }

  const active = deployments.filter((d) => d.status === 'active')
  const history = deployments.filter((d) => d.status !== 'active')

  const refreshSummaries = useCallback(async () => {
    try {
      const data = await fetchAllPaperDeployments()
      setDeployments(Array.isArray(data) ? data : [])
    } catch {
      // Best-effort top-summary refresh; per-section errors stay local.
    }
  }, [])

  function askStop(deployment) {
    setStopTarget(deployment)
    setStopReason('')
    setStopError(null)
  }

  function cancelStop() {
    if (stopBusy) return
    setStopTarget(null)
    setStopReason('')
    setStopError(null)
  }

  async function confirmStop() {
    if (!stopTarget || stopBusy) return
    setStopBusy(true)
    setStopError(null)
    try {
      await stopDeployment(stopTarget.strategy_id, stopReason.trim() || null)
      const stoppedId = stopTarget.id
      setStopTarget(null)
      setStopReason('')
      setExpanded((current) => {
        if (!current[stoppedId]) return current
        const next = { ...current }
        delete next[stoppedId]
        return next
      })
      await refreshSummaries()
    } catch (err) {
      setStopError(err)
    } finally {
      setStopBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head__text">
          <p className="page-lede">
            
          </p>
        </div>
        <Link className="btn" to="/strategies">
          View approved strategies
        </Link>
      </div>

      

      {error && (
        <Note tone="danger" title="Paper deployments failed to load">
          <span>
            {error.message || 'Request failed.'}{' '}
            <button type="button" className="btn btn--sm" onClick={() => load()}>
              Retry
            </button>
          </span>
        </Note>
      )}

      <section className="panel panel--accent" aria-labelledby="paper-active">
        <div className="panel__head">
          <h2 className="section-title" id="paper-active">
            Active paper deployments
          </h2>
          <span className="disclaimer-text">
            {loading ? 'Loading…' : `${active.length} active`}
          </span>
        </div>
        {loading ? (
          <p className="disclaimer-text">Loading deployment histories…</p>
        ) : active.length === 0 ? (
          <p className="disclaimer-text">
            No active paper deployment. Approve a backtested strategy, then deploy it in paper mode
            from its deployment page.
          </p>
        ) : (
          <>
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">Active paper deployments</caption>
              <thead>
                <tr>
                  <th scope="col">Strategy</th>
                  <th scope="col">Market</th>
                  <th scope="col">Equity (virtual)</th>
                  <th scope="col">P&amp;L (virtual)</th>
                  <th scope="col">Return</th>
                  <th scope="col">Deployed</th>
                  <th scope="col">Details</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {active.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/strategies/${d.strategy_id}`}>
                        {d.strategy_name ?? d.strategy_id}
                      </Link>
                    </td>
                    <td>{d.market ?? '—'}</td>
                    <td className="tabular">
                      {d.equity == null ? '—' : `₹${formatMoney(d.equity)}`}
                    </td>
                    <td className="tabular">
                      {d.total_pnl == null ? '—' : formatSignedMoney(d.total_pnl)}
                    </td>
                    <td className="tabular">{formatPercent(d.return_pct)}</td>
                    <td className="tabular">{formatDateTime(d.deployed_at)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--sm"
                        aria-expanded={Boolean(expanded[d.id])}
                        onClick={() => toggle(d.id)}
                      >
                        {expanded[d.id] ? 'Hide' : 'Show'}
                      </button>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--sm btn--danger"
                        onClick={() => askStop(d)}
                        disabled={stopBusy && stopTarget?.id === d.id}
                      >
                        Stop
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {stopTarget && (
            <div className="paper-expanded" aria-live="polite">
              <div className="paper-details">
                <h4 className="paper-details__heading">Stop paper trading</h4>
                <p className="disclaimer-text">
                  Paper Trading will stop for{' '}
                  <strong>{stopTarget.strategy_name ?? stopTarget.strategy_id}</strong>.
                  Existing simulated results are preserved and further Paper Ticks are
                  disabled. This does NOT delete the deployment or its history.
                </p>
                <label className="field" htmlFor="hub-stop-reason">
                  <span className="field__label">Reason (optional)</span>
                  <input
                    id="hub-stop-reason"
                    className="field__input"
                    type="text"
                    maxLength={500}
                    placeholder="e.g. Ending this simulation run"
                    value={stopReason}
                    disabled={stopBusy}
                    onChange={(event) => setStopReason(event.target.value)}
                  />
                </label>
                {stopError && (
                  <Note tone="danger" title="Stop failed" reasons={stopError.reasons}>
                    <span>
                      {stopError.message || 'Request failed.'}{' '}
                      <button type="button" className="btn btn--sm" onClick={confirmStop} disabled={stopBusy}>
                        Retry
                      </button>
                    </span>
                  </Note>
                )}
                <div className="row">
                  <button
                    type="button"
                    className="btn btn--sm btn--danger"
                    onClick={confirmStop}
                    disabled={stopBusy}
                  >
                    {stopBusy && <span className="btn__spinner" aria-hidden="true" />}
                    {stopBusy ? 'Stopping…' : 'Confirm stop'}
                  </button>
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={cancelStop}
                    disabled={stopBusy}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
          {active
            .filter((d) => expanded[d.id])
            .map((d) => (
              <div key={d.id} className="paper-expanded">
                <PaperDeploymentDetails deployment={d} onChanged={refreshSummaries} />
              </div>
            ))}
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="paper-history">
        <div className="panel__head">
          <h2 className="section-title" id="paper-history">
            Deployment history
          </h2>
          <span className="disclaimer-text">
            {loading ? '' : `${history.length} record${history.length === 1 ? '' : 's'} (stopped only)`}
          </span>
        </div>
        {loading ? (
          <p className="disclaimer-text">Loading…</p>
        ) : history.length === 0 ? (
          <p className="disclaimer-text">
            No stopped deployments yet. Active deployments appear above; this history
            lists only stopped records.
          </p>
        ) : (
          <>
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">Stopped paper deployments</caption>
              <thead>
                <tr>
                  <th scope="col">Strategy</th>
                  <th scope="col">Status</th>
                  <th scope="col">Starting cash</th>
                  <th scope="col">Equity (virtual)</th>
                  <th scope="col">Trades</th>
                  <th scope="col">Deployed</th>
                  <th scope="col">Stopped</th>
                  <th scope="col">Details</th>
                </tr>
              </thead>
              <tbody>
                {history.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/strategies/${d.strategy_id}`}>
                        {d.strategy_name ?? d.strategy_id}
                      </Link>
                    </td>
                    <td>
                      <StatusBadge status={d.status} />
                    </td>
                    <td className="tabular">
                      {d.starting_cash == null ? '—' : `₹${formatMoney(d.starting_cash)}`}
                    </td>
                    <td className="tabular">
                      {d.equity == null ? '—' : `₹${formatMoney(d.equity)}`}
                    </td>
                    <td className="tabular">{d.completed_trades ?? '—'}</td>
                    <td className="tabular">{formatDateTime(d.deployed_at)}</td>
                    <td className="tabular">
                      {d.status === 'active' ? '—' : formatDateTime(d.stopped_at)}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--sm"
                        aria-expanded={Boolean(expanded[d.id])}
                        onClick={() => toggle(d.id)}
                      >
                        {expanded[d.id] ? 'Hide' : 'Show'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {history
            .filter((d) => expanded[d.id])
            .map((d) => (
              <div key={d.id} className="paper-expanded">
                <PaperDeploymentDetails deployment={d} onChanged={refreshSummaries} />
              </div>
            ))}
          </>
        )}
      </section>
    </div>
  )
}
