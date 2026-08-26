function Backtesting() {
  return (
    <div className="backtesting-page">

      {/* HEADER */}
      <section className="backtesting-header">
        <div>
          <p className="eyebrow">BACKTESTING ENGINE</p>

          <h2>Test your strategy against history.</h2>

          <p>
            Evaluate strategy performance using historical market data before
            considering paper trading.
          </p>
        </div>

        <div className="backtest-status">
          <span></span>
          Ready to backtest
        </div>
      </section>


      {/* CONFIGURATION */}
      <section className="panel">

        <div className="section-title">
          <div className="section-number">01</div>

          <div>
            <h3>Backtest Configuration</h3>
            <p>
              Select your strategy, market and historical period.
            </p>
          </div>
        </div>


        <div className="backtest-form">

          <div className="form-group">
            <label>Strategy</label>

            <select defaultValue="RSI Momentum Strategy">
              <option>RSI Momentum Strategy</option>
              <option>MACD Crossover</option>
              <option>Mean Reversion</option>
            </select>
          </div>


          <div className="form-group">
            <label>Instrument</label>

            <select defaultValue="NIFTY 50">
              <option>NIFTY 50</option>
              <option>BANKNIFTY</option>
              <option>FINNIFTY</option>
            </select>
          </div>


          <div className="form-group">
            <label>Timeframe</label>

            <select defaultValue="5 Minutes">
              <option>5 Minutes</option>
              <option>15 Minutes</option>
              <option>1 Hour</option>
              <option>Daily</option>
            </select>
          </div>


          <div className="form-group">
            <label>Initial Capital</label>

            <input
              type="text"
              defaultValue="₹1,00,000"
            />
          </div>


          <div className="form-group">
            <label>Start Date</label>

            <input
              type="date"
              defaultValue="2021-01-01"
            />
          </div>


          <div className="form-group">
            <label>End Date</label>

            <input
              type="date"
              defaultValue="2026-08-01"
            />
          </div>

        </div>


        <button className="primary-button run-button">
          ▶ Run Backtest
        </button>

      </section>


      {/* RESULTS */}
      <section className="results-section">

        <div className="results-header">
          <div>
            <p className="eyebrow">BACKTEST RESULTS</p>
            <h3>RSI Momentum Strategy</h3>
          </div>

          <span className="completed-badge">
            ✓ Completed
          </span>
        </div>


        {/* METRICS */}

        <div className="results-grid">

          <div className="result-card highlight">
            <span>Total Return</span>
            <strong>+24.85%</strong>
            <small>₹24,850 profit</small>
          </div>


          <div className="result-card">
            <span>Sharpe Ratio</span>
            <strong>1.84</strong>
            <small>Risk-adjusted return</small>
          </div>


          <div className="result-card">
            <span>Win Rate</span>
            <strong>68.2%</strong>
            <small>142 winning trades</small>
          </div>


          <div className="result-card danger-card">
            <span>Max Drawdown</span>
            <strong>-8.4%</strong>
            <small>Maximum portfolio decline</small>
          </div>

        </div>


        {/* CHART */}

        <div className="panel equity-panel">

          <div className="panel-header">

            <div>
              <p className="eyebrow">EQUITY CURVE</p>
              <h3>Portfolio Growth</h3>
            </div>

            <div className="chart-legend">
              <span></span>
              Strategy
            </div>

          </div>


          <div className="equity-chart">

            <div className="y-axis">
              <span>₹1.25L</span>
              <span>₹1.15L</span>
              <span>₹1.05L</span>
              <span>₹1.00L</span>
            </div>

            <div className="chart-area">

              <div className="equity-line">
                ╱╲___╱╲____╱╲___╱╲____╱╲
              </div>

              <div className="chart-grid-line"></div>
              <div className="chart-grid-line"></div>
              <div className="chart-grid-line"></div>

              <div className="x-axis">
                <span>2021</span>
                <span>2022</span>
                <span>2023</span>
                <span>2024</span>
                <span>2025</span>
                <span>2026</span>
              </div>

            </div>

          </div>

        </div>


        {/* TRADE STATISTICS */}

        <div className="panel trade-panel">

          <div className="panel-header">

            <div>
              <p className="eyebrow">TRADE ANALYSIS</p>
              <h3>Trade Statistics</h3>
            </div>

          </div>


          <div className="trade-grid">

            <div>
              <span>Total Trades</span>
              <strong>208</strong>
            </div>

            <div>
              <span>Winning Trades</span>
              <strong className="positive">142</strong>
            </div>

            <div>
              <span>Losing Trades</span>
              <strong className="negative">66</strong>
            </div>

            <div>
              <span>Profit Factor</span>
              <strong>2.14</strong>
            </div>

            <div>
              <span>Avg. Trade</span>
              <strong>₹119</strong>
            </div>

            <div>
              <span>Best Trade</span>
              <strong className="positive">+₹3,820</strong>
            </div>

          </div>

        </div>


        {/* AI SUMMARY */}

        <div className="ai-summary">

          <div className="ai-summary-icon">
            ✦
          </div>

          <div>

            <p className="eyebrow">
              AI PERFORMANCE SUMMARY
            </p>

            <h3>
              Your strategy shows positive historical performance.
            </h3>

            <p>
              The RSI Momentum Strategy generated a 24.85% return with a
              Sharpe ratio of 1.84 and a controlled maximum drawdown of 8.4%.
              The strategy achieved a 68.2% win rate across 208 trades.
            </p>

          </div>

        </div>

      </section>

    </div>
  );
}

export default Backtesting;