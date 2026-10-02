import { Link } from 'react-router-dom'

/**
 * Compact reference card rendered under a chat reply that produced a strategy.
 * Only a link lives here — the full workflow lives on the strategy pages.
 *
 * Deliberately carries no status badge: the cached thread can be hours old, so
 * the live status shown on the strategy pages is the only one worth displaying.
 */
export default function StrategyMiniCard({ strategy }) {
  return (
    <div className="mini-card">
      <div className="mini-card__top">
        <span className="mini-card__label">Strategy created</span>
        <span className="tag">NIFTY 50</span>
      </div>
      <span className="mini-card__name">{strategy.strategy_name || 'Untitled Strategy'}</span>
      {strategy.strategy_description && <p className="mini-card__desc">{strategy.strategy_description}</p>}
      <div>
        <Link className="btn btn--primary btn--sm" to={`/strategies/${strategy.strategy_id}`}>
          Open strategy
        </Link>
      </div>
    </div>
  )
}