import { Activity, Check, Landmark, SlidersHorizontal, TrendingUp } from 'lucide-react'

const MARKETS = [
  { id: 'NIFTY50', name: 'NIFTY 50', description: 'Benchmark Index', default: true, Icon: TrendingUp },
  { id: 'BANKNIFTY', name: 'BANK NIFTY', description: 'Banking Index', Icon: Landmark },
  { id: 'SENSEX', name: 'SENSEX', description: 'BSE Benchmark', Icon: Activity },
  { id: 'OTHER', name: 'OTHER', description: 'Custom Market', Icon: SlidersHorizontal },
]

export default function MarketSection({ value, onChange, error }) {
  return (
    <section className="strategy-section" aria-labelledby="market-heading">
      <div className="strategy-section__head">
        <h2 id="market-heading" className="strategy-section__title">What do you want to trade?</h2>
      </div>

      <div className="market-grid" role="radiogroup" aria-label="Select market">
        {MARKETS.map((market) => {
          const selected = value === market.id
          const Icon = market.Icon
          return (
            <button
              key={market.id}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={market.name}
              className={`market-card${selected ? ' market-card--selected' : ''}`}
              onClick={() => onChange(market.id)}
            >
              {market.default && <span className="market-card__badge">Default</span>}
              {selected && (
                <span className="card-check" aria-hidden="true">
                  <Check size={13} strokeWidth={3} />
                </span>
              )}
              <span className="card-icon" aria-hidden="true">
                <Icon size={24} />
              </span>
              <span className="market-card__name">{market.name}</span>
              <span className="market-card__desc">{market.description}</span>
            </button>
          )
        })}
      </div>

      {error && <p className="field__error" role="alert">{error}</p>}
    </section>
  )
}