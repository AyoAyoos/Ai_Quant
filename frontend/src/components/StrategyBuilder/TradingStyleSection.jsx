import { BarChart2, Check, Clock, LineChart, Zap } from 'lucide-react'

const STYLES = [
  { id: 'scalping', name: 'Scalping', Icon: Zap, description: 'Fast trades, seconds to minutes' },
  { id: 'intraday', name: 'Intraday', Icon: BarChart2, description: 'Same-day trades, hours' },
  { id: 'swing', name: 'Swing', Icon: LineChart, description: 'Multi-day positions, days to weeks' },
  { id: 'positional', name: 'Positional', Icon: Clock, description: 'Longer term, weeks to months' },
]

export default function TradingStyleSection({ value, onChange, error }) {
  return (
    <section className="strategy-section" aria-labelledby="trading-style-heading">
      <div className="strategy-section__head">
        <h2 id="trading-style-heading" className="strategy-section__title">What type of strategy do you want?</h2>
      </div>

      <div className="style-grid" role="radiogroup" aria-label="Select trading style">
        {STYLES.map((style) => {
          const selected = value === style.id
          const Icon = style.Icon
          return (
            <button
              key={style.id}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={style.name}
              className={`style-card${selected ? ' style-card--selected' : ''}`}
              onClick={() => onChange(style.id)}
            >
              {selected && (
                <span className="card-check" aria-hidden="true">
                  <Check size={13} strokeWidth={3} />
                </span>
              )}
              <span className="card-icon" aria-hidden="true">
                <Icon size={24} />
              </span>
              <span className="style-card__name">{style.name}</span>
              <span className="style-card__desc">{style.description}</span>
            </button>
          )
        })}
      </div>

      {error && <p className="field__error" role="alert">{error}</p>}
    </section>
  )
}