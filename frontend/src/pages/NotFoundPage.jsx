import { Link } from 'react-router-dom'

/** Route match that does not exist — never a silent blank screen. */
export default function NotFoundPage() {
  return (
    <div className="page">
      <div className="empty-state">
        <span className="empty-state__icon" aria-hidden="true">
          ⌕
        </span>
        <span className="empty-state__title">Page not found</span>
          <p className="empty-state__text">
            That URL is not part of this app. Start from the overview, describe a strategy in the
            studio, browse the library, backtest, analyze, paper-trade, or check settings and
            documentation.
          </p>
          <div className="empty-state__actions">
            <Link className="btn btn--primary" to="/">
              Go to overview
            </Link>
            <Link className="btn" to="/studio">
              Open studio
            </Link>
            <Link className="btn" to="/strategies">
              Strategy library
            </Link>
          </div>
      </div>
    </div>
  )
}