import MetricCard from "../components/MetricCard";

function Dashboard() {
  return (
    <div className="dashboard">
      <section className="welcome-section">
        <div>
          <p className="eyebrow">MARKET WORKSPACE</p>
          <h2>Good morning, Shraddha.</h2>
          <p>
            Monitor your strategies, analyze performance, and build your next
            trading idea with AI.
          </p>
        </div>

        <button className="primary-button">
          + Create Strategy
        </button>
      </section>

      <section className="metrics-grid">
        <MetricCard
          label="Portfolio Value"
          value="₹12,45,000"
          change="+12.48%"
          type="success"
        />

        <MetricCard
          label="Today's P&L"
          value="+₹8,420"
          change="+2.31%"
          type="success"
        />

        <MetricCard
          label="Sharpe Ratio"
          value="1.84"
          change="Good"
          type="success"
        />

        <MetricCard
          label="Max Drawdown"
          value="-8.4%"
          change="Controlled"
          type="warning"
        />
      </section>

      <section className="dashboard-grid">
        <div className="panel performance-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">PERFORMANCE</p>
              <h3>Portfolio Performance</h3>
            </div>

            <select>
              <option>6 Months</option>
              <option>1 Year</option>
              <option>3 Years</option>
            </select>
          </div>

          <div className="chart-placeholder">
            <div className="chart-line">
              ╱╲__╱╲___╱╲____╱╲
            </div>

            <div className="chart-labels">
              <span>Mar</span>
              <span>Apr</span>
              <span>May</span>
              <span>Jun</span>
              <span>Jul</span>
              <span>Aug</span>
            </div>
          </div>
        </div>

        <div className="panel strategies-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">STRATEGIES</p>
              <h3>Recent Strategies</h3>
            </div>

            <button className="text-button">View all</button>
          </div>

          <div className="strategy-row">
            <div>
              <strong>RSI Momentum</strong>
              <span>NIFTY 50 • 5 min</span>
            </div>
            <span className="positive">+18.4%</span>
          </div>

          <div className="strategy-row">
            <div>
              <strong>MACD Crossover</strong>
              <span>BANKNIFTY • 15 min</span>
            </div>
            <span className="positive">+12.7%</span>
          </div>

          <div className="strategy-row">
            <div>
              <strong>Mean Reversion</strong>
              <span>RELIANCE • Daily</span>
            </div>
            <span className="negative">-3.2%</span>
          </div>
        </div>
      </section>
    </div>
  );
}

export default Dashboard;