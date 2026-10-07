import { useState, useCallback, useMemo } from 'react'
import { generateStrategy, isNetworkError, isNotFound } from '../../lib/api.js'
import { registerStrategy } from '../../lib/storage.js'
import { useNavigate } from 'react-router-dom'
import MarketSection from './MarketSection.jsx'
import TradingStyleSection from './TradingStyleSection.jsx'
import TimeframeSection from './TimeframeSection.jsx'
import IndicatorsSection from './IndicatorsSection.jsx'
import { INDICATORS as INDICATOR_CATALOG } from './indicatorCatalog.js'
import EntryConditionsSection from './EntryConditionsSection.jsx'
import ExitRiskSection from './ExitRiskSection.jsx'
import StrategyPreview from './StrategyPreview.jsx'
import GenerationState from './GenerationState.jsx'

const DEFAULT_CONFIG = {
  market: 'NIFTY50',
  tradingStyle: 'intraday',
  timeframe: '15m',
  indicators: ['EMA'],
  indicatorParams: {
    EMA: { fast: 20, slow: 50 },
  },
  entryConditions: [
    { left: 'EMA 20', operator: 'crosses above', right: 'EMA 50', logicalOp: 'AND' },
  ],
  exitConditions: {
    exitOnOpposite: true,
    customExits: [],
  },
  riskManagement: {
    stopLoss: { enabled: true, value: 1 },
    takeProfit: { enabled: true, value: 2 },
    trailingStop: { enabled: false, value: 0.5 },
    maxTradesPerDay: 3,
  },
}

export default function StrategyBuilder() {
  const navigate = useNavigate()
  const [config, setConfig] = useState(DEFAULT_CONFIG)
  const [generationStatus, setGenerationStatus] = useState('idle')
  const [generationError, setGenerationError] = useState(null)
  const [generatedStrategy, setGeneratedStrategy] = useState(null)
  const [aiSuggestions, setAiSuggestions] = useState(null)

  // Validation
  const errors = useMemo(() => {
    const errs = {}
    if (!config.market) errs.market = 'Please select a market'
    if (!config.tradingStyle) errs.tradingStyle = 'Please select a trading style'
    if (!config.timeframe) errs.timeframe = 'Please select a timeframe'
    if (!config.indicators || config.indicators.length === 0) errs.indicators = 'Please select at least one indicator'
    if (!config.entryConditions || config.entryConditions.length === 0) errs.entryConditions = 'Please add at least one entry condition'
    if (config.riskManagement?.stopLoss?.enabled && config.riskManagement.stopLoss.value <= 0) {
      errs.riskManagement = 'Stop loss must be positive'
    }
    if (config.riskManagement?.takeProfit?.enabled && config.riskManagement.takeProfit.value <= 0) {
      errs.riskManagement = 'Take profit must be positive'
    }
    return errs
  }, [config])

  const hasErrors = Object.keys(errors).length > 0

  const updateConfig = useCallback((partial) => {
    setConfig((prev) => ({ ...prev, ...partial }))
  }, [])

  const updateIndicatorParam = useCallback((indicators, indicatorId, paramKey, value) => {
    setConfig((prev) => ({
      ...prev,
      indicatorParams: {
        ...prev.indicatorParams,
        [indicatorId]: { ...prev.indicatorParams[indicatorId], [paramKey]: value },
      },
    }))
  }, [])

  const handleGenerate = async () => {
    if (hasErrors) return

    setGenerationStatus('loading')
    setGenerationError(null)
    setAiSuggestions(null)

    try {
      // Build the spec for the backend — inside try so ANY failure (bad
      // config shape, request error) lands in catch and clears the spinner
      // instead of leaving status stuck on 'loading'.
      const spec = {
        market: config.market,
        trading_style: config.tradingStyle,
        timeframe: config.timeframe,
        indicators: config.indicators.map((indicatorId) => ({
          // State stores ids ('BOLLINGER_BANDS'); the backend schema accepts
          // display names ('Bollinger Bands'). Map id -> name, fall back to
          // the raw value so unknown ids still surface a backend 422.
          name:
            INDICATOR_CATALOG.find((i) => i.id === indicatorId)?.name ?? indicatorId,
          parameters: config.indicatorParams[indicatorId] || {},
        })),
        entry_conditions: config.entryConditions.map((c) =>
          `${c.left} ${c.operator} ${c.right}`
        ),
        exit_conditions: [
          ...(config.exitConditions.exitOnOpposite ? ['Exit on opposite signal'] : []),
          ...(config.exitConditions.customExits || []).map((c) => `${c.left} ${c.operator} ${c.right}`),
        ],
        risk_management: {
          stop_loss_percent: config.riskManagement.stopLoss.enabled ? config.riskManagement.stopLoss.value : null,
          take_profit_percent: config.riskManagement.takeProfit.enabled ? config.riskManagement.takeProfit.value : null,
          trailing_stop_percent: config.riskManagement.trailingStop.enabled ? config.riskManagement.trailingStop.value : null,
          max_trades_per_day: config.riskManagement.maxTradesPerDay,
        },
      }

      const result = await generateStrategy(spec)

      // Register the strategy in the local registry so it appears on the Strategies page
      registerStrategy({
        id: result.strategy_id,
        name: result.name,
        description: result.description,
      })

      setGeneratedStrategy(result)
      setGenerationStatus('success')
    } catch (err) {
      setGenerationStatus('error')
      if (isNetworkError(err)) {
        setGenerationError('Cannot reach the backend. Is it running?')
      } else if (isNotFound(err)) {
        setGenerationError('Strategy endpoint not found')
      } else {
        setGenerationError(err.message || 'Generation failed')
      }
    }
  }

  const handleRetry = () => {
    setGenerationStatus('idle')
    setGenerationError(null)
    handleGenerate()
  }

  const handleViewStrategy = () => {
    if (generatedStrategy?.strategy_id) {
      navigate(`/strategies/${generatedStrategy.strategy_id}`)
    }
  }

  const handleRunBacktest = () => {
    if (generatedStrategy?.strategy_id) {
      navigate(`/strategies/${generatedStrategy.strategy_id}/backtest`)
    }
  }

  const handleAIInterpret = async (_naturalLanguage) => {
    // For now, we'll simulate AI interpretation
    // In production, this would call a backend endpoint
    const mockSuggestions = [
      { left: 'EMA 20', operator: 'crosses above', right: 'EMA 50', logicalOp: 'AND' },
      { left: 'RSI', operator: 'is below', right: '30', logicalOp: 'AND' },
    ]
    setAiSuggestions(mockSuggestions)
  }

  const _acceptAISuggestions = () => {
    if (aiSuggestions) {
      setConfig((prev) => ({ ...prev, entryConditions: aiSuggestions }))
      setAiSuggestions(null)
    }
  }

  const previewConfig = useMemo(() => ({
    market: config.market,
    tradingStyle: config.tradingStyle,
    timeframe: config.timeframe,
    indicators: config.indicators,
    entryConditions: config.entryConditions,
    exitConditions: config.exitConditions,
    riskManagement: config.riskManagement,
    indicatorParams: config.indicatorParams,
  }), [config])

  return (
    <div className="strategy-builder-page">
      <header className="strategy-builder__header">
        <h1 className="strategy-builder__title">Create Your Trading Strategy</h1>
        <p className="strategy-builder__subtitle">
          Configure your strategy requirements and let AI generate the executable strategy.
        </p>
      </header>

      <form className="strategy-builder__form" onSubmit={(e) => e.preventDefault()}>
        <MarketSection
          value={config.market}
          onChange={(v) => updateConfig({ market: v })}
          error={errors.market}
        />

        <TradingStyleSection
          value={config.tradingStyle}
          onChange={(v) => updateConfig({ tradingStyle: v })}
          error={errors.tradingStyle}
        />

        <TimeframeSection
          value={config.timeframe}
          onChange={(v) => updateConfig({ timeframe: v })}
          tradingStyle={config.tradingStyle}
          error={errors.timeframe}
        />

        <IndicatorsSection
          value={config.indicators}
          onChange={(indicators, indicatorId, paramKey, value) => {
            if (indicatorId && paramKey) {
              updateIndicatorParam(indicators, indicatorId, paramKey, value)
            } else {
              updateConfig({ indicators })
            }
          }}
          error={errors.indicators}
        />

        <EntryConditionsSection
          value={config.entryConditions}
          onChange={(v) => updateConfig({ entryConditions: v })}
          availableIndicators={config.indicators}
          error={errors.entryConditions}
          onAIInterpret={handleAIInterpret}
          aiSuggestions={aiSuggestions}
        />

        <ExitRiskSection
          value={{ ...config?.exitConditions, ...config?.riskManagement }}
          onChange={(v) => {
            // The section edits one combined object; split it back into the
            // two config keys handleGenerate/validation read from.
            const { exitOnOpposite, customExits, ...riskManagement } = v
            updateConfig({
              exitConditions: { exitOnOpposite, customExits },
              riskManagement,
            })
          }}
          error={errors.riskManagement}
        />

        <StrategyPreview config={previewConfig} />

        <div className="strategy-builder__actions">
          <GenerationState
            status={generationStatus}
            error={generationError}
            onRetry={handleRetry}
            onViewStrategy={handleViewStrategy}
            onRunBacktest={handleRunBacktest}
            strategy={generatedStrategy}
          />

          {generationStatus === 'idle' && (
            <button
              type="button"
              className="btn btn--primary btn--lg strategy-builder__generate-btn"
              onClick={handleGenerate}
              disabled={hasErrors}
            >
              ✨ GENERATE STRATEGY
            </button>
          )}
        </div>
      </form>
    </div>
  )
}