import { useEffect, useState } from 'react'
import { CheckCircle2, Circle, Loader2 } from 'lucide-react'

const LOADING_STEPS = [
  { key: 'validating', label: 'Validating requirements' },
  { key: 'building', label: 'Building strategy specification' },
  { key: 'generating', label: 'AI generating strategy' },
  { key: 'preparing', label: 'Preparing strategy' },
]

// The backend call is a single await with no step callbacks, so the
// timeline advances on a timer and holds on the final step until done.
const STEP_ADVANCE_MS = 2200

export default function GenerationState({ status, error, onRetry, onViewStrategy, onRunBacktest, strategy }) {
  // status: 'idle' | 'loading' | 'success' | 'error'
  // loading states: 'validating' | 'building' | 'generating' | 'preparing'

  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    if (status !== 'loading') return undefined
    setActiveStep(0)
    const id = setInterval(() => {
      setActiveStep((step) => (step < LOADING_STEPS.length - 1 ? step + 1 : step))
    }, STEP_ADVANCE_MS)
    return () => clearInterval(id)
  }, [status])

  if (status === 'idle') return null

  if (status === 'loading') {
    return (
      <div className="generation-state generation-state--loading" role="status" aria-live="polite">
        <svg className="generation-state__ring" viewBox="0 0 48 48" aria-hidden="true">
          <defs>
            <linearGradient id="gen-ring-gradient" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#403D88" />
              <stop offset="100%" stopColor="#F8B2B2" />
            </linearGradient>
          </defs>
          <circle cx="24" cy="24" r="20" fill="none" stroke="rgba(139, 99, 155, 0.2)" strokeWidth="4" />
          <circle
            cx="24"
            cy="24"
            r="20"
            fill="none"
            stroke="url(#gen-ring-gradient)"
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray="88 38"
          />
        </svg>
        <h3 className="generation-state__title">Generating Your Strategy…</h3>
        <ol className="generation-state__steps">
          {LOADING_STEPS.map((step, index) => {
            const stepState =
              index < activeStep ? 'done' : index === activeStep ? 'active' : 'todo'
            return (
              <li
                key={step.key}
                className={`generation-state__step generation-state__step--${stepState}`}
                aria-current={stepState === 'active' ? 'step' : undefined}
              >
                <span className="generation-state__step-icon" aria-hidden="true">
                  {stepState === 'done' ? (
                    <CheckCircle2 size={20} />
                  ) : stepState === 'active' ? (
                    <Loader2 size={20} />
                  ) : (
                    <Circle size={20} />
                  )}
                </span>
                <span className="generation-state__step-label">{step.label}</span>
              </li>
            )
          })}
        </ol>
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