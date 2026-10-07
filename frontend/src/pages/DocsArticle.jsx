import { Link } from 'react-router-dom'
import Icon from '../components/Icon.jsx'
import DocumentationContent from '../components/DocumentationContent.jsx'

/**
 * Documentation — preserves the existing landing-page content verbatim.
 *
 * PAGE SPLIT ONLY: the "HOW IT WORKS / SYSTEM PIPELINE / CAPABILITIES /
 * THREAT MITIGATION / CORE INFRASTRUCTURE / DEVELOPER SETUP / SCOPE & INTENT /
 * TECH STACK" sections live in DocumentationContent.jsx (shared with the
 * landing page embed); this wrapper only adds the subnav, hero, ribbon and
 * footer chrome around them. No text, number or workflow is edited here.
 */

const SUBNAV = [
  { href: '#how-it-works', label: 'How It Works' },
  { href: '#features', label: 'Features' },
  { href: '#metrics', label: 'Metrics' },
  { href: '#security', label: 'Security Sandbox' },
  { href: '#tech-stack', label: 'Tech Stack' },
  { href: '#quickstart', label: 'Quickstart' },
  { href: '#limitations', label: 'Scope & Limits' },
]

export default function DocsArticle() {
  return (
    <div className="landing">
      {/* ------------------------------------------------ sticky sub-nav */}
      <div className="landing__subnav">
        <div className="landing__subnav-inner no-scrollbar">
          <nav className="landing__subnav-links" aria-label="On this page">
            {SUBNAV.map((item, index) => (
              <a
                key={item.href}
                href={item.href}
                className={`landing__subnav-link${index === 0 ? ' landing__subnav-link--lead' : ''}`}
              >
                {item.label}
              </a>
            ))}
          </nav>
          <span className="landing__subnav-status">
            <span className="landing__pulse" aria-hidden="true" />
            Educational build · paper only
          </span>
        </div>
      </div>

      <div className="landing__container">
        {/* ------------------------------------------------------- hero */}
        <section className="landing__saas-hero">
          <div className="landing__saas-copy">
            <h1 className="landing__saas-headline">
              Next-Gen <span className="landing__saas-accent">AI Quant</span> Strategy Assistant
            </h1>

            <p className="landing__saas-lede">
              Describe a strategy in plain English and let AI generate runnable Backtrader code,
              backtest it on two years of real NIFTY 50 data, and promote winners through a human
              approval gate into paper trading.
            </p>

            <div className="landing__saas-cta">
              <Link className="landing__saas-btn landing__saas-btn--primary" to="/studio">
                Get Started Free
              </Link>
              <a className="landing__saas-btn landing__saas-btn--outline" href="#metrics">
                View Demo
              </a>
            </div>
          </div>

          <div
            className="landing__saas-preview"
            role="img"
            aria-label="Illustrative preview of an AI strategy prompt and its cumulative-returns chart"
          >
            <div className="landing__prompt">
              <span className="landing__prompt-label">AI Studio prompt</span>
              <p className="landing__prompt-text">
                &ldquo;Create a mean-reversion strategy for NIFTY 50 using RSI-14 below 30 with
                50-EMA trend confirmation&hellip;&rdquo;
              </p>
              <span className="landing__prompt-status">
                <Icon name="bolt" size={14} />
                Drafting bt.Strategy&hellip;
              </span>
            </div>
            <div className="landing__returns">
              <span className="landing__returns-label">Cumulative returns &middot; illustrative</span>
              <svg
                className="landing__returns-svg"
                viewBox="0 0 400 140"
                preserveAspectRatio="none"
                aria-hidden="true"
                focusable="false"
              >
                <defs>
                  <linearGradient id="saas-line" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0" stopColor="#F8B2B2" />
                    <stop offset="1" stopColor="#8B639B" />
                  </linearGradient>
                  <linearGradient id="saas-area" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#8B639B" stopOpacity="0.28" />
                    <stop offset="1" stopColor="#8B639B" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <line x1="0" x2="400" y1="35" y2="35" stroke="#403D88" strokeOpacity="0.1" />
                <line x1="0" x2="400" y1="70" y2="70" stroke="#403D88" strokeOpacity="0.1" />
                <line x1="0" x2="400" y1="105" y2="105" stroke="#403D88" strokeOpacity="0.1" />
                <path
                  d="M0,118 C40,112 60,96 90,92 S140,78 170,70 S230,60 260,48 S330,34 360,26 L400,18 L400,140 L0,140 Z"
                  fill="url(#saas-area)"
                />
                <path
                  d="M0,118 C40,112 60,96 90,92 S140,78 170,70 S230,60 260,48 S330,34 360,26 L400,18"
                  fill="none"
                  stroke="url(#saas-line)"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
                <circle cx="400" cy="18" r="5" fill="#8B639B" />
                <circle cx="400" cy="18" r="9" fill="none" stroke="#8B639B" strokeOpacity="0.35" />
              </svg>
            </div>
          </div>
        </section>

        <DocumentationContent />

        {/* ------------------------------------------------ closing ribbon */}
        <section className="landing__ribbon">
          <div className="landing__ribbon-text">
            <h2 className="landing__ribbon-title">Ready to test your first algorithmic thesis?</h2>
            <p className="landing__ribbon-body">
              Clone the repo, drop in a Groq key, and start describing strategies in plain English. The
              assistant will ask you for everything it needs before it writes a line of code.
            </p>
          </div>
          <div className="landing__ribbon-actions">
            <a className="landing__btn landing__btn--primary" href="#quickstart">
              <Icon name="terminal" size={18} />
              Start local engine
            </a>
            <Link className="landing__btn landing__btn--tonal" to="/chat">
              Open web chat
            </Link>
          </div>
        </section>
      </div>

      {/* ------------------------------------------------------- footer */}
      <footer className="landing__footer">
        <div className="landing__footer-inner">
          <div className="landing__footer-brand">
            <Icon name="ssid_chart" size={20} />
            <span>Quant Strategy Assistant</span>
          </div>
          <nav className="landing__footer-links" aria-label="Footer">
            <a href="#security">Compliance &amp; security</a>
            <a href="#quickstart">Documentation</a>
            <a href="#metrics">Metrics reference</a>
            <Link to="/strategies">Strategy library</Link>
          </nav>
          <p className="landing__footer-legal">
            Educational prototype. Paper trading only. No live orders, no investment advice, no guaranteed
            returns.
          </p>
        </div>
      </footer>
    </div>
  )
}
