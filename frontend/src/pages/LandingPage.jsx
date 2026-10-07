import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import Icon from '../components/Icon.jsx'
import DocumentationContent from '../components/DocumentationContent.jsx'

const FEATURES = [
  {
    id: 'studio',
    icon: 'smart_toy',
    title: 'Conversational Strategy Studio',
    body: 'Leverage advanced LLMs to transform your trading ideas into ready-to-run Python code through a multi-phase interactive chat interface.',
  },
  {
    id: 'strategies',
    icon: 'bar_chart',
    title: 'Secure Backtesting & Analytics',
    body: 'Safely evaluate generated strategies against real NIFTY 50 historical data in an isolated sandbox, complete with deep performance metrics, risk analysis, and equity curve visualization.',
  },
  {
    id: null,
    icon: 'shield',
    title: 'Risk-Free Paper Trading',
    body: 'Progress your strategies through a strict data-driven approval lifecycle. Deploy and monitor paper trades in a simulated environment without risking real capital.',
  },
]

/**
 * Landing — public pre-login entry page (dark mode).
 *
 * Purely presentational: no API calls, no state. Served at /.
 */
export default function LandingPage() {
  const { hash } = useLocation()

  // Deep-link support for in-page anchors (e.g. /#features, /#studio, /#strategies,
  // /#documentation). React Router does not scroll to hashes on its own, so
  // resolve the target element and smooth-scroll to it.
  useEffect(() => {
    if (!hash) return
    const targetId = hash.replace('#', '')
    document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [hash])

  const scrollToSection = (id) => (event) => {
    event.preventDefault()
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    window.history.replaceState(null, '', `#${id}`)
  }

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
          <a className="lp__nav-link" href="#features" onClick={scrollToSection('features')}>
            Features
          </a>
          <a className="lp__nav-link" href="#studio" onClick={scrollToSection('studio')}>
            Studio
          </a>
          <a className="lp__nav-link" href="#strategies" onClick={scrollToSection('strategies')}>
            Strategies
          </a>
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
        </section>

        <section className="lp__features" id="features" aria-label="Platform features">
          <div className="lp__section-head" aria-hidden="true">
            <span className="lp__section-label">Core capabilities</span>
            <span className="lp__section-rule" />
            <span className="lp__section-count">03</span>
          </div>
          <div className="lp__grid">
            {FEATURES.map((feature) => (
              <article
                key={feature.title}
                className="lp__card"
                {...(feature.id ? { id: feature.id } : {})}
              >
                <span className="lp__icon" aria-hidden="true">
                  <Icon name={feature.icon} size={22} />
                </span>
                <h2 className="lp__card-title">{feature.title}</h2>
                <p className="lp__card-body">{feature.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="lp__docs" id="documentation" aria-label="Documentation">
          <div className="lp__section-head" aria-hidden="true">
            <span className="lp__section-label">Documentation</span>
            <span className="lp__section-rule" />
          </div>
          <div className="lp__docs-body">
            <DocumentationContent isLandingSubset={true} />
          </div>
        </section>
      </main>

      <footer className="lp__footer">
        <div className="lp__footer-grid">
          <div className="lp__footer-col">
            <span className="lp__footer-brand" aria-label="AI Quant home">
              <img className="lp__logo" src="/favicon.svg" alt="" width={30} height={30} />
              <span className="lp__name">AI Quant</span>
            </span>
            <p className="lp__footer-text">© 2026 AI Quant. All rights reserved.</p>
          </div>
          <div className="lp__footer-col">
            <h2 className="lp__footer-heading">Support</h2>
            <p className="lp__footer-text">For queries or help: +918237517479</p>
          </div>
          <div className="lp__footer-col">
            <h2 className="lp__footer-heading">Open Source</h2>
            <a
              className="lp__footer-link"
              href="https://github.com/AyoAyoos/Ai_Quant"
              target="_blank"
              rel="noreferrer"
            >
              <Icon name="code" size={16} />
              <span>GitHub Repository</span>
            </a>
          </div>
        </div>
        <div className="lp__footer-note">
          <Icon name="shield" size={15} />
          <span>Educational prototype, Paper trading only. No guaranteed returns.</span>
        </div>
      </footer>
    </div>
  )
}
