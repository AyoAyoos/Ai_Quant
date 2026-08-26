function Analytics() {
  return (
    <div className="analytics-page">

      {/* HEADER */}
      <section className="analytics-header">
        <div>
          <p className="eyebrow">QUANT ANALYTICS</p>

          <h2>Understand your strategy performance.</h2>

          <p>
            Analyze returns, risk, consistency, and trading behavior across
            your strategies.
          </p>
        </div>

        <select className="analytics-select">
          <option>RSI Momentum Strategy</option>
          <option>MACD Crossover</option>
          <option>Mean Reversion</option>
        </select>
      </section>


      {/* PERFORMANCE METRICS */}
      <section className="analytics-metrics">

        <div className="analytics-card">
          <span>Total Return</span>
          <strong className="positive">+24.85%</strong>
          <small>vs benchmark +14.2%</small>
        </div>

        <div className="analytics-card">
          <span>Sharpe Ratio</span>
          <strong>1.84</strong>
          <small>Risk-adjusted performance</small>
        </div>

        <div className="analytics-card">
          <span>Win Rate</span>
          <strong>68.2%</strong>
          <small>208 total trades</small>
        </div>

        <div className="analytics-card">
          <span>Profit Factor</span>
          <strong>2.14</strong>
          <small>Strong profitability</small>
        </div>

        <div className="analytics-card">
          <span>Max Drawdown</span>
          <strong className="negative">-8.4%</strong>
          <small>Controlled risk</small>
        </div>

        <div className="analytics-card">
          <span>Avg. Trade</span>
          <strong>₹119</strong>
          <small>Per completed trade</small>
        </div>

      </section>


      {/* PERFORMANCE CHART */}
      <section className="panel analytics-chart-panel">

        <div className="panel-header">

          <div>
            <p className="eyebrow">PERFORMANCE</p>
            <h3>Strategy vs Benchmark</h3>
          </div>

          <div className="chart-filters">
            <button className="active-filter">1Y</button>
            <button>3Y</button>
            <button>5Y</button>
            <button>MAX</button>
          </div>

        </div>


        <div className="analytics-chart">

          <div className="analytics-y-axis">
            <span>140%</span>
            <span>120%</span>
            <span>100%</span>
            <span>80%</span>
            <span>60%</span>
          </div>

          <div className="analytics-chart-area">

            <div className="strategy-curve">
              ╱╲___╱╲____╱╲___╱╲____╱╲
            </div>

            <div className="benchmark-curve">
              ╱╲____╱╲___╱╲____╱╲___╱
            </div>

            <div className="analytics-grid-line line-1"></div>
            <div className="analytics-grid-line line-2"></div>
            <div className="analytics-grid-line line-3"></div>
            <div className="analytics-grid-line line-4"></div>

            <div className="analytics-x-axis">
              <span>Jan</span>
              <span>Mar</span>
              <span>May</span>
              <span>Jul</span>
              <span>Aug</span>
            </div>

          </div>

        </div>


        <div className="chart-keys">

          <span>
            <i className="strategy-dot"></i>
            Strategy
          </span>

          <span>
            <i className="benchmark-dot"></i>
            NIFTY 50
          </span>

        </div>

      </section>


      {/* TWO COLUMN ANALYSIS */}
      <section className="analytics-grid">


        {/* RISK */}
        <div className="panel">

          <div className="panel-header">

            <div>
              <p className="eyebrow">RISK ANALYSIS</p>
              <h3>Risk Profile</h3>
            </div>

          </div>


          <div className="risk-analysis">

            <div className="risk-row">
              <span>Volatility</span>

              <div className="progress">
                <div
                  className="progress-fill"
                  style={{ width: "42%" }}
                ></div>
              </div>

              <strong>42%</strong>
            </div>


            <div className="risk-row">
              <span>Drawdown Risk</span>

              <div className="progress">
                <div
                  className="progress-fill"
                  style={{ width: "28%" }}
                ></div>
              </div>

              <strong>28%</strong>
            </div>


            <div className="risk-row">
              <span>Market Exposure</span>

              <div className="progress">
                <div
                  className="progress-fill"
                  style={{ width: "64%" }}
                ></div>
              </div>

              <strong>64%</strong>
            </div>


            <div className="risk-row">
              <span>Consistency</span>

              <div className="progress">
                <div
                  className="progress-fill"
                  style={{ width: "76%" }}
                ></div>
              </div>

              <strong>76%</strong>
            </div>

          </div>

        </div>


        {/* MONTHLY PERFORMANCE */}
        <div className="panel">

          <div className="panel-header">

            <div>
              <p className="eyebrow">MONTHLY RETURNS</p>
              <h3>Performance Breakdown</h3>
            </div>

          </div>


          <div className="monthly-grid">

            <div>
              <span>Jan</span>
              <strong className="positive">+4.2%</strong>
            </div>

            <div>
              <span>Feb</span>
              <strong className="positive">+2.8%</strong>
            </div>

            <div>
              <span>Mar</span>
              <strong className="negative">-1.4%</strong>
            </div>

            <div>
              <span>Apr</span>
              <strong className="positive">+5.1%</strong>
            </div>

            <div>
              <span>May</span>
              <strong className="positive">+3.6%</strong>
            </div>

            <div>
              <span>Jun</span>
              <strong className="positive">+2.1%</strong>
            </div>

            <div>
              <span>Jul</span>
              <strong className="negative">-0.8%</strong>
            </div>

            <div>
              <span>Aug</span>
              <strong className="positive">+3.4%</strong>
            </div>

          </div>

        </div>

      </section>


      {/* AI INSIGHT */}
      <section className="analytics-ai">

        <div className="analytics-ai-icon">
          ✦
        </div>

        <div>

          <p className="eyebrow">
            AI ANALYTICS INSIGHT
          </p>

          <h3>
            Your strategy is outperforming the benchmark.
          </h3>

          <p>
            The strategy generated higher returns than the NIFTY 50 benchmark
            while maintaining a relatively controlled drawdown. Most profitable
            trades occurred during momentum-driven market periods.
          </p>

        </div>

      </section>

    </div>
  );
}

export default Analytics;