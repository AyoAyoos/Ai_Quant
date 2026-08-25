import { useState, useRef, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

import './App.css'

const API_BASE = 'http://127.0.0.1:8000'

function App() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        'Hi! Describe the trading strategy you\'d like — e.g. "medium-risk NIFTY 50 strategy, hold 2-5 days, avoid high volatility."',
    },
  ])

  const [input, setInput] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const [loading, setLoading] = useState(false)

  // Finalized strategy returned by backend
  const [strategy, setStrategy] = useState(null)

  // Backtest results returned by backend
  const [backtestResults, setBacktestResults] = useState(null)

  const [backtestLoading, setBacktestLoading] = useState(false)
  const [backtestError, setBacktestError] = useState(null)

  const bottomRef = useRef(null)

  // =========================================================
  // AUTO SCROLL CHAT
  // =========================================================

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: 'smooth',
    })
  }, [messages])

  // =========================================================
  // SEND CHAT MESSAGE
  // =========================================================

  async function sendMessage() {
    if (!input.trim() || loading) return

    const userMsg = {
      role: 'user',
      content: input,
    }

    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          content: userMsg.content,
        }),
      })

      if (!res.ok) {
        throw new Error(`Chat request failed: ${res.status}`)
      }

      const data = await res.json()

      setConversationId(data.conversation_id)

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
        },
      ])

      // -------------------------------------------------------
      // Strategy was finalized
      // -------------------------------------------------------

      if (data.strategy) {
        setStrategy(data.strategy)

        // New strategy = remove previous backtest
        setBacktestResults(null)
        setBacktestError(null)
      }
    } catch (err) {
      console.error(err)

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            'Error reaching the backend. Is it running?',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  // =========================================================
  // RUN BACKTEST
  // =========================================================

  async function runBacktest() {
    if (!strategy?.id || backtestLoading) return

    setBacktestLoading(true)
    setBacktestError(null)
    setBacktestResults(null)

    try {
      const res = await fetch(
        `${API_BASE}/backtest/${strategy.id}`,
        {
          method: 'POST',
        }
      )

      if (!res.ok) {
        const errorData = await res.json().catch(() => null)

        throw new Error(
          errorData?.detail ||
            `Backtest failed: ${res.status}`
        )
      }

      const data = await res.json()

      console.log('BACKTEST RESPONSE:', data)

      setBacktestResults(data.results)
    } catch (err) {
      console.error(err)

      setBacktestError(
        err.message || 'Unable to run backtest.'
      )
    } finally {
      setBacktestLoading(false)
    }
  }

  // =========================================================
  // FORMAT MONEY
  // =========================================================

  function formatMoney(value) {
    if (value === null || value === undefined) {
      return '—'
    }

    return `₹${Number(value).toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`
  }

  // =========================================================
  // FORMAT NUMBER
  // =========================================================

  function formatNumber(value, decimals = 2) {
    if (value === null || value === undefined) {
      return '—'
    }

    return Number(value).toFixed(decimals)
  }

  // =========================================================
  // PREPARE EQUITY CURVE DATA
  // =========================================================

  const equityCurve =
    backtestResults?.equity_curve || []

  // =========================================================
  // UI
  // =========================================================

  return (
    <div className="chat-app">

      {/* =====================================================
          HEADER
      ===================================================== */}

      <header className="chat-header">

        <h1>Quant Strategy Assistant</h1>

        <p className="disclaimer">
          ⚠️ Educational prototype. No guaranteed returns.
          Paper trading only.
        </p>

      </header>

      {/* =====================================================
          CHAT WINDOW
      ===================================================== */}

      <div className="chat-window">

        {messages.map((m, i) => (
          <div
            key={i}
            className={`bubble ${m.role}`}
          >
            {m.content}
          </div>
        ))}

        {loading && (
          <div className="bubble assistant">
            Thinking…
          </div>
        )}

        <div ref={bottomRef} />

      </div>

      {/* =====================================================
          CHAT INPUT
      ===================================================== */}

      <div className="chat-input">

        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              sendMessage()
            }
          }}
          placeholder="Describe your strategy idea..."
          disabled={loading}
        />

        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
        >
          Send
        </button>

      </div>

      {/* =====================================================
          STRATEGY CARD
      ===================================================== */}

      {strategy && (

        <div className="strategy-panel">

          <div className="strategy-header">

            <div>

              <h2>Strategy Ready</h2>

              <h3>
                {strategy.name}
              </h3>

            </div>

            <span className="strategy-market">
              {strategy.market}
            </span>

          </div>

          <p className="strategy-description">
            {strategy.description}
          </p>

          <div className="strategy-details">

            <div>
              <strong>Timeframe</strong>
              <span>{strategy.timeframe}</span>
            </div>

            <div>
              <strong>Risk / Trade</strong>
              <span>
                {Number(
                  strategy.risk_management.risk_per_trade
                ) * 100}
                %
              </span>
            </div>

            <div>
              <strong>Stop Loss</strong>
              <span>
                {Number(
                  strategy.risk_management.stop_loss_pct
                ) * 100}
                %
              </span>
            </div>

            <div>
              <strong>Take Profit</strong>
              <span>
                {Number(
                  strategy.risk_management.take_profit_pct
                ) * 100}
                %
              </span>
            </div>

          </div>

          {/* =================================================
              RUN BACKTEST
          ================================================= */}

          <button
            className="backtest-button"
            onClick={runBacktest}
            disabled={backtestLoading}
          >

            {backtestLoading
              ? 'Running Backtest…'
              : 'Run Backtest'}

          </button>

          {backtestError && (

            <div className="backtest-error">
              {backtestError}
            </div>

          )}

        </div>

      )}

      {/* =====================================================
          BACKTEST RESULTS
      ===================================================== */}

      {backtestResults && (

        <div className="results-panel">

          <h2>Backtest Results</h2>

          <p className="results-period">

            {new Date(
              backtestResults.start_date
            ).toLocaleDateString('en-IN')}

            {' → '}

            {new Date(
              backtestResults.end_date
            ).toLocaleDateString('en-IN')}

          </p>

          {/* =================================================
              CAPITAL
          ================================================= */}

          <div className="results-grid">

            <div className="metric-card">
              <span>Initial Capital</span>

              <strong>
                {formatMoney(
                  backtestResults.initial_capital
                )}
              </strong>
            </div>

            <div className="metric-card">
              <span>Final Capital</span>

              <strong>
                {formatMoney(
                  backtestResults.final_capital
                )}
              </strong>
            </div>

            <div className="metric-card">
              <span>Total Return</span>

              <strong>
                {formatNumber(
                  backtestResults.total_return_pct
                )}
                %
              </strong>
            </div>

            <div className="metric-card">
              <span>CAGR</span>

              <strong>
                {formatNumber(
                  backtestResults.cagr_pct
                )}
                %
              </strong>
            </div>

          </div>

          {/* =================================================
              RISK / PERFORMANCE
          ================================================= */}

          <div className="results-grid">

            <div className="metric-card">
              <span>Sharpe Ratio</span>

              <strong>
                {formatNumber(
                  backtestResults.sharpe_ratio
                )}
              </strong>
            </div>

            <div className="metric-card">
              <span>Max Drawdown</span>

              <strong>
                {formatNumber(
                  backtestResults.max_drawdown_pct
                )}
                %
              </strong>
            </div>

            <div className="metric-card">
              <span>Win Rate</span>

              <strong>
                {formatNumber(
                  backtestResults.win_rate_pct
                )}
                %
              </strong>
            </div>

            <div className="metric-card">
              <span>Profit Factor</span>

              <strong>
                {formatNumber(
                  backtestResults.profit_factor
                )}
              </strong>
            </div>

          </div>

          {/* =================================================
              TRADE STATISTICS
          ================================================= */}

          <div className="results-grid">

            <div className="metric-card">
              <span>Total Trades</span>

              <strong>
                {backtestResults.num_trades}
              </strong>
            </div>

            <div className="metric-card">
              <span>Winning Trades</span>

              <strong>
                {backtestResults.winning_trades}
              </strong>
            </div>

            <div className="metric-card">
              <span>Losing Trades</span>

              <strong>
                {backtestResults.losing_trades}
              </strong>
            </div>

            <div className="metric-card">
              <span>Average Trade P&L</span>

              <strong>
                {formatMoney(
                  backtestResults.average_trade_pnl
                )}
              </strong>
            </div>

          </div>

          {/* =================================================
    TRADER-ORIENTED SUMMARY
================================================= */}

<div className="summary-panel">

  <h2>Quick Summary</h2>

  <div className="summary-grid">

    <div className="summary-item">
      <span>Historical Result</span>
      <strong>
        {backtestResults.total_return_pct > 0
          ? 'Profitable'
          : 'Loss-making'}
      </strong>
    </div>

    <div className="summary-item">
      <span>Risk</span>
      <strong>
        {backtestResults.max_drawdown_pct <= 5
          ? 'Low'
          : backtestResults.max_drawdown_pct <= 10
            ? 'Moderate'
            : 'High'}
      </strong>
    </div>

    <div className="summary-item">
      <span>Risk-Adjusted Performance</span>
      <strong>
        {backtestResults.sharpe_ratio === null
          ? 'Not Available'
          : backtestResults.sharpe_ratio >= 1
            ? 'Strong'
            : backtestResults.sharpe_ratio >= 0
              ? 'Moderate'
              : 'Weak'}
      </strong>
    </div>

    <div className="summary-item">
      <span>Win Rate</span>
      <strong>
        {formatNumber(backtestResults.win_rate_pct)}%
      </strong>
    </div>

    <div className="summary-item">
      <span>Profit Factor</span>
      <strong>
        {formatNumber(backtestResults.profit_factor)}
      </strong>
    </div>

  </div>

</div>

          {/* =================================================
              EQUITY CURVE
          ================================================= */}

          {equityCurve.length > 0 && (

            <div className="equity-panel">

              <h2>Equity Curve</h2>

              <p className="equity-description">
                Portfolio value throughout the backtest period.
              </p>

              <div className="equity-chart">

                <ResponsiveContainer
                  width="100%"
                  height={350}
                >

                  <LineChart
                    data={equityCurve}
                    margin={{
                      top: 20,
                      right: 30,
                      left: 20,
                      bottom: 20,
                    }}
                  >

                    <CartesianGrid
                      strokeDasharray="3 3"
                    />

                    <XAxis
                      dataKey="date"
                      tickFormatter={(date) =>
                        new Date(date).toLocaleDateString(
                          'en-IN',
                          {
                            month: 'short',
                            year: 'numeric',
                          }
                        )
                      }
                    />

                    <YAxis
                      tickFormatter={(value) =>
                        `₹${Number(value).toLocaleString(
                          'en-IN'
                        )}`
                      }
                    />

                    <Tooltip
                      formatter={(value) => [
                        formatMoney(value),
                        'Portfolio Value',
                      ]}
                      labelFormatter={(date) =>
                        new Date(
                          date
                        ).toLocaleDateString(
                          'en-IN'
                        )
                      }
                    />

                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="currentColor"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{
                        r: 5,
                      }}
                    />

                  </LineChart>

                </ResponsiveContainer>

              </div>

            </div>

          )}

        </div>

      )}

    </div>
  )
}

export default App