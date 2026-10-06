import { INDICATORS } from './indicatorCatalog.js'

export default function IndicatorsSection({ value, onChange, error }) {
  // value is an array of indicator ids, e.g., ['EMA', 'RSI']
  // onChange receives updated array

  const handleToggle = (indicatorId) => {
    onChange(value.includes(indicatorId)
      ? value.filter((id) => id !== indicatorId)
      : [...value, indicatorId]
    )
  }

  return (
    <section className="strategy-section" aria-labelledby="indicators-heading">
      <div className="strategy-section__head">
        <h2 id="indicators-heading" className="strategy-section__title">Which indicators do you want to use?</h2>
      </div>

      <div className="indicators-grid" role="group" aria-label="Select indicators">
        {INDICATORS.map((indicator) => {
          const selected = value.includes(indicator.id)
          return (
            <button
              key={indicator.id}
              type="button"
              className={`indicator-card${selected ? ' indicator-card--selected' : ''}`}
              onClick={() => handleToggle(indicator.id)}
              aria-pressed={selected}
            >
              <span className="indicator-card__name">{indicator.name}</span>
              <span className="indicator-card__desc">{indicator.description}</span>
              {selected && <span className="indicator-card__check" aria-hidden="true">✓</span>}
            </button>
          )
        })}
      </div>

      {/* Conditional parameter fields for selected indicators */}
      {value.length > 0 && (
        <div className="indicator-params" aria-label="Indicator parameters">
          {value.map((indicatorId) => {
            const indicator = INDICATORS.find((i) => i.id === indicatorId)
            if (!indicator || indicator.params.length === 0) return null

            return (
              <div key={indicatorId} className="indicator-param-panel">
                <h3 className="indicator-param-panel__title">{indicator.name} Settings</h3>
                <div className="form-grid">
                  {indicator.params.map((param) => (
                    <div key={param.key} className="field">
                      <label htmlFor={`indicator-${indicatorId}-${param.key}`} className="field__label">
                        {param.label}
                      </label>
                      <div className="field__control">
                        <input
                          type="number"
                          id={`indicator-${indicatorId}-${param.key}`}
                          className="field__input"
                          min={param.min}
                          max={param.max}
                          step={param.step || 1}
                          defaultValue={param.default}
                          onChange={(e) => onChange(value, indicatorId, param.key, Number(e.target.value))}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {error && <p className="field__error" role="alert">{error}</p>}
    </section>
  )
}