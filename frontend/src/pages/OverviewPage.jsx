import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchDeployments, fetchHealth, fetchStrategy } from '../lib/api.js'
import { getCachedBacktest, readStrategies } from '../lib/storage.js'
import { formatDateTime } from '../lib/format.js'
import StatusBadge from '../components/StatusBadge.jsx'
import Note from '../components/Note.jsx'

/**
 * Overview / Dashboard — page 1 of the 7-page split.
 *
 * UI ORGANIZATION ONLY. No backend, API, calculation or workflow change.
 * Every value below comes from an existing source:
 *   - strategy registry + live GET /strategies/{id} (same as StrategiesPage)
 *   - GET /health (same contract as lib/api.js)
 *   - browser-cached backtests (same as BacktestPage)
 *   - GET /strategies/{id}/deployments (same as DeploymentPage)
 *   - static pipeline/security strings already documented on the landing page
 */

function useOverviewData() {
  const [entries, setEntries] = useState(() => readStrategies())
  const [statusById, setStatusById] = useState({})
  const [health, setHealth] = useState('checking')
  const [deployments, setDeployments] = useState([])
  const [backtestedCount, setBacktestedCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    const known = readStrategies()
    setEntries(known)

    fetchHealth()
      .then(() => {
        if (!cancelled) setHealth('online')
      })
      .catch(() => {
        if (!cancelled) setHealth('offline')
      })

    if (known.length === 0) {
      setStatusById({})
      setDeployments([])
      setBacktestedCount(0)
      return () => {
        cancelled = true
      }
    }

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

    let cached = 0
    for (const entry of known) {
      if (getCachedBacktest(entry.id)) cached += 1
    }
    setBacktestedCount(cached)

    Promise.all(
      known.map(async (entry) => {
        try {
          const list = await fetchDeployments(entry.id)
          return Array.isArray(list) ? list.map((d) => ({ ...d, strategyId: entry.id })) : []
        } catch {
          return []
        }
      }),
    ).then((lists) => {
      if (!cancelled) setDeployments(lists.flat())
    })

    return () => {
      cancelled = true
    }
  }, [])

  return { entries, statusById, health, deployments, backtestedCount }
}

const SYSTEM_ROWS = [
  { label: 'Backtest engine', value: 'Backtrader 1.9.78.123 · 120 s watchdog', key: 'engine' },
  { label: 'NIFTY 50 data', value: '^NSEI daily via Yahoo Finance · local CSV cache', key: 'data' },
  { label: 'AI / LLM', value: 'Groq · openai/gpt-oss-120b · key required for chat', key: 'ai' },
  { label: 'Security sandbox', value: 'AST allowlist · subprocess isolation · 1 GB / 120 s / 256 KB', key: 'sandbox' },
]

export default function OverviewPage() {
  const { entries, statusById, health, deployments, backtestedCount } = useOverviewData()

  const counts = { draft: 0, backtested: 0, approved: 0, paper_trading: 0, rejected: 0 }
  for (const entry of entries) {
    const status = statusById[entry.id]
    if (status && counts[status] !== undefined) counts[status] += 1
  }
  const activeDeployments = deployments.filter((d) => d.status === 'active')
  const recent = [...entries]
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    .slice(0, 5)

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">Overview</h1>
          <p className="page-lede">
            Quick overview of the current system — strategies, paper-trading status, key metrics and
            engine health. Create in the Studio, manage under Strategies, run under Backtesting.
          </p>
        </div>
        <div className="page-actions">
          <Link className="btn btn--primary" to="/studio">
            Open Strategy Studio
          </Link>
          <Link className="btn" to="/strategies">
            View strategies
          </Link>
        </div>
      </div>

      <section className="panel" aria-labelledby="overview-metrics">
        <h2 className="section-title" id="overview-metrics">
          Key metrics
        </h2>
        <div className="metrics-grid">
          <div className="metric">
            <span className="metric__value">{entries.length}</span>
            <span className="metric__label">Strategies registered</span>
          </div>
          <div className="metric">
            <span className="metric__value">{backtestedCount}</span>
            <span className="metric__label">Backtests cached (this browser)</span>
          </div>
          <div className="metric">
            <span className="metric__value">{counts.approved}</span>
            <span className="metric__label">Approved</span>
          </div>
          <div className="metric">
            <span className="metric__value">{activeDeployments.length}</span>
            <span className="metric__label">Active paper deployments</span>
          </div>
        </div>
        <p className="disclaimer-text">
          Counts come from this browser&apos;s registry with live status read from the backend — the
          same source as the Strategies page. Nothing here is recalculated.
        </p>
      </section>

      <section className="panel" aria-labelledby="overview-recent">
        <div className="panel__head">
          <h2 className="section-title" id="overview-recent">
            Recent strategies
          </h2>
          <Link className="btn btn--sm" to="/strategies">
            Open library
          </Link>
        </div>
        {recent.length === 0 ? (
          <p className="disclaimer-text">
            No strategies yet. Describe an idea in the Strategy Studio and the finalized strategy is
            registered here automatically.
          </p>
        ) : (
          <div className="strategy-grid">
            {recent.map((entry) => (
              <article key={entry.id} className="strategy-tile">
                <div className="strategy-tile__top">
                  <h3 className="strategy-tile__name">
                    <Link to={`/strategies/${entry.id}`}>{entry.name}</Link>
                  </h3>
                  {statusById[entry.id] ? (
                    <StatusBadge status={statusById[entry.id]} />
                  ) : (
                    <StatusBadge label="status unavailable" />
                  )}
                </div>
                <div className="strategy-tile__foot">
                  <span className="strategy-tile__time">Created {formatDateTime(entry.createdAt)}</span>
                  <Link className="btn btn--sm" to={`/strategies/${entry.id}`}>
                    Open
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="overview-paper">
        <div className="panel__head">
          <h2 className="section-title" id="overview-paper">
            Paper-trading summary
          </h2>
          <Link className="btn btn--sm" to="/paper-trading">
            Open paper trading
          </Link>
        </div>
        {activeDeployments.length === 0 ? (
          <p className="disclaimer-text">
            No active paper deployment. Paper trading only — no live orders, no broker integration.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">Active paper deployments</caption>
              <thead>
                <tr>
                  <th scope="col">Deployment</th>
                  <th scope="col">Cash</th>
                  <th scope="col">Deployed</th>
                </tr>
              </thead>
              <tbody>
                {activeDeployments.slice(0, 5).map((d) => (
                  <tr key={d.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>{d.id}</td>
                    <td className="tabular">₹{Number(d.cash).toLocaleString('en-IN')}</td>
                    <td className="tabular">{formatDateTime(d.deployed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="overview-system">
        <div className="panel__head">
          <h2 className="section-title" id="overview-system">
            System status
          </h2>
          <Link className="btn btn--sm" to="/settings">
            Open settings / system
          </Link>
        </div>
        <div className="kv">
          <div className="kv__item">
            <span className="kv__key">Backend</span>
            <span className="kv__value">
              {health === 'online' ? 'Online' : health === 'offline' ? 'Unreachable' : 'Checking…'}
            </span>
          </div>
          {SYSTEM_ROWS.map((row) => (
            <div className="kv__item" key={row.key}>
              <span className="kv__key">{row.label}</span>
              <span className="kv__value kv__value--muted">{row.value}</span>
            </div>
          ))}
        </div>
        <p className="disclaimer-text">
          Detailed security and infrastructure reference lives under Settings → Security and in
          Documentation — kept off this page on purpose.
        </p>
      </section>

      <section className="panel" aria-labelledby="overview-actions">
        <h2 className="section-title" id="overview-actions">
          Quick actions
        </h2>
        <div className="page-actions">
          <Link className="btn btn--primary" to="/studio">
            Open Strategy Studio
          </Link>
          <Link className="btn" to="/backtests">
            Run a backtest
          </Link>
          <Link className="btn" to="/analytics">
            Analyze results
          </Link>
          <Link className="btn btn--ghost" to="/docs">
            How it works
          </Link>
        </div>
      </section>

      <Note tone="warning" title="Regulatory & algorithmic safety notice">
        <span>
          <strong>Educational prototype. Paper trading only. No live orders.</strong> This tool runs
          deterministic simulation and paper-trading bookkeeping on historical NIFTY 50 data. It is
          not investment advice and places no orders of any kind. Past backtested performance does
          not guarantee future returns.
        </span>
      </Note>
    </div>
  )
}
