function Strategy() {
  return (
    <div className="strategy-page">

      {/* Header */}
      <section className="strategy-header">
        <div>
          <p className="eyebrow">STRATEGY BUILDER</p>

          <h2>Build your trading strategy</h2>

          <p>
            Define your trading logic, customize conditions, and prepare your
            strategy for backtesting.
          </p>
        </div>

        <div className="strategy-actions">
          <button className="secondary-button">
            Save Draft
          </button>

          <button className="primary-button">
            Run Backtest →
          </button>
        </div>
      </section>


      {/* Strategy Name */}
      <section className="panel strategy-name-panel">

        <div className="section-title">
          <div className="section-number">01</div>

          <div>
            <h3>Strategy Details</h3>
            <p>Give your strategy a name and select the market.</p>
          </div>
        </div>

        <div className="form-grid">

          <div className="form-group">
            <label>Strategy Name</label>

            <input
              type="text"
              placeholder="e.g. RSI Momentum Strategy"
              defaultValue="RSI Momentum Strategy"
            />
          </div>

          <div className="form-group">
            <label>Market</label>

            <select defaultValue="NIFTY 50">
              <option>NIFTY 50</option>
              <option>BANKNIFTY</option>
              <option>FINNIFTY</option>
              <option>Stocks</option>
            </select>
          </div>

        </div>

      </section>


      {/* Entry Conditions */}
      <section className="panel">

        <div className="section-title">

          <div className="section-number">
            02
          </div>

          <div>
            <h3>Entry Conditions</h3>

            <p>
              Define when your strategy should enter a trade.
            </p>
          </div>

        </div>


        <div className="condition-card">

          <div className="condition-label">
            IF
          </div>

          <select defaultValue="RSI">
            <option>RSI</option>
            <option>MACD</option>
            <option>Moving Average</option>
            <option>Bollinger Bands</option>
          </select>

          <select defaultValue="<">
            <option>&lt;</option>
            <option>&gt;</option>
            <option>=</option>
          </select>

          <input
            type="number"
            defaultValue="30"
          />

          <span className="condition-unit">
            value
          </span>

        </div>


        <button className="add-condition">
          + Add Entry Condition
        </button>

      </section>


      {/* Exit Conditions */}
      <section className="panel">

        <div className="section-title">

          <div className="section-number">
            03
          </div>

          <div>
            <h3>Exit Conditions</h3>

            <p>
              Define when your strategy should close a position.
            </p>
          </div>

        </div>


        <div className="condition-card">

          <div className="condition-label">
            IF
          </div>

          <select defaultValue="RSI">
            <option>RSI</option>
            <option>MACD</option>
            <option>Moving Average</option>
            <option>Bollinger Bands</option>
          </select>

          <select defaultValue=">">
            <option>&gt;</option>
            <option>&lt;</option>
            <option>=</option>
          </select>

          <input
            type="number"
            defaultValue="70"
          />

          <span className="condition-unit">
            value
          </span>

        </div>


        <button className="add-condition">
          + Add Exit Condition
        </button>

      </section>


      {/* Risk Management */}
      <section className="panel">

        <div className="section-title">

          <div className="section-number">
            04
          </div>

          <div>
            <h3>Risk Management</h3>

            <p>
              Control your potential losses and define your targets.
            </p>
          </div>

        </div>


        <div className="risk-grid">

          <div className="risk-card">

            <span>Stop Loss</span>

            <strong>2%</strong>

            <input
              type="range"
              min="0"
              max="10"
              defaultValue="2"
            />

          </div>


          <div className="risk-card">

            <span>Take Profit</span>

            <strong>5%</strong>

            <input
              type="range"
              min="0"
              max="20"
              defaultValue="5"
            />

          </div>


          <div className="risk-card">

            <span>Position Size</span>

            <strong>10%</strong>

            <input
              type="range"
              min="1"
              max="100"
              defaultValue="10"
            />

          </div>

        </div>

      </section>


      {/* Strategy Summary */}
      <section className="strategy-summary">

        <div>

          <p className="eyebrow">
            STRATEGY READY
          </p>

          <h3>
            RSI Momentum Strategy
          </h3>

          <p>
            NIFTY 50 • RSI based momentum • Medium Risk
          </p>

        </div>


        <button className="primary-button">
          Run Backtest →
        </button>

      </section>

    </div>
  );
}

export default Strategy;