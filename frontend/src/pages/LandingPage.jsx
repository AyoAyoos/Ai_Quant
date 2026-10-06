import { Link } from 'react-router-dom'
import Icon from '../components/Icon.jsx'

const FEATURES = [
  {
    icon: 'auto_awesome',
    title: 'AI Strategy Creation',
    body: 'Describe your idea in natural language and get AI-powered trading strategies with ready-to-run code.',
  },
  {
    icon: 'code',
    title: 'Backtesting',
    body: 'Test your strategies on historical data with robust analysis and performance metrics.',
  },
  {
    icon: 'bar_chart',
    title: 'Analytics',
    body: 'Visualize results, track key metrics and gain insights to improve your strategies.',
  },
  {
    icon: 'shield',
    title: 'Paper Trading',
    body: 'Practice and refine your strategies in a risk-free environment.',
  },
  {
    icon: 'database',
    title: 'Real Market Data',
    body: 'Powered by reliable market data (e.g., NIFTY 50) for accurate backtesting and analysis.',
  },
  {
    icon: 'smart_toy',
    title: 'Powered by LLMs',
    body: 'Built with advanced AI models for smarter, contextual strategy generation.',
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
        <span className="lp__brand">
          <span className="lp__mark" aria-hidden="true">
            <Icon name="ssid_chart" size={20} />
          </span>
          <span className="lp__name">Quant Strategy Assistant</span>
        </span>
        <Link className="lp__login" to="/login">
          Login
        </Link>
      </header>

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

        <section className="lp__grid" aria-label="Platform features">
          {FEATURES.map((feature) => (
            <article key={feature.title} className="lp__card">
              <span className="lp__icon" aria-hidden="true">
                <Icon name={feature.icon} size={22} />
              </span>
              <h2 className="lp__card-title">{feature.title}</h2>
              <p className="lp__card-body">{feature.body}</p>
            </article>
          ))}
        </section>
      </main>

      <footer className="lp__footer">
        <Icon name="shield" size={15} />
        <span>Educational prototype. Paper trading only. No guaranteed returns.</span>
      </footer>
    </div>
  )
}
