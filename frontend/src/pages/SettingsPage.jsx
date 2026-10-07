import { useEffect, useState } from 'react'
import { API_BASE, BACKTEST_TIMEOUT_MS, CHAT_TIMEOUT_MS, HEALTH_POLL_MS, fetchHealth } from '../lib/api.js'
import { isStorageAvailable } from '../lib/storage.js'
import Disclosure from '../components/Disclosure.jsx'

/**
 * Settings / System — page 7 of the 7-page split.
 *
 * UI ORGANIZATION ONLY. Configuration and system information moved here so the
 * dashboard stays a quick overview. Every value below is an existing constant
 * (lib/api.js timeouts, backtest defaults, documented sandbox limits) or a
 * live GET /health probe — nothing new is exposed and nothing is changed.
 */
export default function SettingsPage() {
  const [health, setHealth] = useState('checking')

  useEffect(() => {
    let cancelled = false
    fetchHealth()
      .then(() => {
        if (!cancelled) setHealth('online')
      })
      .catch(() => {
        if (!cancelled) setHealth('offline')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head__text">
          <p className="page-lede">
            Configuration and system information. Detailed technical reference lives here instead
            of crowding the dashboard.
          </p>
        </div>
      </div>

      <section className="panel" aria-labelledby="settings-general">
        <h2 className="section-title" id="settings-general">
          General
        </h2>
        <div className="kv">
          <div className="kv__item">
            <span className="kv__key">Theme</span>
            <span className="kv__value kv__value--muted">System theme (no in-app switch)</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Local preferences</span>
            <span className="kv__value kv__value--muted">
              {isStorageAvailable()
                ? 'Browser storage available — chat thread, strategy registry and cached backtests persist locally.'
                : 'Browser storage unavailable — history will not persist between reloads.'}
            </span>
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="settings-ai">
        <h2 className="section-title" id="settings-ai">
          AI / LLM
        </h2>
        <div className="kv">
          <div className="kv__item">
            <span className="kv__key">Provider</span>
            <span className="kv__value kv__value--muted">Groq</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Model</span>
            <span className="kv__value kv__value--muted">openai/gpt-oss-120b</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Chat timeout</span>
            <span className="kv__value kv__value--muted">
              {Math.round(CHAT_TIMEOUT_MS / 1000)} s (LLM chat is slow; 30–90 s typical)
            </span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Status</span>
            <span className="kv__value kv__value--muted">
              Requires a free Groq API key — everything except chat works without one.
            </span>
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="settings-backtest">
        <h2 className="section-title" id="settings-backtest">
          Backtesting
        </h2>
        <div className="kv">
          <div className="kv__item">
            <span className="kv__key">Default cash</span>
            <span className="kv__value kv__value--muted">₹100,000</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Default commission</span>
            <span className="kv__value kv__value--muted">0.1%</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Default position size</span>
            <span className="kv__value kv__value--muted">95% (PercentSizer)</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Worker cap</span>
            <span className="kv__value kv__value--muted">
              {Math.round(BACKTEST_TIMEOUT_MS / 1000)} s wall clock (gateway timeout on expiry)
            </span>
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="settings-data">
        <h2 className="section-title" id="settings-data">
          Data
        </h2>
        <div className="kv">
          <div className="kv__item">
            <span className="kv__key">Universe</span>
            <span className="kv__value kv__value--muted">NIFTY 50 (^NSEI), daily OHLCV bars</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Source</span>
            <span className="kv__value kv__value--muted">Yahoo Finance, two years on first run</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Cache</span>
            <span className="kv__value kv__value--muted">
              Local CSV store — stale cache is reused if Yahoo rate-limits
            </span>
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="settings-security">
        <h2 className="section-title" id="settings-security">
          Security
        </h2>
        <div className="kv">
          <div className="kv__item">
            <span className="kv__key">AST validation</span>
            <span className="kv__value kv__value--muted">
              Allowlist: backtrader, pandas, numpy, math, datetime — __import__, eval, exec, open,
              getattr and dunder traversal refused before execution
            </span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Sandbox</span>
            <span className="kv__value kv__value--muted">Separate subprocess, never the API process</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Memory limit</span>
            <span className="kv__value kv__value--muted">1 GB address-space cap (POSIX pre-exec hook)</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Execution timeout</span>
            <span className="kv__value kv__value--muted">120 s wall clock, process-tree kill on expiry</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Output limit</span>
            <span className="kv__value kv__value--muted">
              256 KB stdout ceiling · 500-row trade cap · 400-point equity cap
            </span>
          </div>
        </div>
        <Disclosure title="Technical details" meta="Subprocess hardening">
          <p className="disclaimer-text">
            This is a subprocess sandbox, not a container or cgroup boundary. A clever payload
            running inside the worker could still misbehave within its OS user privileges — run the
            worker as an unprivileged user and treat the host accordingly. Full threat table lives
            in Documentation.
          </p>
        </Disclosure>
      </section>

      <section className="panel" aria-labelledby="settings-system">
        <h2 className="section-title" id="settings-system">
          System
        </h2>
        <div className="kv">
          <div className="kv__item">
            <span className="kv__key">Backend</span>
            <span className="kv__value">
              {health === 'online' ? 'Online' : health === 'offline' ? 'Unreachable' : 'Checking…'}
            </span>
          </div>
          <div className="kv__item">
            <span className="kv__key">API base</span>
            <span className="kv__value kv__value--muted">{API_BASE}</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Database</span>
            <span className="kv__value kv__value--muted">PostgreSQL 16 (migrations applied on startup)</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Backtesting engine</span>
            <span className="kv__value kv__value--muted">Backtrader 1.9.78.123</span>
          </div>
          <div className="kv__item">
            <span className="kv__key">Health poll</span>
            <span className="kv__value kv__value--muted">Every {Math.round(HEALTH_POLL_MS / 1000)} s</span>
          </div>
        </div>
      </section>

      <p className="disclaimer-text">
        Educational prototype. Paper trading only. No live orders, no investment advice, no
        guaranteed returns.
      </p>
    </div>
  )
}
