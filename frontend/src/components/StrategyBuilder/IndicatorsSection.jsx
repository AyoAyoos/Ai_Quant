const INDICATORS = [
  {
    id: 'EMA',
    name: 'EMA',
    description: 'Exponential Moving Average',
    params: [
      { key: 'fast', label: 'Fast Period', type: 'number', min: 1, max: 200, default: 20 },
      { key: 'slow', label: 'Slow Period', type: 'number', min: 1, max: 200, default: 50 },
    ],
  },
  {
    id: 'SMA',
    name: 'SMA',
    description: 'Simple Moving Average',
    params: [
      { key: 'period', label: 'Period', type: 'number', min: 1, max: 200, default: 20 },
    ],
  },
  {
    id: 'RSI',
    name: 'RSI',
    description: 'Relative Strength Index',
    params: [
      { key: 'period', label: 'Period', type: 'number', min: 1, max: 100, default: 14 },
      { key: 'oversold', label: 'Oversold', type: 'number', min: 1, max: 50, default: 30 },
      { key: 'overbought', label: 'Overbought', type: 'number', min: 50, max: 100, default: 70 },
    ],
  },
  {
    id: 'MACD',
    name: 'MACD',
    description: 'Moving Average Convergence Divergence',
    params: [
      { key: 'fast', label: 'Fast Period', type: 'number', min: 1, max: 50, default: 12 },
      { key: 'slow', label: 'Slow Period', type: 'number', min: 1, max: 100, default: 26 },
      { key: 'signal', label: 'Signal Period', type: 'number', min: 1, max: 50, default: 9 },
    ],
  },
  {
    id: 'BOLLINGER_BANDS',
    name: 'Bollinger Bands',
    description: 'Volatility Bands',
    params: [
      { key: 'period', label: 'Period', type: 'number', min: 1, max: 100, default: 20 },
      { key: 'devfactor', label: 'Deviation Factor', type: 'number', min: 0.1, max: 5, step: 0.1, default: 2.0 },
    ],
  },
  {
    id: 'VOLUME',
    name: 'Volume',
    description: 'Volume Indicator',
    params: [],
  },
]

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