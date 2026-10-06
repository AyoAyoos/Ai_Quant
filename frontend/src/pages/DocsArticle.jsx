import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/Icon.jsx'
import CopyButton from '../components/CopyButton.jsx'
import {
  SAMPLE_BENCHMARK,
  SAMPLE_DATES,
  SAMPLE_EQUITY,
  SAMPLE_METRICS,
  SAMPLE_STRATEGY,
  SAMPLE_TRADES,
} from '../lib/sampleResults.js'

/* ------------------------------------------------------------------ content */

const SUBNAV = [
  { href: '#how-it-works', label: 'How It Works' },
  { href: '#features', label: 'Features' },
  { href: '#metrics', label: 'Metrics' },
  { href: '#security', label: 'Security Sandbox' },
  { href: '#tech-stack', label: 'Tech Stack' },
  { href: '#quickstart', label: 'Quickstart' },
  { href: '#limitations', label: 'Scope & Limits' },
]

const PIPELINE = [
  {
    icon: 'schema',
    title: 'Schema Codegen',
    body: 'The assistant chats freely until the rules are concrete, then a second, narrow LLM call returns {name, description, code} against a strict JSON schema. If that call fails, a regex parser recovers the class and strips the plotting and CSV boilerplate.',
    foot: ['Output', 'Backtrader AST'],
  },
  {
    icon: 'security',
    title: 'AST & Isolation',
    body: 'An AST walk refuses any import outside backtrader, pandas, numpy, math and datetime, and refuses the escape hatches (__import__, eval, exec, open, __globals__, getattr). Static refusal happens before a single line runs.',
    foot: ['Constraint', '1 GB / 120 s watchdog'],
  },
  {
    icon: 'timeline',
    title: 'NIFTY 50 Simulation',
    body: 'The strategy runs in its own subprocess over daily OHLCV bars, with your cash, commission and position-size settings applied. Sharpe, Sortino, CAGR, drawdown and a per-trade table come back in one response.',
    foot: ['Dataset', '740 daily bars'],
  },
  {
    icon: 'rule',
    title: 'Approval Gate',
    body: 'Nothing is deployed on the model’s say-so. You read the metrics and explicitly approve or reject — a rejection needs a written reason, and every transition is recorded in a newest-first audit trail.',
    foot: ['Outcome', 'Paper trading or rejected'],
  },
]

const FEATURES = [
  {
    icon: 'chat_bubble',
    title: 'Conversational Strategy Design',
    body: 'Describe an alpha hypothesis in plain financial English. The assistant asks for the timeframe, thresholds, exit rule and position size it is missing instead of guessing, then writes a real bt.Strategy class with the indicators wired up.',
    foot: ['Target', 'Backtrader 1.9.78'],
  },
  {
    icon: 'schema',
    title: 'Schema-Constrained Codegen',
    body: 'Structure comes from a json_schema-constrained call plus a regex fallback, not from asking a model nicely in the prompt. Machine markers and code fences are stripped from the reply you read, while the raw turn is kept in history.',
    foot: ['Enforcement', 'Pydantic v2 contracts'],
  },
  {
    icon: 'database',
    title: 'One-Click NIFTY 50 Ingestion',
    body: 'Two years of daily ^NSEI bars download from Yahoo Finance on first run and cache to a local CSV. If Yahoo rate-limits, backtests reuse the stale cache instead of failing — you see older start dates rather than an error.',
    foot: ['Cache', 'Local CSV store'],
  },
  {
    icon: 'calculate',
    title: 'Full Quantitative Metric Suite',
    body: 'CAGR, Sharpe, Sortino from downside deviation, max drawdown, win rate, profit factor and a buy & hold comparison. CAGR and Sortino are computed here rather than read off an analyzer, because the bundled backtrader ships neither correctly.',
    foot: ['Math', 'pandas / numpy'],
  },
  {
    icon: 'lock',
    title: 'Sandboxed Python Subprocess',
    body: 'Generated code never executes in the API process. It is piped over stdin to a separate interpreter with a 120-second wall clock, a process-tree kill on expiry, a 256 KB output ceiling and a 1 GB address-space cap on POSIX.',
    foot: ['Isolation', 'Subprocess + RLIMIT_AS'],
  },
  {
    icon: 'verified',
    title: 'Human Gate & Audit Trail',
    body: 'Approval requires a stored backtest, a minimum trade count and a drawdown ceiling — a quality gate, not a profitability filter. Rejections and stops carry a written reason, and deployments are listed newest-first.',
    foot: ['Persistence', 'PostgreSQL 16'],
  },
]

const QUICK = [
  {
    icon: 'forum',
    title: 'AI Studio',
    body: 'Chat a plain-English idea into runnable Backtrader code.',
    to: '/studio',
  },
  {
    icon: 'timeline',
    title: 'Backtest Engine',
    body: 'Sandboxed runs over two years of NIFTY 50 bars.',
    to: '/backtests',
  },
  {
    icon: 'calculate',
    title: 'Risk Analytics',
    body: 'Sharpe, drawdown and win-rate reads on cached runs.',
    to: '/analytics',
  },
  {
    icon: 'verified',
    title: 'Paper Deployments',
    body: 'Gate winning strategies into paper trading.',
    to: '/paper-trading',
  },
]

const THREATS = [
  {
    risk: 'critical',
    threat: 'Arbitrary code execution',
    mitigation:
      'An AST allowlist inspects the syntax tree before execution. Imports outside backtrader / pandas / numpy / math / datetime are refused, as are __import__, eval, exec, open, compile, getattr, setattr and dunder traversal.',
    layer: 'Pre-execution AST walk',
  },
  {
    risk: 'high',
    threat: 'Infinite loops / hanging jobs',
    mitigation:
      'A 120-second wall-clock timeout bounds every run. The worker is spawned as its own process-group leader so expiry triggers killpg with SIGKILL on POSIX, or taskkill /F /T on Windows, taking the whole child tree with it.',
    layer: 'Subprocess orchestrator',
  },
  {
    risk: 'high',
    threat: 'Memory exhaustion',
    mitigation:
      'resource.setrlimit(RLIMIT_AS, 1 GB) in the child pre-exec hook caps virtual memory before the worker can starve the host. An optional RLIMIT_CPU bounds pure CPU spin. Both are POSIX-only; Windows has no rlimit equivalent.',
    layer: 'OS pre-exec hook',
  },
  {
    risk: 'medium',
    threat: 'Log and payload flooding',
    mitigation:
      'Worker stdout above 256 KB fails the run outright rather than filling the response, the trade table is capped at 500 rows and the equity curve at 400 points, so a strategy that trades every bar cannot blow up the API or the browser.',
    layer: 'Output and payload caps',
  },
  {
    risk: 'high',
    threat: 'Filesystem and network egress',
    mitigation:
      'os, socket, urllib, shutil and pathlib are all outside the allowlist and the obvious escape hatches are refused, which closes the direct routes. This is a static guardrail, not a kernel boundary: libraries inside the allowlist still perform their own file and network I/O, and the worker inherits the API process environment, so run it unprivileged.',
    layer: 'Import allowlist + process boundary',
  },
]

const STACK = [
  { name: 'React 19', role: 'Frontend', note: 'Vite 8 · oxlint' },
  { name: 'FastAPI', role: 'Async backend', note: 'Uvicorn · Pydantic v2' },
  { name: 'PostgreSQL 16', role: 'Audit storage', note: 'Alembic migrations' },
  { name: 'Backtrader', role: 'Event simulation', note: '1.9.78.123' },
  { name: 'Groq', role: 'Code generation', note: 'openai/gpt-oss-120b' },
  { name: 'yfinance', role: 'NIFTY ingestion', note: '^NSEI daily' },
  { name: 'Docker', role: 'Multi-container', note: 'Compose · nginx' },
  { name: 'pytest', role: 'Test suite', note: 'Guardrail coverage' },
]

const LIMITATIONS = [
  {
    title: 'No authentication',
    body: 'A single local user is created on first use. There are no passwords, no multi-tenant isolation, no RBAC and no SSO — it is a single-operator workbench, not a hosted service.',
  },
  {
    title: 'No live brokerage gateway',
    body: 'Deployments are validated and recorded, but nothing schedules them against a live market and no order ever reaches a broker. There is no broker integration of any kind.',
  },
  {
    title: 'Single-position sizing',
    body: 'The default PercentSizer assumes one open position at a time. Cross-asset statistical arbitrage and dynamic portfolio rebalancing are not modelled.',
  },
  {
    title: 'Not a VM-level sandbox',
    body: 'Isolation is an AST allowlist, memory ceilings and OS process trees — not Firecracker or gVisor. A sufficiently clever payload inside the worker could still misbehave, so never run the worker as root.',
  },
  {
    title: 'Curated to NIFTY 50',
    body: 'Ingestion maps to the ^NSEI index. Individual NSE constituents, intraday bars, tick data and crypto feeds are not part of this distribution.',
  },
  {
    title: 'No guaranteed returns',
    body: 'Generated strategies are experimental hypotheses exposed to overfitting, lookahead bias and slippage the simulation does not model. The approval gate checks quality, never profitability.',
  },
]

const DOCKER_CMD = 'docker compose up --build'

const MANUAL_CMD = [
  '# 1. Environment & database',
  'cp .env.example .env        # then paste GROQ_API_KEY',
  'docker compose up -d db',
  '',
  '# 2. FastAPI backend',
  'python -m venv venv',
  'source venv/bin/activate    # Windows: venv\\Scripts\\Activate',
  'pip install -r requirements.txt',
  'uvicorn app.main:app --reload',
  '',
  '# 3. React frontend',
  'cd ../frontend && npm install && npm run dev',
].join('\n')

/* --------------------------------------------------------------- utilities */

function SectionHead({ eyebrow, title, lede, aside }) {
  return (
    <div className="landing__section-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2 className="landing__section-title">{title}</h2>
        {lede && <p className="landing__section-lede">{lede}</p>}
      </div>
      {aside}
    </div>
  )
}

/**
 * Builds the equity + benchmark polylines from the sampled NAV series.
 *
 * Both series share one y-domain so the vertical gap between them is the actual
 * performance difference rather than two independently scaled charts — the
 * single most misleading thing a marketing chart can do.
 */
function useEquityPaths() {
  return useMemo(() => {
    const W = 1000
    const H = 240
    const PAD = 18
    const all = [...SAMPLE_EQUITY, ...SAMPLE_BENCHMARK]
    const lo = Math.min(...all)
    const hi = Math.max(...all)
    const span = hi - lo || 1
    const count = SAMPLE_EQUITY.length

    const toPath = (series) =>
      series
        .map((value, index) => {
          const x = PAD + (index / (count - 1)) * (W - PAD * 2)
          const y = H - PAD - ((value - lo) / span) * (H - PAD * 2)
          return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
        })
        .join(' ')

    const gridYs = [0.25, 0.5, 0.75].map((f) => PAD + f * (H - PAD * 2))
    const labels = [hi, (hi + lo) / 2, lo].map((v) => Math.round(v / 1000).toString())

    /* X ticks come from the real sampled dates so the axis states the window
       instead of implying one. Anchored first/last, aligned to the text edges. */
    const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const index = Math.round(f * (count - 1))
      const x = PAD + f * (W - PAD * 2)
      return {
        x: f === 0 ? x + 4 : f === 1 ? x - 4 : x,
        anchor: f === 0 ? 'start' : f === 1 ? 'end' : 'middle',
        label: SAMPLE_DATES[index].slice(0, 7),
      }
    })

    return {
      path: toPath(SAMPLE_EQUITY),
      benchPath: toPath(SAMPLE_BENCHMARK),
      area: `${toPath(SAMPLE_EQUITY)} L${W - PAD},${H - PAD} L${PAD},${H - PAD} Z`,
      gridYs,
      labels,
      xTicks,
      H,
    }
  }, [])
}

function EquityPreview() {
  const { path, benchPath, area, gridYs, labels, xTicks, H } = useEquityPaths()
  const m = SAMPLE_METRICS

  return (
    <div className="landing__chart-card">
      <div className="landing__chart-head">
        <div className="landing__legend">
          <span className="landing__legend-item landing__legend-item--strategy">
            <span className="landing__legend-swatch" aria-hidden="true" />
            Strategy net NAV
          </span>
          <span className="landing__legend-item">
            <span className="landing__legend-swatch landing__legend-swatch--bench" aria-hidden="true" />
            NIFTY 50 buy &amp; hold
          </span>
        </div>
        <span className="landing__chart-period">
          {SAMPLE_STRATEGY.startDate} → {SAMPLE_STRATEGY.endDate}
        </span>
      </div>

      <div className="landing__chart-body">
        <svg
          className="landing__chart-svg"
          viewBox={`0 0 1000 ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`Strategy net value rose from ${m.value_start.toLocaleString()} to ${m.value_end.toLocaleString()} over three years, against a buy and hold benchmark returning ${m.benchmark_return_pct} percent.`}
        >
          {gridYs.map((y) => (
            <line key={y} x1="0" x2="1000" y1={y} y2={y} className="landing__chart-grid" />
          ))}
          <path d={benchPath} className="landing__chart-line landing__chart-line--bench" />
          <path d={area} className="landing__chart-area" />
          <path d={path} className="landing__chart-line landing__chart-line--strategy" />
          {gridYs.map((y, i) => (
            <text key={y} x="6" y={y - 5} className="landing__chart-label">
              {labels[i]}k
            </text>
          ))}
          {xTicks.map((tick) => (
            <text
              key={tick.label}
              x={tick.x}
              y={H - 4}
              textAnchor={tick.anchor}
              className="landing__chart-label"
            >
              {tick.label}
            </text>
          ))}
        </svg>

        <span className="landing__chart-readout">
          NAV {m.total_return_pct.toFixed(2)}% vs {m.benchmark_return_pct.toFixed(2)}%
        </span>
      </div>

      <div className="landing__verdict">
        <Icon name="military_tech" size={20} />
        <span className="landing__verdict-label">Benchmark verdict</span>
        <span className="landing__verdict-text">
          Beat buy &amp; hold by{' '}
          <strong>{(m.total_return_pct - m.benchmark_return_pct).toFixed(2)} points</strong> — with a{' '}
          {m.win_rate_pct.toFixed(0)}% win rate, which is exactly why the app scores the{' '}
          <em>outcome</em> rather than the hit rate.
        </span>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------- page */

export default function DocsArticle() {
  const m = SAMPLE_METRICS

  const statTiles = [
    { label: 'Total return', value: `${m.total_return_pct.toFixed(2)}%`, sub: `vs ${m.benchmark_return_pct.toFixed(2)}% buy & hold`, tone: 'up' },
    { label: 'CAGR', value: `${m.cagr_pct.toFixed(2)}%`, sub: '3 yr, annualised in the parent', tone: 'flat' },
    { label: 'Sharpe', value: m.sharpe.toFixed(2), sub: 'backtrader TimeReturn series', tone: 'flat' },
    { label: 'Sortino', value: m.sortino.toFixed(2), sub: 'downside deviation only', tone: 'flat' },
    { label: 'Max drawdown', value: `-${m.max_drawdown_pct.toFixed(2)}%`, sub: `${m.max_drawdown_duration_bars.toFixed(0)} bars underwater`, tone: 'down' },
    { label: 'Profit factor', value: m.profit_factor.toFixed(2), sub: `${SAMPLE_TRADES.wins} W / ${SAMPLE_TRADES.losses} L`, tone: 'flat' },
  ]

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

        {/* --------------------------------------------- quick feature grid */}
        <section className="landing__quick" aria-label="Product areas">
          <div className="landing__quick-grid">
            {QUICK.map((item) => (
              <Link key={item.title} className="landing__quick-card" to={item.to}>
                <span className="landing__quick-icon" aria-hidden="true">
                  <Icon name={item.icon} size={22} />
                </span>
                <span className="landing__quick-title">{item.title}</span>
                <span className="landing__quick-body">{item.body}</span>
              </Link>
            ))}
          </div>
        </section>

        {/* --------------------------------------------------- disclaimer */}
        <section className="landing__notice" role="note">
          <Icon name="warning" size={22} />
          <div>
            <strong className="landing__notice-title">Regulatory &amp; algorithmic safety notice</strong>
            <p>
              <strong>Educational prototype only.</strong> This tool runs deterministic simulation and
              paper-trading bookkeeping on historical NIFTY 50 data. It is not investment advice, not a
              financial recommendation, and not a broker gateway — it places no orders of any kind. Past
              backtested performance does not guarantee future returns.
            </p>
          </div>
        </section>

        {/* ---------------------------------------------- how it works */}
        <section className="landing__section" id="how-it-works">
          <SectionHead
            eyebrow="System pipeline"
            title="Four-state lifecycle"
            lede="No code runs uninspected. Every strategy passes schema extraction, an AST quarantine, a parameterised backtest and an explicit human decision before it can be recorded as a deployment."
          />
          <div className="landing__pipeline">
            {PIPELINE.map((step, index) => (
              <article key={step.title} className="landing__step">
                <div className="landing__step-top">
                  <span className="landing__step-num">{String(index + 1).padStart(2, '0')}</span>
                  <Icon name={step.icon} size={20} />
                </div>
                <h3 className="landing__step-title">{step.title}</h3>
                <p className="landing__step-body">{step.body}</p>
                <p className="landing__step-foot">
                  <span>{step.foot[0]}:</span> {step.foot[1]}
                </p>
              </article>
            ))}
          </div>

          <div className="landing__branch">
            <span className="landing__branch-label">
              <Icon name="account_tree" size={18} />
              Rejection branch
            </span>
            <span>AST check fails → nothing executes, the API returns the refused construct</span>
            <span aria-hidden="true">•</span>
            <span>Operator rejects → reason stored, strategy archived and unreachable for deployment</span>
          </div>
        </section>

        {/* --------------------------------------------------- features */}
        <section className="landing__section" id="features">
          <SectionHead
            eyebrow="Capabilities"
            title="Engineered for technical precision"
            lede="Six things this workbench actually does, and the exact mechanism behind each one."
          />
          <div className="landing__features">
            {FEATURES.map((feature) => (
              <article key={feature.title} className="landing__feature">
                <div className="landing__feature-icon">
                  <Icon name={feature.icon} size={20} />
                </div>
                <h3 className="landing__feature-title">{feature.title}</h3>
                <p className="landing__feature-body">{feature.body}</p>
                <p className="landing__feature-foot">{feature.foot[0]}</p>
                <p className="landing__feature-value">{feature.foot[1]}</p>
              </article>
            ))}
          </div>
        </section>

        {/* ---------------------------------------------------- metrics */}
        <section className="landing__section" id="metrics">
          <SectionHead
            eyebrow="Performance analytics"
            title="What the engine measures"
            lede="Actual output from this repository's own sandbox worker, run against the checked-in nifty50.csv test fixture — a bundled sample series, not a live Yahoo download. Nothing here is illustrative — but it is also not a recommendation, and it is not a good strategy."
            aside={
              <span className="landing__chip landing__chip--lg">
                Sandbox worker output · {SAMPLE_STRATEGY.name}
              </span>
            }
          />

          <div className="landing__stats">
            {statTiles.map((tile) => (
              <div key={tile.label} className="landing__stat">
                <span className="landing__stat-label">{tile.label}</span>
                <span className={`landing__stat-value landing__stat-value--${tile.tone}`}>{tile.value}</span>
                <span className="landing__stat-sub">{tile.sub}</span>
              </div>
            ))}
          </div>

          <EquityPreview />

          <p className="landing__fineprint">
            Reproduce it: from the <code>backend/</code> directory, pipe the sample class into{' '}
            <code>
              python -m app.services.strategy_runner --data tests/fixtures/nifty50.csv
            </code>{' '}
            using the worker defaults (₹100,000 cash, 0.1% commission, 95% PercentSizer). The sample returns{' '}
            {m.total_return_pct.toFixed(2)}% against a {m.benchmark_return_pct.toFixed(2)}% buy &amp;
            hold on the same bars — a modest edge, on a single historical window, with no out-of-sample
            split. That is the honest ceiling of what one backtest can tell you.
          </p>
        </section>

        {/* ---------------------------------------------------- security */}
        <section className="landing__section" id="security">
          <SectionHead
            eyebrow="Subprocess hardening"
            title="Multi-layer threat mitigation"
            lede="Running code a language model wrote means assuming it is hostile. Every layer below is a real check in the codebase, and the last section of this page is explicit about what they do not cover."
          />
          <div className="landing__table-wrap">
            <table className="landing__table">
              <thead>
                <tr>
                  <th scope="col">Threat vector</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Mitigation</th>
                  <th scope="col">Where it lives</th>
                </tr>
              </thead>
              <tbody>
                {THREATS.map((row) => (
                  <tr key={row.threat}>
                    <th scope="row">{row.threat}</th>
                    <td>
                      <span className={`landing__risk landing__risk--${row.risk}`}>{row.risk}</span>
                    </td>
                    <td className="landing__table-muted">{row.mitigation}</td>
                    <td className="landing__table-layer">{row.layer}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="landing__fineprint">
            This is a subprocess sandbox, not a container or cgroup boundary. A clever payload running{' '}
            <em>inside</em> the worker could still misbehave within its OS user privileges — run the
            worker as an unprivileged user and treat the host accordingly.
          </p>
        </section>

        {/* -------------------------------------------------- tech stack */}
        <section className="landing__section" id="tech-stack">
          <SectionHead eyebrow="Core infrastructure" title="Built on boring, proven tooling" />
          <div className="landing__stack">
            {STACK.map((item) => (
              <div key={item.name} className="landing__stack-tile">
                <span className="landing__stack-name">{item.name}</span>
                <span className="landing__stack-role">{item.role}</span>
                <span className="landing__stack-note">{item.note}</span>
              </div>
            ))}
          </div>
        </section>

        {/* --------------------------------------------------- quickstart */}
        <section className="landing__section" id="quickstart">
          <SectionHead
            eyebrow="Developer setup"
            title="Running in under a minute"
            lede="Two paths. Both need a free Groq API key — everything except chat works without one."
          />
          <div className="landing__paths">
            <article className="landing__path landing__path--dark">
              <div className="landing__path-head">
                <span className="landing__path-title">
                  <Icon name="dock" size={18} />
                  Path A · Docker Compose
                </span>
                <span className="landing__chip landing__chip--dark">Recommended</span>
              </div>
              <p className="landing__path-body">
                Brings up Postgres 16, the FastAPI backend (migrations applied on startup) and the nginx
                frontend in one command. No host Python needed.
              </p>
              <div className="landing__cmd landing__cmd--dark">
                <code>{DOCKER_CMD}</code>
                <CopyButton text={DOCKER_CMD} label="Copy" />
              </div>
              <p className="landing__path-foot">
                <span>Frontend :3000 · API :8000 · DB :5432</span>
                <span>Zero host Python</span>
              </p>
            </article>

            <article className="landing__path">
              <div className="landing__path-head">
                <span className="landing__path-title">
                  <Icon name="terminal" size={18} />
                  Path B · Manual environment
                </span>
                <span className="landing__chip">Python 3.11+ · Node 20+</span>
              </div>
              <p className="landing__path-body">
                Full control over the virtualenv and hot reload. Run this from the{' '}
                <code>backend/</code> directory.
              </p>
              <div className="landing__cmd">
                <pre>
                  <code>{MANUAL_CMD}</code>
                </pre>
                <CopyButton text={MANUAL_CMD} label="Copy all" />
              </div>
              <p className="landing__path-foot">
                <span>API :8000 · Vite :5173</span>
                <span>Hot reload on</span>
              </p>
            </article>
          </div>
          <p className="landing__fineprint">
            Windows users: activate with <code>venv\Scripts\Activate</code>. Do not run local uvicorn and
            the compose backend at once — they collide on port 8000.
          </p>
        </section>

        {/* ------------------------------------------------- limitations */}
        <section className="landing__section" id="limitations">
          <SectionHead
            eyebrow="Scope &amp; intent"
            title="What this platform is not"
            lede="Explicit operational boundaries. A research tool that oversells its scope is worse than no tool."
          />
          <div className="landing__limits">
            {LIMITATIONS.map((limit) => (
              <article key={limit.title} className="landing__limit">
                <h3 className="landing__limit-title">
                  <Icon name="cancel" size={19} />
                  {limit.title}
                </h3>
                <p className="landing__limit-body">{limit.body}</p>
              </article>
            ))}
          </div>
        </section>

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