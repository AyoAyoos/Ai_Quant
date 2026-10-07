import { Link } from 'react-router-dom'
import Icon from '../components/Icon.jsx'

const FEATURES = [
  {
    icon: 'smart_toy',
    title: 'Conversational Strategy Studio',
    body: 'Leverage advanced LLMs to transform your trading ideas into ready-to-run Python code through a multi-phase interactive chat interface.',
  },
  {
    icon: 'bar_chart',
    title: 'Secure Backtesting & Analytics',
    body: 'Safely evaluate generated strategies against real NIFTY 50 historical data in an isolated sandbox, complete with deep performance metrics, risk analysis, and equity curve visualization.',
  },
  {
    icon: 'shield',
    title: 'Risk-Free Paper Trading',
    body: 'Progress your strategies through a strict data-driven approval lifecycle. Deploy and monitor paper trades in a simulated environment without risking real capital.',
  },
]

/**
 * Landing — public pre-login entry page (dark mode).
 *
 * Purely presentational: no API calls, no state. Served at /welcome.
 */
export default function LandingPage() {
  return (
    <div className="lp">
      <a className="skip-link" href="#lp-main">
        Skip to content
      </a>

      <header className="lp__header">
        <span className="lp__brand" aria-label="AI Quant home">
          <img className="lp__logo" src="/favicon.svg" alt="" width={34} height={34} />
          <span className="lp__name">AI Quant</span>
        </span>
        <nav className="lp__nav" aria-label="Primary">
          <a className="lp__nav-link" href="#lp-features">
            Features
          </a>
          <Link className="lp__nav-link" to="/studio">
            Studio
          </Link>
          <Link className="lp__nav-link" to="/strategies">
            Strategies
          </Link>
        </nav>
        <Link className="lp__login" to="/login">
          Login
        </Link>
      </header>
      <div className="lp__rule" aria-hidden="true" />

      <main className="lp__main" id="lp-main">
        <section className="lp__hero" aria-labelledby="lp-title">
          <h1 className="lp__headline" id="lp-title">
            <span className="lp__ai">AI</span> Quant Strategy Assistant
          </h1>
          <p className="lp__sub">
            Turn your ideas into data-driven trading strategies with the power of AI. Backtest.
            Analyse. Trade (Paper).
          </p>
          <div className="lp__cta">
            <Link className="lp__btn lp__btn--solid" to="/studio">
              Try Strategy Studio
              <Icon name="arrow_forward" size={18} />
            </Link>
            <Link className="lp__btn lp__btn--hollow" to="/strategies">
              View Strategies
            </Link>
          </div>
        </section>

        <section className="lp__features" id="lp-features" aria-label="Platform features">
          <div className="lp__section-head" aria-hidden="true">
            <span className="lp__section-label">Core capabilities</span>
            <span className="lp__section-rule" />
            <span className="lp__section-count">03</span>
          </div>
          <div className="lp__grid">
            {FEATURES.map((feature) => (
              <article key={feature.title} className="lp__card">
                <span className="lp__icon" aria-hidden="true">
                  <Icon name={feature.icon} size={22} />
                </span>
                <h2 className="lp__card-title">{feature.title}</h2>
                <p className="lp__card-body">{feature.body}</p>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="lp__footer">
        <Icon name="shield" size={15} />
        <span>Educational prototype, Paper trading only. No guaranteed returns.</span>
      </footer>
    </div>
  )
}
