import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { deployStrategy, fetchDeployments, stopDeployment } from '../lib/api.js'
import { canPerform, explainUnavailable } from '../lib/actions.js'
import { formatDateTime } from '../lib/format.js'
import { useStrategyDetail } from '../lib/useStrategy.js'
import Note from '../components/Note.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import StrategyTabs from '../components/StrategyTabs.jsx'
import LoadingBlock, { SkeletonBlock, SkeletonTitle } from '../components/Skeletons.jsx'

const DEFAULTS = { cash: 100000, commissionPct: 0.1, sizerPercent: 95 }

function DeploymentRow({ deployment }) {
  const active = deployment.status === 'active'
  return (
    <tr>
      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>{deployment.id}</td>
      <td>
        <StatusBadge status={deployment.status} />
      </td>
      <td className="tabular">₹{Number(deployment.cash).toLocaleString('en-IN')}</td>
      <td className="tabular">{Number(deployment.commission_pct).toFixed(2)}%</td>
      <td className="tabular">{Number(deployment.sizer_percents).toFixed(1)}%</td>
      <td className="tabular">{formatDateTime(deployment.deployed_at)}</td>
      <td className="tabular">
        {active ? <span style={{ color: 'var(--muted)' }}>—</span> : formatDateTime(deployment.stopped_at)}
      </td>
      <td>{deployment.stop_reason || <span style={{ color: 'var(--muted)' }}>—</span>}</td>
    </tr>
  )
}

export default function DeploymentPage() {
  const { id } = useParams()
  const { detail, status, loading, notFound, refresh } = useStrategyDetail(id)

  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [values, setValues] = useState(DEFAULTS)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [stopReason, setStopReason] = useState('')

  const loadHistory = useCallback(async () => {
    try {
      const data = await fetchDeployments(id)
      setHistory(Array.isArray(data) ? data : [])
    } catch {
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }, [id])

  useEffect(() => {
    if (!id) return
    setHistoryLoading(true)
    loadHistory()
  }, [id, loadHistory])

  async function handleDeploy() {
    if (busy) return
    setBusy('deploy')
    setError(null)
    setNotice(null)
    try {
      const gate = await deployStrategy(id, values)
      setNotice(`Deployment created. The strategy is now ${String(gate.status).replace('_', ' ')}.`)
      await Promise.all([refresh(), loadHistory()])
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }

  async function handleStop() {
    if (busy) return
    setBusy('stop')
    setError(null)
    setNotice(null)
    try {
      const gate = await stopDeployment(id, stopReason.trim() || null)
      setNotice(`Deployment stopped. The strategy is now ${String(gate.status).replace('_', ' ')}.`)
      setStopReason('')
      await Promise.all([refresh(), loadHistory()])
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }

  if (loading) {
    return (
      <div className="page">
        <LoadingBlock label="Loading strategy">
          <div className="stack">
            <SkeletonTitle />
            <SkeletonBlock height={200} />
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

  const canDeploy = canPerform(status, 'deploy')
  const canStop = canPerform(status, 'stop')
  const active = status === 'paper_trading' ? history.find((d) => d.status === 'active') : null

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/strategies">Strategies</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/strategies/${id}`}>{detail.name}</Link>
        <span aria-hidden="true">/</span>
        <span>Deployment</span>
      </nav>

      <div className="page-head">
        <div className="page-head__text">
          <div className="row">
            <h1 className="page-title">Deployment</h1>
            <StatusBadge status={status} />
          </div>
          <p className="page-lede">
            Paper trading means the strategy runs the same execution path against simulated fills. No broker
            is connected, no order leaves this machine, and no real money is ever at risk.
          </p>
        </div>
        <StrategyTabs strategyId={id} />
      </div>

      {notice && (
        <Note tone="success" title="Deployment updated">
          <span>{notice}</span>
        </Note>
      )}

      {error && (
        <Note tone="danger" title={error.status === 422 ? 'The backend refused that' : 'Request failed'} reasons={error.reasons}>
          <span>{error.message}</span>
        </Note>
      )}

      {active && (
        <section className="panel panel--accent" aria-labelledby="active-heading">
          <div className="panel__head">
            <h2 className="section-title" id="active-heading">
              Active deployment
            </h2>
            <StatusBadge status="active" />
          </div>
          <div className="kv">
            <div className="kv__item">
              <span className="kv__key">Deployment id</span>
              <span className="kv__value" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
                {active.id}
              </span>
            </div>
            <div className="kv__item">
              <span className="kv__key">Deployed at</span>
              <span className="kv__value">{formatDateTime(active.deployed_at)}</span>
            </div>
            <div className="kv__item">
              <span className="kv__key">Starting cash</span>
              <span className="kv__value tabular">₹{Number(active.cash).toLocaleString('en-IN')}</span>
            </div>
            <div className="kv__item">
              <span className="kv__key">Commission</span>
              <span className="kv__value tabular">{Number(active.commission_pct).toFixed(2)}%</span>
            </div>
            <div className="kv__item">
              <span className="kv__key">Position size</span>
              <span className="kv__value tabular">{Number(active.sizer_percents).toFixed(1)}%</span>
            </div>
          </div>

          <div className="page-actions">
            <button type="button" className="btn btn--danger" onClick={handleStop} disabled={busy !== null}>
              {busy === 'stop' && <span className="btn__spinner" aria-hidden="true" />}
              {busy === 'stop' ? 'Stopping…' : 'Stop deployment'}
            </button>
          </div>

          <div className="field" style={{ maxWidth: '420px' }}>
            <label className="field__label" htmlFor="stop-reason">
              Reason (optional)
            </label>
            <input
              id="stop-reason"
              className="field__input"
              type="text"
              maxLength={500}
              value={stopReason}
              placeholder="e.g. Reached the date limit"
              onChange={(event) => setStopReason(event.target.value)}
            />
            <span className="field__hint">Stored on the deployment record. 500 characters max.</span>
          </div>
        </section>
      )}

      <section className="panel" aria-labelledby="deploy-heading">
        <div className="panel__head">
          <h2 className="section-title" id="deploy-heading">
            Start a paper deployment
          </h2>
        </div>

        {!canDeploy && (
          <Note tone="warning" title={`Not available at status "${status}"`}>
            <span>{explainUnavailable(status, 'deploy')}</span>
          </Note>
        )}

        <form className="form-grid" onSubmit={(event) => event.preventDefault()}>
          <div className="field">
            <label className="field__label" htmlFor="deploy-cash">
              Starting cash
            </label>
            <div className="field__control">
              <input
                id="deploy-cash"
                className="field__input"
                type="number"
                step="any"
                min="0"
                value={values.cash}
                disabled={!canDeploy}
                onChange={(event) => setValues((c) => ({ ...c, cash: event.target.value === '' ? '' : Number(event.target.value) }))}
              />
              <span className="field__suffix">₹</span>
            </div>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="deploy-commission">
              Commission
            </label>
            <div className="field__control">
              <input
                id="deploy-commission"
                className="field__input"
                type="number"
                step="any"
                min="0"
                value={values.commissionPct}
                disabled={!canDeploy}
                onChange={(event) =>
                  setValues((c) => ({ ...c, commissionPct: event.target.value === '' ? '' : Number(event.target.value) }))
                }
              />
              <span className="field__suffix">%</span>
            </div>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="deploy-sizer">
              Position size
            </label>
            <div className="field__control">
              <input
                id="deploy-sizer"
                className="field__input"
                type="number"
                step="any"
                min="0"
                value={values.sizerPercent}
                disabled={!canDeploy}
                onChange={(event) =>
                  setValues((c) => ({ ...c, sizerPercent: event.target.value === '' ? '' : Number(event.target.value) }))
                }
              />
              <span className="field__suffix">%</span>
            </div>
          </div>
        </form>

        <div className="page-actions">
          <button type="button" className="btn btn--positive" onClick={handleDeploy} disabled={!canDeploy || busy !== null}>
            {busy === 'deploy' && <span className="btn__spinner" aria-hidden="true" />}
            {busy === 'deploy' ? 'Deploying…' : 'Deploy in paper mode'}
          </button>
          {canStop && !active && (
            <Link className="btn btn--danger" to={`/strategies/${id}/deployment`}>
              Stop active deployment
            </Link>
          )}
        </div>

        <p className="disclaimer-text">
          Past performance does not guarantee future results. Educational prototype — paper trading only.
        </p>
      </section>

      <section className="panel" aria-labelledby="history-heading">
        <div className="panel__head">
          <h2 className="section-title" id="history-heading">
            Deployment history
          </h2>
          {!historyLoading && <span className="disclaimer-text">{history.length} record{history.length === 1 ? '' : 's'}</span>}
        </div>

        {historyLoading ? (
          <SkeletonBlock height={90} />
        ) : history.length === 0 ? (
          <p className="disclaimer-text">
            No deployment has ever been created for this strategy. The backend returns an empty list until
            the first successful deploy.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">All deployments for {detail.name}</caption>
              <thead>
                <tr>
                  <th scope="col">Deployment</th>
                  <th scope="col">Status</th>
                  <th scope="col">Starting cash</th>
                  <th scope="col">Commission</th>
                  <th scope="col">Size</th>
                  <th scope="col">Deployed</th>
                  <th scope="col">Stopped</th>
                  <th scope="col">Reason</th>
                </tr>
              </thead>
              <tbody>
                {history.map((deployment) => (
                  <DeploymentRow key={deployment.id} deployment={deployment} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}