import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import TechText from '../components/TechText.jsx'
import CrystalizedBall from '../components/CrystalizedBall.jsx'
import LogoMark from '../components/LogoMark.jsx'
import LiveAlgoChart from '../components/LiveAlgoChart.jsx'

const PIPELINE = [
  {
    n: '01',
    id: 'studio',
    title: 'Conversational Studio',
    body: 'Describe your thesis in plain English — the AI drafts testable strategy logic and shows its plan before anything runs.',
  },
  {
    n: '02',
    id: null,
    title: 'Live Simulation',
    body: 'Watch a simulated Nifty 50 feed with live BUY/SELL execution markers, Sharpe and P&L tracking.',
  },
  {
    n: '03',
    id: 'strategies',
    title: 'Secure Backtesting',
    body: 'Sandboxed backtests on real NIFTY 50 history with Sharpe, drawdown, win-rate and equity curves.',
  },
  {
    n: '04',
    id: null,
    title: 'Approval Gate',
    body: 'Every strategy passes a 4-stage quality gate plus an explicit human decision before deployment.',
  },
  {
    n: '05',
    id: null,
    title: 'Paper Trading',
    body: 'Deploy winners into simulated live trading — every fill tracked trade by trade, zero real capital.',
  },
  {
    n: '06',
    id: null,
    title: 'Open Methodology',
    body: 'Metrics, assumptions and limitations published openly — read the full docs anytime.',
  },
]

/**
 * Landing — public pre-login entry page (dark mode).
 *
 * Purely presentational: no API calls, no state. Served at /.
 */
export default function LandingPage() {
  const { hash } = useLocation()

  // Deep-link support for in-page anchors (e.g. /#features, /#process,
  // /#security). React Router does not scroll to hashes on its own, so
  // resolve the target element and smooth-scroll to it.
  useEffect(() => {
    if (!hash) return
    const targetId = hash.replace('#', '')
    document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [hash])

  // Landing-only viewport treatment: snap sections end to end and hide the
  // page scrollbar while this route is mounted. Cleaned up on unmount so
  // app pages are unaffected.
  useEffect(() => {
    document.documentElement.classList.add('lp-lock')
    document.body.classList.add('lp-lock')
    return () => {
      document.documentElement.classList.remove('lp-lock')
      document.body.classList.remove('lp-lock')
    }
  }, [])

  const scrollToSection = (id) => (event) => {
    event.preventDefault()
    // Suspend scroll-snap for the duration of this jump: proximity snap can
    // otherwise yank the landing position and leave a sliver of the previous
    // (white) section visible under the navbar.
    const root = document.documentElement
    root.style.scrollSnapType = 'none'
    window.clearTimeout(scrollToSection._snapTimer)
    const restoreSnap = () => {
      root.style.scrollSnapType = ''
    }
    // Exact landing: section top flush under the sticky navbar.
    const navbarHeight = document.querySelector('header')?.offsetHeight || 72
    const targetElement = document.getElementById(id)
    if (!targetElement) {
      restoreSnap()
      return
    }
    const targetPosition =
      targetElement.getBoundingClientRect().top + window.pageYOffset - navbarHeight
    window.scrollTo({ top: targetPosition, behavior: 'smooth' })
    window.history.replaceState(null, '', `#${id}`)
    scrollToSection._snapTimer = window.setTimeout(restoreSnap, 900)
  }

  const scrollToTop = (event) => {
    event.preventDefault()
    window.scrollTo({ top: 0, behavior: 'smooth' })
    window.history.replaceState(null, '', window.location.pathname)
  }

  return (
    <div className="lp" id="top">
      <a className="skip-link" href="#lp-main">
        Skip to content
      </a>

      <header className="lp__header">
        <div className="lp__header-inner">
          <a className="lp__brand" href="#top" onClick={scrollToTop} aria-label="QuantNiti home — back to top">
            <img
              className="lp__logo-mark"
              src="/svg/icon/icon-on-dark.svg"
              alt=""
              aria-hidden="true"
              width={32}
              height={32}
            />
            <span className="lp__brand-name" aria-hidden="true">
              <span className="lp__brand-quant">Quant</span>
              <span className="lp__brand-niti">Niti</span>
            </span>
          </a>
          <nav className="lp__nav" aria-label="Primary">
            <a className="lp__nav-link" href="#features" onClick={scrollToSection('features')}>
              Features
            </a>
            <a className="lp__nav-link" href="#process" onClick={scrollToSection('process')}>
              Process
            </a>
            <a className="lp__nav-link" href="#security" onClick={scrollToSection('security')}>
              Security
            </a>
          </nav>
          <Link className="lp__login" to="/login">
            Login
          </Link>
        </div>
      </header>

      <main className="lp__main" id="lp-main">
        <section className="lp__hero" aria-labelledby="lp-title">
          <div className="lp__brandmark" aria-hidden="false">
            <div className="lp__logo-tech lp__logo-tech--crystal">
              <div className="lp__crystal" aria-hidden="true">
                <CrystalizedBall
                  preset="plasma"
                  color="#ffb3ba"
                  size={1.1}
                  strands={4}
                  crackle={0.6}
                  flares={0.4}
                  glow={0.55}
                  sparks={0.35}
                  haze={0.5}
                  fill={0.5}
                  particleCount={9000}
                  interactive
                  hoverStrength={0.7}
                />
              </div>
              <LogoMark
                className="lp__brandmark-logo lp__brandmark-logo--in-crystal"
                width={96}
                height={96}
              />
            </div>
            <div className="lp__tech">
              <TechText
                text="QuantNiti"
                fontFamily="'Plus Jakarta Sans', 'Space Grotesk', sans-serif"
                fontWeight={800}
                fontSize={110}
                reveal="letter"
                dashLength={4}
                dashGap={2}
                specks={15}
                color="#ffffff"
                highlight="Niti"
                highlightColor="#ffb3ba"
                accentColor="#ffb3ba"
              />
            </div>
          </div>
          <h1 className="lp__headline" id="lp-title">
            <span className="lp__ai">AI</span> Quant Strategy Assistant
          </h1>
          <p className="lp__sub">
            Turn your ideas into data-driven trading strategies with the power of AI. Backtest.
            Analyse. Trade (Paper).
          </p>
        </section>

        <section className="lp__live" id="live-demo" aria-label="Live algorithmic trading demo">
          <div className="lp__section-head" aria-hidden="true">
            <span className="lp__section-label">Live simulation</span>
            <span className="lp__section-rule" />
          </div>
          <LiveAlgoChart />
        </section>
      </main>

      <section className="lp__sheet lp__sheet--light" id="features" aria-label="How it works">
        <div className="lp__sheet-inner">
          <p className="lp__eyebrow lp__eyebrow--dark">Features</p>
          <h2 className="lp__sheet-title">From concept to execution in minutes.</h2>
          <ol className="lp__steps">
            {PIPELINE.map((step) => (
              <li
                key={step.n}
                className="lp__step"
                {...(step.id ? { id: step.id } : {})}
              >
                <span className="lp__step-num" aria-hidden="true">
                  {step.n}
                </span>
                <h3 className="lp__step-title">{step.title}</h3>
                <p className="lp__step-body">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="lp__process" id="process" aria-label="How a strategy is created">
        <div className="lp__process-inner">
          <p className="lp__eyebrow">From idea to paper trade</p>
          <h2 className="lp__sheet-title lp__sheet-title--light">How your strategy comes to life.</h2>
          <p className="lp__process-lede">
            No code, no spreadsheets — describe your thesis and watch it become a tested,
            paper-traded strategy.
          </p>
          <svg
            className="lp__flow"
            viewBox="0 0 880 210"
            role="img"
            aria-label="Strategy creation flow: describe, draft, validate, deploy"
          >
            {/* connectors */}
            <g className="lp__flow-track" aria-hidden="true">
              <line x1="140" y1="88" x2="252" y2="88" />
              <polygon points="252,80 268,88 252,96" />
              <line x1="380" y1="88" x2="492" y2="88" />
              <polygon points="492,80 508,88 492,96" />
              <line x1="620" y1="88" x2="732" y2="88" />
              <polygon points="732,80 748,88 732,96" />
            </g>
            {/* node 1 — describe */}
            <g>
              <circle cx="86" cy="88" r="54" className="lp__flow-node" />
              <rect x="62" y="70" width="48" height="28" rx="9" className="lp__flow-icon" />
              <polygon points="74,98 70,110 86,98" className="lp__flow-icon" />
              <line x1="70" y1="79" x2="102" y2="79" className="lp__flow-line" />
              <line x1="70" y1="88" x2="94" y2="88" className="lp__flow-line" />
              <text x="86" y="176" className="lp__flow-num">1</text>
            </g>
            {/* node 2 — draft */}
            <g>
              <circle cx="326" cy="88" r="54" className="lp__flow-node" />
              <path
                d="M326 62c1.6 8 4.4 10.8 12.4 12.4-8 1.6-10.8 4.4-12.4 12.4-1.6-8-4.4-10.8-12.4-12.4 8-1.6 10.8-4.4 12.4-12.4z"
                className="lp__flow-accent"
              />
              <path
                d="M352 78c1 5 2.8 6.8 7.8 7.8-5 1-6.8 2.8-7.8 7.8-1-5-2.8-6.8-7.8-7.8 5-1 6.8-2.8 7.8-7.8z"
                className="lp__flow-accent"
              />
              <path
                d="M300 96c0.8 4 2.2 5.4 6.2 6.2-4 0.8-5.4 2.2-6.2 6.2-0.8-4-2.2-5.4-6.2-6.2 4-0.8 5.4-2.2 6.2-6.2z"
                className="lp__flow-accent"
              />
              <text x="326" y="176" className="lp__flow-num">2</text>
            </g>
            {/* node 3 — validate */}
            <g>
              <circle cx="566" cy="88" r="54" className="lp__flow-node" />
              <line x1="536" y1="112" x2="596" y2="112" className="lp__flow-line" />
              <line x1="536" y1="112" x2="536" y2="64" className="lp__flow-line" />
              <polyline
                points="542,104 556,96 566,100 590,72"
                className="lp__flow-icon"
              />
              <circle cx="590" cy="72" r="6" className="lp__flow-dot" />
              <text x="566" y="176" className="lp__flow-num">3</text>
            </g>
            {/* node 4 — deploy */}
            <g>
              <circle cx="806" cy="88" r="54" className="lp__flow-node" />
              <path
                d="M806 62l20 8v12c0 13-8.6 22.4-20 27-11.4-4.6-20-14-20-27v-12z"
                className="lp__flow-icon"
              />
              <polyline points="798,88 804,94 815,82" className="lp__flow-check" />
              <text x="806" y="176" className="lp__flow-num">4</text>
            </g>
          </svg>
          <ol className="lp__flow-steps">
            <li className="lp__flow-step">
              <h3>Describe</h3>
              <p>Tell the Studio your market thesis in plain words — direction, style and triggers.</p>
            </li>
            <li className="lp__flow-step">
              <h3>Draft</h3>
              <p>The AI turns your thesis into a testable strategy and shows its plan up front.</p>
            </li>
            <li className="lp__flow-step">
              <h3>Validate</h3>
              <p>We replay it over years of Nifty 50 history and grade it on Sharpe and drawdown.</p>
            </li>
            <li className="lp__flow-step">
              <h3>Deploy</h3>
              <p>Winners pass your approval into paper trading, tracked trade by trade.</p>
            </li>
          </ol>
        </div>
      </section>

      <section className="lp__sheet lp__sheet--dark" id="security" aria-label="Trust and security">
        <div className="lp__sheet-inner">
          <p className="lp__eyebrow">Built for learning &amp; security</p>
          <h2 className="lp__sheet-title lp__sheet-title--light">
            Enterprise-grade analytics. Zero financial risk.
          </h2>
          <p className="lp__sheet-lede">
            The analytics are real — the money never is. Everything runs on historical data
            and simulated books.
          </p>
          <dl className="lp__stats">
            <div className="lp__stat">
              <dd>0</dd>
              <dt>real-money orders</dt>
            </div>
            <div className="lp__stat">
              <dd>2 yrs</dd>
              <dt>Nifty 50 history</dt>
            </div>
            <div className="lp__stat">
              <dd>4-stage</dd>
              <dt>approval gate</dt>
            </div>
          </dl>
          <div className="lp__bento">
            <article className="lp__bento-card lp__bento-card--wide">
              <p className="lp__bento-tag">Educational Prototype</p>
              <h3 className="lp__bento-title">Learn strategy design in a deterministic sandbox</h3>
              <p className="lp__bento-body">
                Paper-trading bookkeeping on historical NIFTY 50 data. No orders, no broker
                gateway, no surprises — every metric is computed in the open.
              </p>
            </article>
            <article className="lp__bento-card">
              <p className="lp__bento-tag">No Real Capital at Risk</p>
              <h3 className="lp__bento-title">Simulated deployment only</h3>
              <p className="lp__bento-body">
                Winning strategies graduate through an approval gate into paper trading. Real
                money is never touched.
              </p>
            </article>
            <article className="lp__bento-card">
              <p className="lp__bento-tag">Transparent Mechanics</p>
              <h3 className="lp__bento-title">Every number shows its limits</h3>
              <p className="lp__bento-body">
                Sharpe, drawdown and profit factor come with their caveats — overfitting,
                lookahead bias and slippage are stated, not hidden.
              </p>
            </article>
          </div>
          <Link className="lp__ghost" to="/docs">
            Read the Docs
          </Link>
          <footer className="lp__footer">
            <span>© 2026 QuantNiti</span>
            <span aria-hidden="true">·</span>
            <span>+918237517479</span>
            <span aria-hidden="true">·</span>
            <a
              className="lp__footer-link"
              href="https://github.com/AyoAyoos/Ai_Quant"
              target="_blank"
              rel="noreferrer"
            >
              GitHub Repository
            </a>
            <span aria-hidden="true">·</span>
            <span>Educational prototype only. No guaranteed returns.</span>
          </footer>
        </div>
      </section>
    </div>
  )
}
