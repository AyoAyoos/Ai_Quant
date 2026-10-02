const LABELS = {
  // StrategyStatus — backend/app/models/db_models.py
  draft: 'draft',
  backtested: 'backtested',
  approved: 'approved',
  paper_trading: 'paper trading',
  rejected: 'rejected',
  // DeploymentStatus
  active: 'active',
  stopped: 'stopped',
}

/**
 * Single status-badge implementation so colours stay identical on every page.
 *
 * `missing` is a UI-only state for a cached id the backend no longer has.
 * An unrecognised status renders neutral with its raw value rather than being
 * coerced to a plausible-looking known state.
 */
export default function StatusBadge({ status, missing = false, label = null }) {
  if (missing) {
    return (
      <span className="status-badge status-badge--missing">
        <span className="status-badge__dot" aria-hidden="true" />
        no longer exists
      </span>
    )
  }

  const raw = typeof status === 'string' && status.trim() ? status : 'unknown'
  const key = raw in LABELS ? raw : null

  return (
    <span className={`status-badge status-badge--${key ?? 'unknown'}`}>
      <span className="status-badge__dot" aria-hidden="true" />
      {label ?? (key ? LABELS[key] : raw)}
    </span>
  )
}