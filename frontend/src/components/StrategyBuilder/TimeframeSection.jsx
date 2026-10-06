import { useMemo } from 'react'

const TIMEFRAMES = [
  { id: '5m', label: '5 Minutes', value: '5m' },
  { id: '15m', label: '15 Minutes', value: '15m' },
  { id: '30m', label: '30 Minutes', value: '30m' },
  { id: '1h', label: '1 Hour', value: '1h' },
  { id: '1d', label: '1 Day', value: '1d' },
]

const STYLE_TIMEFRAME_COMPATIBILITY = {
  scalping: ['5m', '15m'],
  intraday: ['5m', '15m', '30m', '1h'],
  swing: ['1h', '1d'],
  positional: ['1d'],
}

export default function TimeframeSection({ value, onChange, tradingStyle, error }) {
  const compatibleTimeframes = useMemo(
    () => TIMEFRAMES.filter((tf) => STYLE_TIMEFRAME_COMPATIBILITY[tradingStyle]?.includes(tf.value)),
    [tradingStyle]
  )

  const isCompatible = compatibleTimeframes.some((tf) => tf.value === value)

  return (
    <section className="strategy-section" aria-labelledby="timeframe-heading">
      <div className="strategy-section__head">
        <h2 id="timeframe-heading" className="strategy-section__title">Which timeframe should the strategy use?</h2>
        {tradingStyle && (
          <p className="strategy-section__hint">
            Compatible with {tradingStyle}: {compatibleTimeframes.map((tf) => tf.label).join(', ')}
          </p>
        )}
      </div>

      <div className="timeframe-chips" role="radiogroup" aria-label="Select timeframe">
        {TIMEFRAMES.map((tf) => {
          const compatible = STYLE_TIMEFRAME_COMPATIBILITY[tradingStyle]?.includes(tf.value)
          return (
            <button
              key={tf.id}
              type="button"
              role="radio"
              aria-checked={value === tf.value}
              aria-disabled={!compatible}
              aria-label={tf.label}
              className={`timeframe-chip${value === tf.value ? ' timeframe-chip--selected' : ''}${!compatible ? ' timeframe-chip--incompatible' : ''}`}
              onClick={() => compatible && onChange(tf.value)}
              disabled={!compatible}
            >
              {tf.label}
            </button>
          )
        })}
      </div>

      {error && <p className="field__error" role="alert">{error}</p>}
      {!isCompatible && value && tradingStyle && (
        <p className="field__error" role="alert">
          {value} is not compatible with {tradingStyle}. Please select a compatible timeframe.
        </p>
      )}
    </section>
  )
}