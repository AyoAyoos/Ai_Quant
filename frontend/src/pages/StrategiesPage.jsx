import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchStrategy, isNetworkError, isNotFound } from '../lib/api.js'
import { readStrategies, removeStrategy } from '../lib/storage.js'
import { formatDateTime, truncate } from '../lib/format.js'
import StatusBadge from '../components/StatusBadge.jsx'
import LoadingBlock, { SkeletonCards } from '../components/Skeletons.jsx'
import Note from '../components/Note.jsx'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'draft', label: 'Draft' },
  { key: 'backtested', label: 'Backtested' },
  { key: 'approved', label: 'Approved' },
  { key: 'paper_trading', label: 'Paper trading' },
  { key: 'rejected', label: 'Rejected' },
]

/**
 * Strategy library.
 *
 * The backend exposes no list endpoint, so the ids come from the local
 * registry and live state is resolved by fanning GET /strategies/{id} out in
 * parallel. Ids the backend no longer knows about are shown as "no longer
 * exists" with a Remove action rather than being hidden.
 */
export default function StrategiesPage() {
  const [entries, setEntries] = useState(() => readStrategies())
  const [details, setDetails] = useState({})
  const [loading, setLoading] = useState(true)
  const [offline, setOffline] = useState(false)
  const [filter, setFilter] = useState('all')

  const load = useCallback(async () => {
    const known = readStrategies()
    setEntries(known)
    setLoading(true)

    if (known.length === 0) {
      setDetails({})
      setLoading(false)
      return
    }

    const results = await Promise.all(
      known.map(async (entry) => {
        try {
          const data = await fetchStrategy(entry.id)
          return [entry.id, { detail: data, missing: false }]
        } catch (err) {
          if (isNotFound(err)) return [entry.id, { detail: null, missing: true }]
          if (isNetworkError(err)) return [entry.id, { detail: null, missing: false, offline: true }]
          return [entry.id, { detail: null, missing: false, failed: true }]
        }
      }),
    )

    const map = {}
    for (const [id, value] of results) map[id] = value
    setDetails(map)
    setOffline(Object.values(map).some((value) => value.offline === true))
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  function handleRemove(id) {
    removeStrategy(id)
    const next = readStrategies()
    setEntries(next)
    setDetails((current) => {
      const copy = { ...current }
      delete copy[id]
      return copy
    })
  }

  const visible = useMemo(() => {
    return entries
      .filter((entry) => {
        if (filter === 'all') return true
        const state = details[entry.id]
        if (!state) return true
        if (state.missing) return false
        return state.detail?.status === filter
      })
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
  }, [entries, details, filter])

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head__text">
          <p className="page-lede">
           
          </p>
        </div>
        <Link className="btn btn--primary" to="/chat">
          New strategy in chat
        </Link>
      </div>

      {offline && (
        <Note tone="warning" title="Backend unreachable">
          Statuses below may be stale. The backend did not answer, so live values could not be refreshed.
        </Note>
      )}

      {entries.length > 0 && (
        <div className="filter-bar" role="group" aria-label="Filter strategies by status">
          {FILTERS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={`filter-chip${filter === option.key ? ' filter-chip--active' : ''}`}
              aria-pressed={filter === option.key}
              onClick={() => setFilter(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <LoadingBlock label="Loading strategies">
          <SkeletonCards count={Math.max(1, Math.min(entries.length, 6))} />
        </LoadingBlock>
      )}

      {!loading && entries.length === 0 && (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">
            ◇
          </span>
          <span className="empty-state__title">No strategies yet</span>
          <p className="empty-state__text">
            Strategies are created by talking to the assistant. Describe an idea in chat, answer the
            follow-up questions, and the finalized strategy is registered here automatically.
          </p>
          <div className="empty-state__actions">
            <Link className="btn btn--primary" to="/chat">
              Go to chat
            </Link>
          </div>
        </div>
      )}

      {!loading && entries.length > 0 && visible.length === 0 && (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">
            ⌕
          </span>
          <span className="empty-state__title">
            No {FILTERS.find((option) => option.key === filter)?.label.toLowerCase()} strategies
          </span>
          <p className="empty-state__text">
            {entries.length} strateg{entries.length === 1 ? 'y is' : 'ies are'} registered in this browser, none
            of which currently has that status.
          </p>
          <div className="empty-state__actions">
            <button type="button" className="btn" onClick={() => setFilter('all')}>
              Show all
            </button>
          </div>
        </div>
      )}

      {!loading && visible.length > 0 && (
        <div className="strategy-grid">
          {visible.map((entry) => {
            const state = details[entry.id]
            const detail = state?.detail
            const missing = state?.missing === true

            return (
              <article key={entry.id} className={`strategy-tile${missing ? ' strategy-tile--missing' : ''}`}>
                <div className="strategy-tile__top">
                  <h2 className="strategy-tile__name">
                    {missing ? entry.name : <Link to={`/strategies/${entry.id}`}>{detail?.name || entry.name}</Link>}
                  </h2>
                  {missing ? (
                    <StatusBadge missing />
                  ) : state?.failed || !detail ? (
                    <StatusBadge label="status unavailable" />
                  ) : (
                    <StatusBadge status={detail.status} />
                  )}
                </div>

                <p className="strategy-tile__desc">
                  {missing
                    ? 'The backend has no strategy with this id. It was probably created against a different database.'
                    : truncate(detail?.description || entry.description || 'No description provided.', 150)}
                </p>

                <div className="strategy-tile__foot">
                  <span className="strategy-tile__time">Created {formatDateTime(entry.createdAt)}</span>
                  <div className="row" style={{ gap: 'var(--sp-1)' }}>
                    {missing ? (
                      <button
                        type="button"
                        className="btn btn--danger btn--sm"
                        onClick={() => handleRemove(entry.id)}
                      >
                        Remove
                      </button>
                    ) : (
                      <>
                        <Link className="btn btn--sm" to={`/strategies/${entry.id}`}>
                          Open
                        </Link>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => handleRemove(entry.id)}
                          title="Remove from this list. The strategy itself is not deleted on the backend."
                        >
                          Remove
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      )}

      <p className="disclaimer-text">
        Removing an entry only deletes it from this browser&apos;s list — the strategy, its backtests and its
        deployment history stay on the backend.
      </p>
    </div>
  )
}