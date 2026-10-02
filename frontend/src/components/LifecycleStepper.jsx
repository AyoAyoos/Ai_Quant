import { Fragment } from 'react'

const STEPS = [
  { key: 'draft', label: 'Draft' },
  { key: 'backtested', label: 'Backtested' },
  { key: 'approved', label: 'Approved' },
  { key: 'paper_trading', label: 'Paper trading' },
]

/**
 * Lifecycle stepper.
 *
 * `rejected` is drawn as a branch off the track rather than a fifth step,
 * because rejection is terminal for that strategy. The backend allows it only
 * from draft or backtested, so those are the steps shown as reached.
 */
export default function LifecycleStepper({ status }) {
  const rejected = status === 'rejected'
  const index = STEPS.findIndex((step) => step.key === status)
  const activeIndex = rejected ? 1 : index

  return (
    <div className="stepper">
      <div className="stepper__track">
        {STEPS.map((step, i) => {
          const done = activeIndex > i
          const current = activeIndex === i
          const state = current ? 'current' : done ? 'done' : ''
          return (
            <Fragment key={step.key}>
              {i > 0 && (
                <span
                  className={`stepper__link${done || current ? ' stepper__link--done' : ''}`}
                  aria-hidden="true"
                />
              )}
              <span className={`stepper__node stepper__node--${state}`}>
                <span className="stepper__dot" aria-hidden="true">
                  {done ? '✓' : i + 1}
                </span>
                <span className="stepper__label">
                  {step.label}
                  {current && <span className="visually-hidden"> — current step</span>}
                </span>
              </span>
            </Fragment>
          )
        })}
      </div>

      {rejected && (
        <div className="stepper__branch">
          <span className="stepper__node stepper__node--rejected">
            <span className="stepper__dot" aria-hidden="true">
              ✕
            </span>
            <span className="stepper__label">Rejected</span>
          </span>
          <span className="stepper__branch-label">
            Rejected from draft or backtested, so approval and deployment are no longer reachable for this
            strategy.
          </span>
        </div>
      )}
    </div>
  )
}