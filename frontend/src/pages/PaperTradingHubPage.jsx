import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchDeployments, fetchStrategy } from '../lib/api.js'
import { readStrategies } from '../lib/storage.js'
import { formatDateTime } from '../lib/format.js'
import StatusBadge from '../components/StatusBadge.jsx'
import Note from '../components/Note.jsx'

/**
 * Paper Trading hub — page 6 of the 7-page split.
 *
 * UI ORGANIZATION ONLY. Simulated/paper deployment only: aggregates the
 * existing GET /strategies/{id}/deployments histories (same call the
 * per-strategy DeploymentPage makes) and links into those unchanged pages for
 * deploy/stop actions. No live trading, no broker integration, no new order
 * path — the existing educational disclaimer stays visible.
 */
export default function PaperTradingHubPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const known = readStrategies()
    if (known.length === 0) {
      setRows([])
      setLoading(false)
      return () => {
        cancelled = true
      }
    }

    Promise.all(
      known.map(async (entry) => {
        let status = null
        try {
          const detail = await fetchStrategy(entry.id)
          status = detail?.status ?? null
        } catch {
          status = null
        }
        let history = []
        try {
          const data = await fetchDeployments(entry.id)
          history = Array.isArray(data) ? data : []
        } catch {
          history = []
        }
        return { entry, status, history }
      }),
    ).then((result) => {
      if (!cancelled) {
        setRows(result)
        setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  const allDeployments = rows.flatMap((row) =>
    row.history.map((d) => ({ ...d, strategyId: row.entry.id, strategyName: row.entry.name })),
  )
  const active = allDeployments.filter((d) => d.status === 'active')

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
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">Active paper deployments</caption>
              <thead>
                <tr>
                  <th scope="col">Strategy</th>
                  <th scope="col">Deployment</th>
                  <th scope="col">Cash</th>
                  <th scope="col">Deployed</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {active.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/strategies/${d.strategyId}`}>{d.strategyName}</Link>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>{d.id}</td>
                    <td className="tabular">₹{Number(d.cash).toLocaleString('en-IN')}</td>
                    <td className="tabular">{formatDateTime(d.deployed_at)}</td>
                    <td>
                      <Link className="btn btn--sm" to={`/strategies/${d.strategyId}/deployment`}>
                        Manage
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="paper-history">
        <div className="panel__head">
          <h2 className="section-title" id="paper-history">
            Deployment history
          </h2>
          <span className="disclaimer-text">
            {loading ? '' : `${allDeployments.length} record${allDeployments.length === 1 ? '' : 's'}`}
          </span>
        </div>
        {loading ? (
          <p className="disclaimer-text">Loading…</p>
        ) : allDeployments.length === 0 ? (
          <p className="disclaimer-text">
            No deployment has ever been created. The backend returns an empty list until the first
            successful deploy.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">All paper deployments</caption>
              <thead>
                <tr>
                  <th scope="col">Strategy</th>
                  <th scope="col">Deployment</th>
                  <th scope="col">Status</th>
                  <th scope="col">Cash</th>
                  <th scope="col">Deployed</th>
                  <th scope="col">Stopped</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {allDeployments.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/strategies/${d.strategyId}`}>{d.strategyName}</Link>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>{d.id}</td>
                    <td>
                      <StatusBadge status={d.status} />
                    </td>
                    <td className="tabular">₹{Number(d.cash).toLocaleString('en-IN')}</td>
                    <td className="tabular">{formatDateTime(d.deployed_at)}</td>
                    <td className="tabular">
                      {d.status === 'active' ? '—' : formatDateTime(d.stopped_at)}
                    </td>
                    <td>
                      <Link className="btn btn--sm" to={`/strategies/${d.strategyId}/deployment`}>
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
