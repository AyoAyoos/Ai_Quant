function AIChat() {
  return (
    <div className="ai-chat-page">
      <div className="ai-chat-header">
        <div>
          <p className="eyebrow">AI QUANT ASSISTANT</p>
          <h2>Turn your trading idea into a strategy.</h2>
          <p>
            Describe your trading requirements in natural language and let AI
            structure them into an executable strategy.
          </p>
        </div>

        <div className="ai-status">
          <span></span>
          AI Online
        </div>
      </div>

      <div className="chat-container">
        <div className="chat-welcome">
          <div className="ai-icon">✦</div>

          <h3>What would you like to build?</h3>

          <p>
            Describe your market, indicators, risk level, holding period, or
            any other trading requirement.
          </p>
        </div>

        <div className="suggestions">
          <button>
            Create an RSI strategy
          </button>

          <button>
            Build a NIFTY 50 strategy
          </button>

          <button>
            Create a low-risk strategy
          </button>
        </div>

        <div className="chat-input-area">
          <textarea
            placeholder="Describe your trading strategy..."
            rows="3"
          />

          <button className="primary-button">
            Generate Strategy →
          </button>
        </div>
      </div>
    </div>
  );
}

export default AIChat;