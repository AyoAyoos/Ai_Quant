import { useState, useRef, useEffect, useCallback } from 'react'
import './App.css'

const API_BASE = 'http://localhost:8000'

function fmt(value, suffix = '', digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${Number(value).toFixed(digits)}${suffix}`
}

function StrategyCard({ strategy, result, error, running, onRun }) {
  const [showTrades, setShowTrades] = useState(false)
  const [showCode, setShowCode] = useState(false)
  const [code, setCode] = useState(null)
  const [codeError, setCodeError] = useState(null)

  async function toggleCode() {
    if (showCode) {
      setShowCode(false)
      return
    }
    setShowCode(true)
    if (code !== null) return
    try {
      const res = await fetch(`${API_BASE}/strategies/${strategy.strategy_id}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Could not load code (${res.status})`)
      setCode(data.generated_code || '(no code stored)')
    } catch (err) {
      setCodeError(err.message)
    }
  }

  return (
    <div className="strategy-card">
      <div className="strategy-head">
        <span className="strategy-badge">✅ Strategy created</span>
        <span className="strategy-name">{strategy.strategy_name}</span>
        {strategy.strategy_description && (
          <p className="strategy-desc">{strategy.strategy_description}</p>
        )}
      </div>

      <div className="strategy-actions">
        <button className="backtest-btn" onClick={onRun} disabled={running || !!result}>
          {running ? 'Running backtest…' : result ? 'Backtest complete' : 'Run backtest on NIFTY 50'}
        </button>
        <button className="ghost-btn" onClick={toggleCode}>
          {showCode ? 'Hide code' : 'View code'}
        </button>
      </div>

      {showCode && (
        <div className="code-viewer">
          {codeError && <div className="backtest-error">{codeError}</div>}
          {code !== null && !codeError && <pre className="code-block">{code}</pre>}
          {code === null && !codeError && <span className="muted-text">Loading…</span>}
        </div>
      )}

      {error && <div className="backtest-error">{error}</div>}

      {result && (
        <div className="metrics">
          <div className="metrics-grid">
            <Metric label="Total return" value={fmt(result.total_return_pct, '%')} good={result.total_return_pct > 0} bad={result.total_return_pct < 0} />
            <Metric label="Buy & hold" value={fmt(result.benchmark_return_pct, '%')} muted />
            <Metric label="CAGR" value={fmt(result.cagr_pct, '%')} good={result.cagr_pct > 0} bad={result.cagr_pct < 0} />
            <Metric label="Max drawdown" value={fmt(result.max_drawdown_pct, '%')} bad={result.max_drawdown_pct < 0} />
            <Metric label="Sharpe" value={fmt(result.sharpe)} />
            <Metric label="Sortino" value={fmt(result.sortino)} />
            <Metric label="Win rate" value={fmt(result.win_rate_pct, '%', 1)} />
            <Metric label="Trades" value={result.num_trades ?? '—'} />
          </div>

          <div className="metrics-range">
            {result.start_date && result.end_date ? (
              <span>{String(result.start_date).slice(0, 10)} → {String(result.end_date).slice(0, 10)}</span>
            ) : (
              <span>Period unavailable</span>
            )}
            {result.total_return_pct !== null && result.benchmark_return_pct !== null && (
              <span className={result.total_return_pct >= result.benchmark_return_pct ? 'edge good' : 'edge bad'}>
                {result.total_return_pct >= result.benchmark_return_pct ? 'Beat' : 'Lagged'} buy &amp; hold by{' '}
                {fmt(Math.abs(result.total_return_pct - result.benchmark_return_pct), ' pts')}
              </span>
            )}
          </div>

          {result.warnings?.length > 0 && (
            <ul className="warnings">
              {result.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}

          {result.equity_curve?.length > 1 && (
            <EquityChart curve={result.equity_curve} />
          )}

          {result.trades?.length > 0 && (
            <div className="trades-section">
              <button className="ghost-btn" onClick={() => setShowTrades((v) => !v)}>
                {showTrades ? 'Hide trades' : `Show trades (${result.trades.length})`}
              </button>
              {showTrades && <TradeTable trades={result.trades} truncated={result.trades_truncated} />}
            </div>
          )}

          <p className="disclaimer">Past performance does not guarantee future results. Educational prototype — paper trading only.</p>
        </div>
      )}
    </div>
  )
}

function Metric({ label, value, good, bad, muted }) {
  const tone = good ? 'good' : bad ? 'bad' : muted ? 'muted' : ''
  return (
    <div className={`metric ${tone}`}>
      <span className="metric-value">{value}</span>
      <span className="metric-label">{label}</span>
    </div>
  )
}

function EquityChart({ curve }) {
  const W = 560
  const H = 150
  const PAD = 8
  const values = curve.map((p) => p[1])
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const up = values[values.length - 1] >= values[0]
  const tone = up ? '#4ec9a5' : '#e57373'

  const pts = curve.map((p, i) => {
    const x = PAD + (i / (curve.length - 1)) * (W - PAD * 2)
    const y = PAD + (1 - (p[1] - min) / span) * (H - PAD * 2)
    return [x.toFixed(1), y.toFixed(1)]
  })
  const line = pts.map((p) => p.join(',')).join(' ')
  const area = `${PAD},${H - PAD} ${line} ${W - PAD},${H - PAD}`

  return (
    <div className="equity">
      <div className="equity-head">
        <span className="equity-title">Portfolio value</span>
        <span className="equity-range">
          {fmt(min, '', 0)} → {fmt(max, '', 0)}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="equity-svg" role="img" aria-label="Equity curve">
        <polygon points={area} fill={tone} opacity="0.12" />
        <polyline points={line} fill="none" stroke={tone} strokeWidth="1.8" strokeLinejoin="round" />
      </svg>
      <div className="equity-dates">
        <span>{curve[0][0]}</span>
        <span>{curve[curve.length - 1][0]}</span>
      </div>
    </div>
  )
}

function TradeTable({ trades, truncated }) {
  return (
    <div className="trade-table-wrap">
      <table className="trade-table">
        <thead>
          <tr>
            <th>Entry</th>
            <th>Exit</th>
            <th>Side</th>
            <th className="num">Size</th>
            <th className="num">Entry</th>
            <th className="num">Exit</th>
            <th className="num">P&amp;L</th>
            <th className="num">Bars</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className={t.won ? 'win' : 'loss'}>
              <td>{t.entry_date}</td>
              <td>{t.exit_date}</td>
              <td>{t.direction}</td>
              <td className="num">{t.size}</td>
              <td className="num">{fmt(t.entry_price, '', 0)}</td>
              <td className="num">{fmt(t.exit_price, '', 0)}</td>
              <td className="num">{t.pnl_net > 0 ? '+' : ''}{fmt(t.pnl_net, '', 0)}</td>
              <td className="num">{t.bars_held}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {truncated > 0 && (
        <p className="muted-text">Showing first {trades.length} of {trades.length + truncated} trades.</p>
      )}
    </div>
  )
}

function App() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hi! Describe the trading strategy you\u2019d like \u2014 e.g. "medium-risk NIFTY 50 strategy, hold 2-5 days, avoid high volatility."' }
  ])
  const [input, setInput] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [backtests, setBacktests] = useState({})
  const [runningId, setRunningId] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage() {
    if (!input.trim() || loading) return
    const userMsg = { role: 'user', content: input }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: conversationId, content: userMsg.content }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
      setConversationId(data.conversation_id)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
          strategy: data.strategy_id
            ? {
                strategy_id: data.strategy_id,
                strategy_name: data.strategy_name,
                strategy_description: data.strategy_description,
              }
            : null,
        },
      ])
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', content: err.message || 'Error reaching the backend. Is it running?' }])
    } finally {
      setLoading(false)
    }
  }

  const runBacktest = useCallback(async (strategyId) => {
    setRunningId(strategyId)
    setBacktests((prev) => ({ ...prev, [strategyId]: { error: null } }))
    try {
      const res = await fetch(`${API_BASE}/strategies/${strategyId}/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Backtest failed (${res.status})`)
      setBacktests((prev) => ({ ...prev, [strategyId]: { result: data } }))
    } catch (err) {
      setBacktests((prev) => ({ ...prev, [strategyId]: { error: err.message } }))
    } finally {
      setRunningId(null)
    }
  }, [])

  return (
    <div className="chat-app">
      <header className="chat-header">
        <h1>Quant Strategy Assistant</h1>
        <p className="disclaimer">⚠️ Educational prototype. No guaranteed returns. Paper trading only.</p>
      </header>

      <div className="chat-window">
        {messages.map((m, i) => (
          <div key={i} className="turn">
            <div className={`bubble ${m.role}`}>{m.content}</div>
            {m.strategy && (
              <StrategyCard
                strategy={m.strategy}
                result={backtests[m.strategy.strategy_id]?.result}
                error={backtests[m.strategy.strategy_id]?.error}
                running={runningId === m.strategy.strategy_id}
                onRun={() => runBacktest(m.strategy.strategy_id)}
              />
            )}
          </div>
        ))}
        {loading && <div className="bubble assistant">Thinking…</div>}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Describe your strategy idea..."
        />
        <button onClick={sendMessage} disabled={loading}>Send</button>
      </div>
    </div>
  )
}

export default App
