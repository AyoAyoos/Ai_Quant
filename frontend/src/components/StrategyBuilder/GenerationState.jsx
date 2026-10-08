import { CheckCircle2 } from 'lucide-react'

export default function GenerationState({ status, error, onRetry, onViewStrategy, onRunBacktest, strategy }) {
  // status: 'idle' | 'loading' | 'success' | 'error'
  // loading states: 'validating' | 'building' | 'generating' | 'preparing'

  const loadingSteps = [
    { key: 'validating', label: 'Validating requirements' },
    { key: 'building', label: 'Building strategy specification' },
    { key: 'generating', label: 'AI generating strategy' },
    { key: 'preparing', label: 'Preparing strategy' },
  ]

  if (status === 'idle') return null

  if (status === 'loading') {
    return (
      <div className="generation-state generation-state--loading" role="status" aria-live="polite">
        <div className="generation-state__spinner" aria-hidden="true" />
        <h3 className="generation-state__title">Generating Your Strategy…</h3>
        <div className="generation-state__steps">
          {loadingSteps.map((step) => (
            <div key={step.key} className="generation-state__step">
              <span className={`generation-state__step-icon`} aria-hidden="true">
                {step.key === 'generating' ? '●' : '○'}
              </span>
              <span className="generation-state__step-label">{step.label}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (status === 'success') {
    return (
      <div className="generation-state generation-state--success" role="status" aria-live="polite">
        <div className="generation-state__head">
          <span className="generation-state__success-icon" aria-hidden="true">
            <CheckCircle2 size={24} />
          </span>
          <h3 className="generation-state__title">Strategy Generated</h3>
        </div>
        {strategy && (
          <div className="generation-state__details">
            <dl className="generation-state__grid">
              <div className="generation-state__field">
                <dt className="generation-state__label">Name</dt>
                <dd className="generation-state__value">{strategy.name}</dd>
              </div>
              <div className="generation-state__field">
                <dt className="generation-state__label">Status</dt>
                <dd className="generation-state__value">
                  <span className="status-badge status-badge--draft">{strategy.status}</span>
                </dd>
              </div>
              <div className="generation-state__field generation-state__field--wide">
                <dt className="generation-state__label">Description</dt>
                <dd className="generation-state__value">{strategy.description}</dd>
              </div>
            </dl>
            <div className="generation-state__actions">
              {onViewStrategy && (
                <button
                  type="button"
                  className="btn generation-state__btn--secondary"
                  onClick={onViewStrategy}
                >
                  View Strategy
                </button>
              )}
              {onRunBacktest && (
                <button
                  type="button"
                  className="btn generation-state__btn--primary"
                  onClick={onRunBacktest}
                >
                  Run Backtest
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="generation-state generation-state--error" role="alert">
        <div className="generation-state__error-icon" aria-hidden="true">✕</div>
        <h3 className="generation-state__title">Generation Failed</h3>
        <p className="generation-state__message">
          {error || 'Unable to generate the strategy. Please check your configuration and try again.'}
        </p>
        <button type="button" className="btn btn--primary" onClick={onRetry}>
          Try Again
        </button>
      </div>
    )
  }

  return null
}