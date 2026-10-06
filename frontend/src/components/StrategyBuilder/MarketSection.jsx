const MARKETS = [
  { id: 'NIFTY50', name: 'NIFTY 50', description: 'Benchmark Index', default: true },
  { id: 'BANKNIFTY', name: 'BANK NIFTY', description: 'Banking Index' },
  { id: 'SENSEX', name: 'SENSEX', description: 'BSE Benchmark' },
  { id: 'OTHER', name: 'OTHER', description: 'Custom Market' },
]

export default function MarketSection({ value, onChange, error }) {
  return (
    <section className="strategy-section" aria-labelledby="market-heading">
      <div className="strategy-section__head">
        <h2 id="market-heading" className="strategy-section__title">What do you want to trade?</h2>
      </div>

      <div className="market-grid" role="radiogroup" aria-label="Select market">
        {MARKETS.map((market) => (
          <button
            key={market.id}
            type="button"
            role="radio"
            aria-checked={value === market.id}
            aria-label={market.name}
            className={`market-card${value === market.id ? ' market-card--selected' : ''}`}
            onClick={() => onChange(market.id)}
          >
            <span className="market-card__name">{market.name}</span>
            <span className="market-card__desc">{market.description}</span>
            {market.default && <span className="market-card__badge">Default</span>}
          </button>
        ))}
      </div>

      {error && <p className="field__error" role="alert">{error}</p>}
    </section>
  )
}