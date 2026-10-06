const STYLES = [
  { id: 'scalping', name: 'Scalping', icon: '⚡', description: 'Fast trades, seconds to minutes' },
  { id: 'intraday', name: 'Intraday', icon: '📊', description: 'Same-day trades, hours' },
  { id: 'swing', name: 'Swing', icon: '📈', description: 'Multi-day positions, days to weeks' },
  { id: 'positional', name: 'Positional', icon: '🕐', description: 'Longer term, weeks to months' },
]

export default function TradingStyleSection({ value, onChange, error }) {
  return (
    <section className="strategy-section" aria-labelledby="trading-style-heading">
      <div className="strategy-section__head">
        <h2 id="trading-style-heading" className="strategy-section__title">What type of strategy do you want?</h2>
      </div>

      <div className="style-grid" role="radiogroup" aria-label="Select trading style">
        {STYLES.map((style) => (
          <button
            key={style.id}
            type="button"
            role="radio"
            aria-checked={value === style.id}
            aria-label={style.name}
            className={`style-card${value === style.id ? ' style-card--selected' : ''}`}
            onClick={() => onChange(style.id)}
          >
            <span className="style-card__icon" aria-hidden="true">{style.icon}</span>
            <span className="style-card__name">{style.name}</span>
            <span className="style-card__desc">{style.description}</span>
          </button>
        ))}
      </div>

      {error && <p className="field__error" role="alert">{error}</p>}
    </section>
  )
}