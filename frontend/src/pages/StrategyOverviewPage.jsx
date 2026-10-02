import { Link, useParams } from 'react-router-dom'
import { canPerform, explainUnavailable } from '../lib/actions.js'
import { formatDateTime } from '../lib/format.js'
import { useStrategyDetail } from '../lib/useStrategy.js'
import CodeViewer from '../components/CodeViewer.jsx'
import Disclosure from '../components/Disclosure.jsx'
import LifecycleStepper from '../components/LifecycleStepper.jsx'
import Note from '../components/Note.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import StrategyTabs from '../components/StrategyTabs.jsx'
import LoadingBlock, { SkeletonBlock, SkeletonTitle } from '../components/Skeletons.jsx'

function MissingPage({ strategyId }) {
  return (
    <div className="page">
      <div className="empty-state">
        <span className="empty-state__icon" aria-hidden="true">
          ⌕
        </span>
        <span className="empty-state__title">Strategy not found</span>
        <p className="empty-state__text">
          The backend has no strategy with id <code>{strategyId}</code>. This usually means the database was
          reset, or the id came from a different environment. Strategies created in this browser stay listed
          on the library page so you can remove stale ones.
        </p>
        <div className="empty-state__actions">
          <Link className="btn btn--primary" to="/strategies">
            Back to library
          </Link>
          <Link className="btn" to="/chat">
            Create a new strategy
          </Link>
        </div>
      </div>
    </div>
  )
}

/** Context actions, driven entirely by the live status. */
function ActionBar({ strategyId, status }) {
  const actions = [
    {
      key: 'backtest',
      label: status === 'backtested' ? 'Re-run backtest' : 'Run backtest',
      to: `/strategies/${strategyId}/backtest`,
      variant: 'primary',
    },
    { key: 'approve', label: 'Approve', to: `/strategies/${strategyId}/approval`, variant: 'positive' },
    { key: 'deploy', label: 'Deploy (paper)', to: `/strategies/${strategyId}/deployment`, variant: 'positive' },
    { key: 'stop', label: 'Stop deployment', to: `/strategies/${strategyId}/deployment`, variant: '' },
    { key: 'reject', label: 'Reject', to: `/strategies/${strategyId}/approval`, variant: 'danger' },
  ]

  const available = actions.filter((action) => canPerform(status, action.key))
  const blocked = actions.filter((action) => !canPerform(status, action.key))

  // Only surface the next real step; a full matrix of greyed buttons is noise.
  const next = available.filter((action) => action.key !== 'reject')
  const showReject = available.some((action) => action.key === 'reject')

  return (
    <div className="stack stack--tight">
      <div className="page-actions">
        {next.map((action) => (
          <Link
            key={action.key}
            className={`btn${action.variant ? ` btn--${action.variant}` : ''}`}
            to={action.to}
          >
            {action.label}
          </Link>
        ))}
        {showReject && (
          <Link className="btn btn--danger" to={`/strategies/${strategyId}/approval`}>
            Reject
          </Link>
        )}
      </div>

      {blocked.some((action) => action.key !== 'reject') && (
        <p className="disclaimer-text">
          {explainUnavailable(status, next[0]?.key ?? 'approve')}
        </p>
      )}
    </div>
  )
}

export default function StrategyOverviewPage() {
  const { id } = useParams()
  const { detail, status, loading, error, notFound, networkError } = useStrategyDetail(id)

  if (loading) {
    return (
      <div className="page">
        <LoadingBlock label="Loading strategy">
          <div className="stack">
            <SkeletonTitle />
            <SkeletonBlock height={110} />
            <SkeletonBlock height={180} />
          </div>
        </LoadingBlock>
      </div>
    )
  }

  if (notFound) return <MissingPage strategyId={id} />

  if (error && !detail) {
    return (
      <div className="page">
        <Note tone="danger" title={networkError ? 'Backend unreachable' : 'Could not load this strategy'}>
          <span>{error.message}</span>
        </Note>
        <div>
          <Link className="btn" to="/strategies">
            Back to library
          </Link>
        </div>
      </div>
    )
  }

  if (!detail) return <MissingPage strategyId={id} />

  const market = detail.market === 'NIFTY50' ? 'NIFTY 50 (^NSEI)' : detail.market

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/strategies">Strategies</Link>
        <span aria-hidden="true">/</span>
        <span>{detail.name}</span>
      </nav>

      <div className="page-head">
        <div className="page-head__text">
          <div className="row">
            <h1 className="page-title">{detail.name}</h1>
            <StatusBadge status={status} />
          </div>
          <p className="page-lede">{detail.description || 'No description was recorded for this strategy.'}</p>
        </div>
        <ActionBar strategyId={id} status={status} />
      </div>

      {detail.status_note && (
        <Note
          tone={status === 'rejected' ? 'danger' : 'info'}
          title={status === 'rejected' ? 'Reason for rejection' : 'Note on this strategy'}
        >
          <span>{detail.status_note}</span>
        </Note>
      )}

      <StrategyTabs strategyId={id} />

      <section className="panel" aria-labelledby="lifecycle-heading">
        <h2 className="section-title" id="lifecycle-heading">
          Lifecycle
        </h2>
        <LifecycleStepper status={status} />
        <p className="disclaimer-text">
          A strategy is created as a draft, becomes backtested when a backtest completes, approved once the
          quality gate passes, and paper-trading while a deployment is active. Stopping returns it to
          approved.
        </p>
      </section>

      <section className="panel" aria-labelledby="facts-heading">
        <h2 className="section-title" id="facts-heading">
          Details
        </h2>
        <div className="kv">
          <div className="kv__item">
            <span className="kv__key">Strategy id</span>
            <span className="kv__value" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
              {detail.strategy_id}
            </span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Market</span>
            <span className="kv__value">{market}</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Status</span>
            <span className="kv__value" style={{ textTransform: 'capitalize' }}>
              {String(status).replace('_', ' ')}
            </span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Loaded at</span>
            <span className="kv__value kv__value--muted">{formatDateTime(new Date())}</span>
          </div>
        </div>
      </section>

      <Disclosure title="Generated strategy code" meta="Python / Backtrader">
        <CodeViewer code={detail.generated_code} />
        <p className="disclaimer-text">
          The code runs only inside a sandboxed subprocess: imports are restricted to backtrader, pandas,
          numpy, math and datetime, dangerous builtins are rejected before execution, and the run is capped
          at 120 seconds.
        </p>
      </Disclosure>
    </div>
  )
}