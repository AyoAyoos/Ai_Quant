export default function StrategyPreview({ config }) {
  const { market, tradingStyle, timeframe, indicators, entryConditions, exitConditions, riskManagement, indicatorParams } = config

  const formatMarket = (m) => {
    const markets = { NIFTY50: 'NIFTY 50', BANKNIFTY: 'BANK NIFTY', SENSEX: 'SENSEX', OTHER: 'Other' }
    return markets[m] || m
  }

  const formatStyle = (s) => {
    const styles = { scalping: 'Scalping', intraday: 'Intraday', swing: 'Swing', positional: 'Positional' }
    return styles[s] || s
  }

  const formatTimeframe = (tf) => {
    const tfs = { '5m': '5 Minutes', '15m': '15 Minutes', '30m': '30 Minutes', '1h': '1 Hour', '1d': '1 Day' }
    return tfs[tf] || tf
  }

  const formatIndicator = (ind) => {
    const params = indicatorParams?.[ind] || {}
    switch (ind) {
      case 'EMA':
        return `EMA ${params.fast || 20} / ${params.slow || 50}`
      case 'SMA':
        return `SMA ${params.period || 20}`
      case 'RSI':
        return `RSI ${params.period || 14} (${params.oversold || 30}/${params.overbought || 70})`
      case 'MACD':
        return `MACD ${params.fast || 12}/${params.slow || 26}/${params.signal || 9}`
      case 'BOLLINGER_BANDS':
        return `Bollinger Bands ${params.period || 20}, ${params.devfactor || 2}σ`
      case 'VOLUME':
        return 'Volume'
      default:
        return ind
    }
  }

  const formatEntry = () => {
    if (!entryConditions || entryConditions.length === 0) return 'Not defined'
    return entryConditions.map((c, i) => {
      const prefix = i > 0 ? `${c.logicalOp} ` : ''
      return `${prefix}${c.left} ${c.operator} ${c.right}`
    }).join(' ')
  }

  const formatExit = () => {
    const parts = []
    if (exitConditions?.exitOnOpposite) parts.push('Opposite signal')
    if (exitConditions?.customExits?.length) {
      parts.push(...exitConditions.customExits.map((c) => `${c.left} ${c.operator} ${c.right}`))
    }
    return parts.length > 0 ? parts.join(', ') : 'Not defined'
  }

  const formatRisk = () => {
    const parts = []
    if (riskManagement?.stopLoss?.enabled) parts.push(`SL: ${riskManagement.stopLoss.value}%`)
    if (riskManagement?.takeProfit?.enabled) parts.push(`TP: ${riskManagement.takeProfit.value}%`)
    if (riskManagement?.trailingStop?.enabled) parts.push(`Trailing: ${riskManagement.trailingStop.value}%`)
    if (riskManagement?.maxTradesPerDay) parts.push(`${riskManagement.maxTradesPerDay}/day`)
    return parts.length > 0 ? parts.join(', ') : 'Not configured'
  }

  return (
    <section className="strategy-section strategy-preview" aria-labelledby="preview-heading">
      <div className="strategy-section__head">
        <h2 id="preview-heading" className="strategy-section__title">Strategy Preview</h2>
      </div>

      <div className="preview-grid">
        <div className="preview-card">
          <div className="preview-card__header">
            <span className="preview-card__market">{formatMarket(market)}</span>
            <span className="preview-card__style">{formatStyle(tradingStyle)}</span>
            <span className="preview-card__timeframe">{formatTimeframe(timeframe)}</span>
          </div>

          <div className="preview-card__section">
            <h4 className="preview-card__section-title">Indicators</h4>
            <ul className="preview-card__list">
              {(indicators || []).map((ind) => (
                <li key={ind}><code>{formatIndicator(ind)}</code></li>
              ))}
              {(!indicators || indicators.length === 0) && <li className="preview-card__empty">None selected</li>}
            </ul>
          </div>

          <div className="preview-card__section">
            <h4 className="preview-card__section-title">Entry</h4>
            <p className="preview-card__text">{formatEntry()}</p>
          </div>

          <div className="preview-card__section">
            <h4 className="preview-card__section-title">Exit</h4>
            <p className="preview-card__text">{formatExit()}</p>
          </div>

          <div className="preview-card__section">
            <h4 className="preview-card__section-title">Risk</h4>
            <p className="preview-card__text">{formatRisk()}</p>
          </div>
        </div>
      </div>
    </section>
  )
}