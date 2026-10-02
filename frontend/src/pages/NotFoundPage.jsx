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
          That URL is not part of this app. The workflow has four places to go: describe a strategy in chat,
          browse the library, or open a strategy&apos;s overview.
        </p>
        <div className="empty-state__actions">
          <Link className="btn btn--primary" to="/chat">
            Go to chat
          </Link>
          <Link className="btn" to="/strategies">
            Strategy library
          </Link>
        </div>
      </div>
    </div>
  )
}