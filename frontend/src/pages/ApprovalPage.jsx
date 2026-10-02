import { useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { approveStrategy, rejectStrategy } from '../lib/api.js'
import { canPerform, explainUnavailable } from '../lib/actions.js'
import { useCachedBacktest, useStrategyDetail } from '../lib/useStrategy.js'
import BenchmarkVerdict from '../components/BenchmarkVerdict.jsx'
import MetricGrid from '../components/MetricGrid.jsx'
import Note from '../components/Note.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import StrategyTabs from '../components/StrategyTabs.jsx'
import LoadingBlock, { SkeletonBlock, SkeletonTitle } from '../components/Skeletons.jsx'

/**
 * The gate thresholds below are the user's own decision criteria, not
 * something the backend reports. The backend itself accepts any backtested
 * strategy, so this page is the honest place to state what "good" means.
 */
const CRITERIA = [
  {
    key: 'max_drawdown_pct',
    label: 'Max drawdown under 25%',
    test: (m) => m.max_drawdown_pct !== null && m.max_drawdown_pct < 25,
    fail: (m) =>
      m.max_drawdown_pct === null
        ? 'No drawdown was recorded.'
        : `Drawdown reached ${m.max_drawdown_pct.toFixed(2)}%, above the 25% ceiling.`,
  },
  {
    key: 'num_trades',
    label: 'At least 10 closed trades',
    test: (m) => m.num_trades !== null && m.num_trades >= 10,
    fail: (m) =>
      m.num_trades === null
        ? 'No trade count was recorded.'
        : `Only ${m.num_trades} closed trade${m.num_trades === 1 ? '' : 's'} — too thin to judge.`,
  },
  {
    key: 'sharpe',
    label: 'Sharpe ratio above 0.5',
    test: (m) => m.sharpe !== null && m.sharpe > 0.5,
    fail: (m) => (m.sharpe === null ? 'No Sharpe ratio was recorded.' : `Sharpe was ${m.sharpe.toFixed(2)}.`),
  },
  {
    key: 'win_rate_pct',
    label: 'Win rate above 40%',
    test: (m) => m.win_rate_pct !== null && m.win_rate_pct > 40,
    fail: (m) =>
      m.win_rate_pct === null ? 'No win rate was recorded.' : `Win rate was ${m.win_rate_pct.toFixed(2)}%.`,
  },
]

function CriteriaList({ metrics }) {
  const rows = useMemo(
    () => CRITERIA.map((criterion) => ({ ...criterion, pass: criterion.test(metrics) })),
    [metrics],
  )
  const passed = rows.filter((row) => row.pass).length

  return (
    <div className="panel">
      <div className="panel__head">
        <h2 className="section-title">Quality gate</h2>
        <span className="tabular" style={{ color: 'var(--muted)', fontSize: 'var(--fs-sm)' }}>
          {passed} of {rows.length} criteria met
        </span>
      </div>

      <ul className="criteria-list">
        {rows.map((row) => (
          <li key={row.key} className="criteria-row">
            <span className={`criteria-row__mark${row.pass ? ' criteria-row__mark--pass' : ''}`} aria-hidden="true">
              {row.pass ? '✓' : '✕'}
            </span>
            <span className="criteria-row__body">
              <span className="criteria-row__label">{row.label}</span>
              <span className="criteria-row__note">{row.pass ? 'Met.' : row.fail(metrics)}</span>
            </span>
            <span className="visually-hidden">{row.pass ? 'met' : 'not met'}</span>
          </li>
        ))}
      </ul>

      <Note tone={passed === rows.length ? 'success' : 'warning'} title={passed === rows.length ? 'All criteria met' : 'Some criteria are not met'}>
        <span>
          {passed === rows.length
            ? 'The backtest clears the gate. The backend will approve it; the choice to proceed is yours.'
            : 'The backend does not enforce these thresholds, so it will still approve this strategy if you ask it to. Approving a strategy that fails its own gate is the main way a paper-trading prototype misleads you.'}
        </span>
      </Note>
    </div>
  )
}

export default function ApprovalPage() {
  const { id } = useParams()
  const { detail, status, loading, notFound, refresh } = useStrategyDetail(id)
  const cached = useCachedBacktest(id)
  const metrics = cached?.result ?? null

  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(null)
  const [confirmReject, setConfirmReject] = useState(false)

  const reasonRef = useRef(null)

  async function handleApprove() {
    if (busy) return
    setBusy('approve')
    setError(null)
    try {
      const gate = await approveStrategy(id)
      setDone(gate)
      await refresh()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }

  async function handleReject() {
    if (busy || reason.trim().length < 3) return
    setBusy('reject')
    setError(null)
    try {
      const gate = await rejectStrategy(id, reason.trim())
      setDone(gate)
      setReason('')
      setConfirmReject(false)
      await refresh()
    } catch (err) {
      setError(err)
      setConfirmReject(false)
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
            <SkeletonBlock height={220} />
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

  const canApprove = canPerform(status, 'approve')
  const canReject = canPerform(status, 'reject')
  const afterApprove = status === 'approved'

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/strategies">Strategies</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/strategies/${id}`}>{detail.name}</Link>
        <span aria-hidden="true">/</span>
        <span>Approval</span>
      </nav>

      <div className="page-head">
        <div className="page-head__text">
          <div className="row">
            <h1 className="page-title">Approval gate</h1>
            <StatusBadge status={status} />
          </div>
          <p className="page-lede">
            Approving is the point of no return for the backtest data — after approval the strategy cannot be
            re-run until a deployment stops. Rejecting makes it read-only.
          </p>
        </div>
        <StrategyTabs strategyId={id} />
      </div>

      {detail.status_note && (
        <Note tone={status === 'rejected' ? 'danger' : 'info'} title="Status note">
          <span>{detail.status_note}</span>
        </Note>
      )}

      {done && (
        <Note tone="success" title={done.status === 'rejected' ? 'Strategy rejected' : 'Strategy approved'}>
          <span>
            Status is now <strong>{String(done.status).replace('_', ' ')}</strong>.{' '}
            {done.status === 'approved'
              ? 'It can now be deployed in paper mode.'
              : 'It is now read-only — create a new strategy in chat to keep working.'}
          </span>
        </Note>
      )}

      {error && (
        <Note tone="danger" title={error.status === 422 ? 'The backend refused that' : 'Request failed'} reasons={error.reasons}>
          <span>{error.message}</span>
        </Note>
      )}

      {!metrics ? (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">
            ⌕
          </span>
          <span className="empty-state__title">No backtest to review</span>
          <p className="empty-state__text">
            The backend stores backtests but exposes no endpoint to read one back, and this browser has no
            cached copy — most likely a different browser or device. Run the backtest here to review the
            numbers.
          </p>
          <div className="empty-state__actions">
            <Link className="btn btn--primary" to={`/strategies/${id}/backtest`}>
              Go to backtest
            </Link>
          </div>
        </div>
      ) : (
        <section className="stack" aria-label="Backtest under review">
          <MetricGrid result={metrics} />
          <BenchmarkVerdict result={metrics} />
          <CriteriaList metrics={metrics} />
        </section>
      )}

      <section className="panel" aria-labelledby="actions-heading">
        <h2 className="section-title" id="actions-heading">
          Decision
        </h2>

        {afterApprove ? (
          <Note tone="success" title="Already approved">
            <span>
              This strategy passed the gate. Deployment is the next step — it can run in paper mode only,
              never with real money.
            </span>
          </Note>
        ) : (
          <>
            {!canApprove && (
              <p className="disclaimer-text" style={{ marginBottom: 'var(--sp-3)' }}>
                {explainUnavailable(status, 'approve')}
              </p>
            )}
            {!canReject && status !== 'approved' && (
              <p className="disclaimer-text" style={{ marginBottom: 'var(--sp-3)' }}>
                {explainUnavailable(status, 'reject')}
              </p>
            )}

            <div className="page-actions">
              <button
                type="button"
                className="btn btn--positive"
                onClick={handleApprove}
                disabled={!canApprove || busy !== null}
              >
                {busy === 'approve' && <span className="btn__spinner" aria-hidden="true" />}
                {busy === 'approve' ? 'Approving…' : 'Approve strategy'}
              </button>

              {!confirmReject ? (
                <button
                  type="button"
                  className="btn btn--danger"
                  onClick={() => setConfirmReject(true)}
                  disabled={!canReject || busy !== null}
                >
                  Reject strategy
                </button>
              ) : (
                <div className="reject-form">
                  <label className="field__label" htmlFor="reject-reason">
                    Why is this strategy being rejected?
                  </label>
                  <div className="row">
                    <input
                      ref={reasonRef}
                      id="reject-reason"
                      className="field__input"
                      type="text"
                      maxLength={500}
                      value={reason}
                      placeholder="e.g. Too few trades to judge"
                      onChange={(event) => setReason(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && reason.trim().length >= 3) handleReject()
                      }}
                    />
                    <button
                      type="button"
                      className="btn btn--danger"
                      onClick={handleReject}
                      disabled={reason.trim().length < 3 || busy !== null}
                    >
                      {busy === 'reject' ? 'Rejecting…' : 'Confirm rejection'}
                    </button>
                    <button type="button" className="btn btn--ghost" onClick={() => setConfirmReject(false)}>
                      Cancel
                    </button>
                  </div>
                  <span className="field__hint">
                    Stored as the strategy&apos;s status note. 3–500 characters. {reason.trim().length}/500.
                  </span>
                </div>
              )}
            </div>
          </>
        )}

        <p className="disclaimer-text">
          Approval is a workflow state, not investment advice. Past performance does not guarantee future
          results. Educational prototype — paper trading only.
        </p>
      </section>
    </div>
  )
}