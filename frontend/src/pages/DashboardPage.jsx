import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart2,
  Brain,
  CheckCircle2,
  Clock,
  ExternalLink,
  Info,
  LineChart,
  Loader2,
  Newspaper,
  PieChart,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import {
  fetchAIBriefing,
  fetchMarketNews,
  fetchMarketOverview,
  fetchMarketPulse,
} from '../lib/api.js'
import {
  formatSignedMoney,
  formatSignedPercent,
} from '../lib/format.js'
import Note from '../components/Note.jsx'
import LiveAlgoChart from '../components/LiveAlgoChart.jsx'

const ICON_SIZE = 16

// Only these three indices appear in the overview.
const OVERVIEW_INDICES = ['NIFTY50', 'BANKNIFTY', 'SENSEX']

const INDEX_META = {
  NIFTY50: { name: 'NIFTY 50', description: 'NSE benchmark' },
  BANKNIFTY: { name: 'BANK NIFTY', description: 'Banking sector' },
  SENSEX: { name: 'SENSEX', description: 'BSE benchmark' },
}

const NEWS_LIMIT = 7

/* ------------------------------------------------------------------ helpers */

function formatIst(unixSeconds, { dateOnly = false } = {}) {
  if (!unixSeconds) return '—'
  const date = new Date(unixSeconds * 1000)
  if (Number.isNaN(date.getTime())) return '—'
  if (dateOnly) {
    return date.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    })
  }
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

function formatIstIso(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatCompactVolume(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const number = Number(value)
  if (number >= 1e7) return `${(number / 1e7).toFixed(2)} Cr`
  if (number >= 1e5) return `${(number / 1e5).toFixed(2)} L`
  if (number >= 1e3) return `${(number / 1e3).toFixed(1)} K`
  return number.toLocaleString('en-IN')
}

function dataStatusLabel(status) {
  switch (status) {
    case 'LIVE':
      return 'LIVE'
    case 'DELAYED':
      return 'DELAYED'
    case 'PRE_OPEN':
      return 'PRE-OPEN'
    case 'HISTORICAL':
      return 'HISTORICAL'
    case 'STALE':
      return 'STALE'
    default:
      return 'UNAVAILABLE'
  }
}

function dataStatusTone(status) {
  switch (status) {
    case 'LIVE':
      return 'live'
    case 'DELAYED':
    case 'PRE_OPEN':
      return 'delayed'
    case 'HISTORICAL':
      return 'historical'
    case 'STALE':
      return 'stale'
    default:
      return 'unavailable'
  }
}

function marketTone(status) {
  if (status === 'OPEN') return 'open'
  if (status === 'PRE-OPEN') return 'pre-open'
  return 'closed'
}

function sentimentTone(sentiment) {
  switch (sentiment) {
    case 'Bullish':
      return 'positive'
    case 'Bearish':
      return 'negative'
    case 'Mixed':
      return 'mixed'
    case 'Sideways':
      return 'neutral'
    default:
      return 'insufficient'
  }
}

function signedPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return formatSignedPercent(Number(value))
}

/* ============================================================ MARKET OVERVIEW */

function IndexCard({ symbol, index, isSelected, onSelect }) {
  const meta = INDEX_META[symbol] ?? { name: symbol, description: 'Index' }
  const unavailable = !index || index.status === 'unavailable' || index.price == null
  const tone = dataStatusTone(index?.data_status ?? (unavailable ? 'UNAVAILABLE' : 'HISTORICAL'))
  const isUp = Number(index?.change_pct ?? 0) >= 0

  return (
    <button
      type="button"
      className={`index-card${isSelected ? ' index-card--selected' : ''}${
        unavailable ? ' index-card--error' : ''
      }`}
      onClick={() => onSelect(symbol)}
      aria-pressed={isSelected}
      title={index?.error || `${meta.name} quote`}
    >
      <div className="index-card__top">
        <span className="index-card__name">{meta.name}</span>
        <span className={`index-card__status-badge ${tone}`}>{dataStatusLabel(index?.data_status)}</span>
      </div>

      <div className="index-card__symbol-row">
        <span className="index-card__symbol">{symbol}</span>
        <span className="index-card__source">{index?.source || 'yfinance'}</span>
      </div>

      {unavailable ? (
        <>
          <div className="index-card__price">
            <span className="index-card__error">Data unavailable</span>
          </div>
          <p className="index-card__error-note">
            {index?.error || 'The provider returned no usable quote for this index.'}
          </p>
        </>
      ) : (
        <>
          <div className="index-card__price">₹{formatPrice(index.price)}</div>
          <div className="index-card__change-row">
            <span className={`index-card__change ${isUp ? 'is-up' : 'is-down'}`}>
              {isUp ? '+' : ''}
              {formatPrice(index.change)}
            </span>
            <span className={`index-card__pct ${isUp ? 'is-up' : 'is-down'}`}>
              {signedPercent(index.change_pct)}
            </span>
          </div>
          <div className="index-card__footer">
            <span>
              <Clock size={12} /> {formatIst(index.timestamp)} IST
            </span>
            {isSelected ? (
              <span className="index-card__selected">
                <CheckCircle2 size={12} /> Viewing
              </span>
            ) : (
              <span className="index-card__hint">Click to view chart</span>
            )}
          </div>
        </>
      )}
    </button>
  )
}

function MarketOverview({ data, loading, error, selectedIndex, onSelect, onRetry }) {
  const marketStatus = data?.market_status
  const indices = data?.indices ?? []
  const bySymbol = useMemo(() => {
    const map = {}
    indices.forEach((index) => {
      map[index.symbol] = index
    })
    return map
  }, [indices])

  return (
    <section className="panel dashboard-section" aria-labelledby="market-overview">
      <div className="panel__head">
        <div>
          <h2 className="section-title" id="market-overview">
            Indian Market Overview
          </h2>
          <p className="section-subtitle">
            Three headline indices · click a card to load its chart
          </p>
        </div>
        <div className="market-overview__status">
          <span className={`market-status-badge ${marketTone(marketStatus?.status)}`}>
            <span className="market-status-badge__dot" aria-hidden="true" />
            {marketStatus?.status ?? 'UNKNOWN'}
          </span>
          <span className="market-overview__status-note">
            {marketStatus?.reason || 'Session status unavailable'}
          </span>
        </div>
      </div>

      {loading && !data ? (
        <div className="index-grid-horizontal">
          {OVERVIEW_INDICES.map((symbol) => (
            <div key={symbol} className="index-card index-card--skeleton" aria-hidden="true">
              <div className="skeleton skeleton--line" />
              <div className="skeleton skeleton--line skeleton--line-lg" />
              <div className="skeleton skeleton--line" />
            </div>
          ))}
        </div>
      ) : (
        <div className="index-grid-horizontal">
          {OVERVIEW_INDICES.map((symbol) => (
            <IndexCard
              key={symbol}
              symbol={symbol}
              index={bySymbol[symbol]}
              isSelected={selectedIndex === symbol}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}

      <div className="market-overview__footer">
        <span>
          Source: Yahoo Finance via yfinance · Updated {formatIst(data?.timestamp)} IST
        </span>
        {marketStatus?.next_open_label && marketStatus?.status !== 'OPEN' && (
          <span>Next session: {marketStatus.next_open_label}</span>
        )}
        <button type="button" className="btn btn--sm btn--ghost" onClick={onRetry}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {error && (
        <Note tone="warning" title="Some index data could not be refreshed">
          <span>{error}. The cards above show the last values returned by the provider.</span>
        </Note>
      )}
    </section>
  )
}

/* ============================================================= MARKET LIVE VIEW */

function MarketLiveView({ selectedIndex, quote, marketStatus }) {
  const meta = INDEX_META[selectedIndex] ?? { name: selectedIndex }
  const status = quote?.data_status ?? (quote?.status === 'unavailable' ? 'UNAVAILABLE' : null)

  return (
    <section className="panel dashboard-section" aria-labelledby="market-live">
      <div className="panel__head">
        <div>
          <h2 className="section-title" id="market-live">
            Market Live View
          </h2>
          <p className="section-subtitle">
            {meta.name} candles · EMA 9/21/50/200 · Volume · RSI · MACD
          </p>
        </div>
        <div className="market-live__meta">
          <span className={`lc-badge lc-badge--${dataStatusTone(status)}`}>
            {dataStatusLabel(status)}
          </span>
          <span className="disclaimer-text">{selectedIndex}</span>
        </div>
      </div>

      <LiveAlgoChart symbol={selectedIndex} quote={quote} marketStatus={marketStatus} />
    </section>
  )
}

/* ================================================================ MARKET PULSE */

function MoverList({ title, icon, items, variant, emptyMessage, tone }) {
  const visible = (items ?? []).slice(0, 5)

  return (
    <div className="pulse-card pulse-card--list">
      <div className="pulse-card__head">
        <h3 className="pulse-card__title">
          <span className={`pulse-card__icon ${tone}`}>{icon}</span>
          {title}
        </h3>
        <span className="pulse-card__count">{visible.length ? `Top ${visible.length}` : '—'}</span>
      </div>

      {visible.length ? (
        <div className="pulse-movers">
          {visible.map((item, index) => {
            const positive = Number(item.change_pct) >= 0
            return (
              <div className="pulse-mover" key={`${item.symbol}-${index}`}>
                <span className="pulse-mover__rank">{index + 1}</span>
                <span className="pulse-mover__identity">
                  <span className="pulse-mover__name">{item.name}</span>
                  <span className="pulse-mover__symbol">{item.symbol}</span>
                </span>
                <span className="pulse-mover__price">₹{formatPrice(item.price)}</span>
                {variant === 'active' ? (
                  <>
                    <span className="pulse-mover__volume">
                      {formatCompactVolume(item.volume)}
                      <em>vol</em>
                    </span>
                    <span className={`pulse-mover__change ${positive ? 'is-up' : 'is-down'}`}>
                      {positive ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                      {signedPercent(item.change_pct)}
                    </span>
                  </>
                ) : (
                  <span className={`pulse-mover__change ${positive ? 'is-up' : 'is-down'}`}>
                    <span>{formatSignedMoney(item.change)}</span>
                    <em>{signedPercent(item.change_pct)}</em>
                  </span>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <p className="pulse-empty">{emptyMessage}</p>
      )}
    </div>
  )
}

function SectorHeatmap({ sectors }) {
  return (
    <div className="pulse-card pulse-card--sectors">
      <div className="pulse-card__head">
        <h3 className="pulse-card__title">
          <span className="pulse-card__icon"><PieChart size={ICON_SIZE} /></span>
          Sector Performance
        </h3>
        <span className="pulse-card__count">NSE sector indices</span>
      </div>

      <div className="pulse-sector-grid">
        {(sectors ?? []).map((sector) => {
          const unavailable =
            sector.status === 'unavailable' || sector.change_pct === null || sector.change_pct === undefined
          const change = Number(sector.change_pct ?? 0)
          const tone = unavailable ? 'unavailable' : change > 0.25 ? 'positive' : change < -0.25 ? 'negative' : 'neutral'
          return (
            <div className={`pulse-sector-tile is-${tone}`} key={sector.sector}>
              <span className="pulse-sector-tile__name">{sector.sector}</span>
              <span className="pulse-sector-tile__change">
                {unavailable ? 'Data unavailable' : signedPercent(change)}
              </span>
            </div>
          )
        })}
        {!sectors?.length && (
          <p className="pulse-empty pulse-empty--wide">
            Sector data is unavailable from the provider.
          </p>
        )}
      </div>
    </div>
  )
}

function MarketBreadth({ breadth }) {
  const advancing = Number(breadth?.advancing ?? 0)
  const declining = Number(breadth?.declining ?? 0)
  const unchanged = Number(breadth?.unchanged ?? 0)
  const total = Number(breadth?.total ?? 0)
  const available = breadth?.status === 'ok' && total > 0

  const advPct = total ? (advancing / total) * 100 : 0
  const decPct = total ? (declining / total) * 100 : 0
  const unchPct = total ? Math.max(0, 100 - advPct - decPct) : 0

  return (
    <div className="pulse-card pulse-card--breadth">
      <div className="pulse-card__head">
        <h3 className="pulse-card__title">
          <span className="pulse-card__icon"><BarChart2 size={ICON_SIZE} /></span>
          Market Breadth
        </h3>
        <span className="pulse-card__count">
          {available ? `${total} stocks` : 'Unavailable'}
        </span>
      </div>

      {available ? (
        <>
          <div className="breadth-stats">
            <div className="breadth-stat is-up">
              <span className="breadth-stat__value">{advancing}</span>
              <span className="breadth-stat__label">Advancing</span>
            </div>
            <div className="breadth-stat is-down">
              <span className="breadth-stat__value">{declining}</span>
              <span className="breadth-stat__label">Declining</span>
            </div>
            <div className="breadth-stat">
              <span className="breadth-stat__value">{unchanged}</span>
              <span className="breadth-stat__label">Unchanged</span>
            </div>
            <div className="breadth-stat">
              <span className="breadth-stat__value">
                {breadth.advance_decline_ratio_display ?? '—'}
              </span>
              <span className="breadth-stat__label">A/D ratio</span>
            </div>
          </div>

          <div
            className="breadth-bar"
            role="img"
            aria-label={`${advancing} advancing, ${declining} declining, ${unchanged} unchanged`}
          >
            <span className="breadth-bar__segment is-up" style={{ width: `${advPct}%` }} />
            <span className="breadth-bar__segment is-flat" style={{ width: `${unchPct}%` }} />
            <span className="breadth-bar__segment is-down" style={{ width: `${decPct}%` }} />
          </div>

          <div className="breadth-legend">
            <span className="is-up">Advancing {advPct.toFixed(0)}%</span>
            <span>Unchanged {unchPct.toFixed(0)}%</span>
            <span className="is-down">Declining {decPct.toFixed(0)}%</span>
          </div>
        </>
      ) : (
        <p className="pulse-empty">
          Breadth is unavailable because the provider returned no usable stock closes. This is
          not the same as zero advancing stocks.
        </p>
      )}
    </div>
  )
}

function MarketPulse() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const result = await fetchMarketPulse()
      setData(result)
      setError(null)
    } catch (err) {
      setError(err.message || 'Failed to load market pulse data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 60000)
    return () => window.clearInterval(timer)
  }, [load])

  const providerUnavailable = data?.status === 'unavailable' || (data && !data.universe_size)

  return (
    <section className="panel dashboard-section" aria-labelledby="market-pulse">
      <div className="panel__head">
        <div>
          <h2 className="section-title" id="market-pulse">
            Market Pulse
          </h2>
          <p className="section-subtitle">
            Movers, sector performance and breadth from a documented NSE universe
          </p>
        </div>
        <div className="market-live__meta">
          <span className="disclaimer-text">Updated {formatIst(data?.timestamp)} IST</span>
          <button type="button" className="btn btn--sm btn--ghost" onClick={load} disabled={loading}>
            {loading ? <Loader2 size={14} className="spinner" /> : <RefreshCw size={14} />}
            Refresh
          </button>
        </div>
      </div>

      {loading && !data ? (
        <div className="pulse-layout">
          <div className="pulse-movers-grid">
            {[0, 1, 2].map((key) => (
              <div key={key} className="pulse-card">
                <div className="skeleton skeleton--line" />
                <div className="skeleton skeleton--line" />
                <div className="skeleton skeleton--line" />
                <div className="skeleton skeleton--line" />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <>
          {providerUnavailable && (
            <Note tone="warning" title="Market Pulse data unavailable">
              <span>
                The market-data provider returned no usable movers or breadth data. No zeros are
                substituted. This can happen when Yahoo Finance is rate-limited or when a session
                has no completed rows yet.
              </span>
            </Note>
          )}

          <div className="pulse-layout">
            <div className="pulse-movers-grid">
              <MoverList
                title="Top Gainers"
                tone="is-up"
                icon={<TrendingUp size={ICON_SIZE} />}
                items={data?.gainers}
                emptyMessage={
                  providerUnavailable
                    ? 'Mover data unavailable from the provider.'
                    : 'No stock in the tracked universe is trading above its previous close.'
                }
              />
              <MoverList
                title="Top Losers"
                tone="is-down"
                icon={<TrendingDown size={ICON_SIZE} />}
                items={data?.losers}
                emptyMessage={
                  providerUnavailable
                    ? 'Mover data unavailable from the provider.'
                    : 'No stock in the tracked universe is trading below its previous close.'
                }
              />
              <MoverList
                title="Most Active"
                tone="is-accent"
                icon={<Activity size={ICON_SIZE} />}
                items={data?.most_active}
                variant="active"
                emptyMessage={
                  providerUnavailable
                    ? 'Volume data unavailable from the provider.'
                    : 'No traded volume was returned for the tracked universe.'
                }
              />
            </div>

            <div className="pulse-lower">
              <SectorHeatmap sectors={data?.sectors} />
              <MarketBreadth breadth={data?.breadth} />
            </div>
          </div>

          <div className="market-overview__footer">
            <span>
              Source: Yahoo Finance via yfinance · {data?.universe_size ?? 0} tracked stocks ·
              Updated {formatIst(data?.timestamp)} IST
            </span>
          </div>
        </>
      )}

      {error && (
        <Note tone="danger" title="Market Pulse request failed">
          <span>{error}</span>
        </Note>
      )}
    </section>
  )
}

/* ================================================================= AI BRIEFING */

function SectorChip({ item }) {
  const positive = Number(item?.change_pct) >= 0
  return (
    <span className={`ai-sector-chip ${positive ? 'is-up' : 'is-down'}`}>
      {item?.sector}
      <em>{signedPercent(item?.change_pct)}</em>
    </span>
  )
}

function AIMarketBriefing() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeMode, setActiveMode] = useState('concise')

  const generate = useCallback(async (mode = 'concise', { force = false } = {}) => {
    setLoading(true)
    setActiveMode(mode)
    setError(null)
    try {
      const result = await fetchAIBriefing({ mode, force })
      setData(result)
    } catch (err) {
      setError(err.message || 'The AI briefing could not be generated.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    generate('concise')
  }, [generate])

  const briefing =
    data?.briefing && typeof data.briefing === 'object' ? data.briefing : null
  const legacyText = typeof data?.briefing === 'string' ? data.briefing : null
  const sentiment = briefing?.sentiment ?? 'Insufficient Data'
  const generatedBy = data?.generated_by === 'llm' ? 'AI generated' : 'Rule-based summary'

  return (
    <section className="panel dashboard-section" aria-labelledby="ai-briefing">
      <div className="panel__head">
        <div>
          <h2 className="section-title" id="ai-briefing">
            <Brain className="section-title__icon" size={ICON_SIZE} />
            AI Market Briefing
          </h2>
          <p className="section-subtitle">
            Facts first, interpretation second · not a trading signal
          </p>
        </div>
        <div className="ai-brief__head-actions">
          <button
            type="button"
            className="btn btn--sm btn--ghost"
            onClick={() => generate(activeMode, { force: true })}
            disabled={loading}
          >
            {loading && activeMode === 'concise' ? (
              <Loader2 size={14} className="spinner" />
            ) : (
              <RefreshCw size={14} />
            )}
            Refresh Analysis
          </button>
          <button
            type="button"
            className="btn btn--sm btn--outline"
            onClick={() => generate('explain')}
            disabled={loading}
          >
            {loading && activeMode === 'explain' ? (
              <Loader2 size={14} className="spinner" />
            ) : (
              <Sparkles size={14} />
            )}
            Explain Market Movement
          </button>
          <button
            type="button"
            className="btn btn--sm btn--outline"
            onClick={() => generate('detailed')}
            disabled={loading}
          >
            {loading && activeMode === 'detailed' ? (
              <Loader2 size={14} className="spinner" />
            ) : (
              <LineChart size={14} />
            )}
            View Detailed Analysis
          </button>
        </div>
      </div>

      {loading && !data && (
        <div className="briefing-loading">
          <Loader2 size={22} className="spinner" />
          <span>Collecting index, sector, breadth and VIX facts…</span>
        </div>
      )}

      {error && (
        <Note tone="danger" title="AI briefing unavailable">
          <span>{error}</span>
        </Note>
      )}

      {data && (
        <div className={`ai-brief${loading ? ' is-refreshing' : ''}`}>
          <div className="ai-brief__top">
            <div className="ai-brief__sentiment">
              <span className="ai-brief__eyebrow">Overall sentiment</span>
              <span className={`ai-sentiment ai-sentiment--${sentimentTone(sentiment)}`}>
                {sentiment}
              </span>
            </div>
            <div className="ai-brief__meta">
              <span className={`ai-source-badge ${data.generated_by === 'llm' ? 'is-ai' : 'is-rules'}`}>
                {generatedBy}
              </span>
              <span>Mode: {data.mode ?? activeMode}</span>
              <span>Generated {formatIstIso(data.timestamp_ist ?? data.timestamp)} IST</span>
              {data.cached && <span className="ai-cached">Cached</span>}
            </div>
          </div>

          <div className="ai-brief__direction">
            <h3 className="ai-block__title">
              <Target size={14} /> Market direction
            </h3>
            <p>{briefing?.market_direction ?? legacyText ?? 'No market direction was returned.'}</p>
          </div>

          <div className="ai-brief__grid">
            <div className="ai-block">
              <h3 className="ai-block__title">
                <PieChart size={14} /> Sector analysis
              </h3>
              {briefing?.sector_analysis?.strong?.length ||
              briefing?.sector_analysis?.weak?.length ? (
                <>
                  <div className="ai-sector-group">
                    <span className="ai-sector-group__label">Strong</span>
                    <div className="ai-sector-chips">
                      {(briefing.sector_analysis.strong ?? []).map((item) => (
                        <SectorChip key={`strong-${item.sector}`} item={item} />
                      ))}
                      {!briefing.sector_analysis.strong?.length && <em>None reported</em>}
                    </div>
                  </div>
                  <div className="ai-sector-group">
                    <span className="ai-sector-group__label">Weak</span>
                    <div className="ai-sector-chips">
                      {(briefing.sector_analysis.weak ?? []).map((item) => (
                        <SectorChip key={`weak-${item.sector}`} item={item} />
                      ))}
                      {!briefing.sector_analysis.weak?.length && <em>None reported</em>}
                    </div>
                  </div>
                  {briefing.sector_analysis.unusual?.length > 0 && (
                    <ul className="ai-mini-list">
                      {briefing.sector_analysis.unusual.map((item, index) => (
                        <li key={`unusual-${index}`}>{item}</li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <p className="ai-muted">Sector data is unavailable for this briefing.</p>
              )}
            </div>

            <div className="ai-block">
              <h3 className="ai-block__title">
                <Activity size={14} /> Volatility analysis
              </h3>
              <p>
                {briefing?.volatility_analysis ??
                  'Volatility analysis was not returned by the AI provider.'}
              </p>
              {briefing?.volatility_level && (
                <span className="ai-vol-level">
                  INDIA VIX level: <strong>{briefing.volatility_level}</strong>
                </span>
              )}
            </div>
          </div>

          <div className="ai-brief__grid ai-brief__grid--lists">
            <div className="ai-block">
              <h3 className="ai-block__title">
                <CheckCircle2 size={14} /> Important observations
              </h3>
              {briefing?.observations?.length ? (
                <ol className="ai-list">
                  {briefing.observations.map((item, index) => (
                    <li key={`observation-${index}`}>{item}</li>
                  ))}
                </ol>
              ) : (
                <p className="ai-muted">No observations were returned.</p>
              )}
            </div>

            <div className="ai-block ai-block--risk">
              <h3 className="ai-block__title">
                <ShieldAlert size={14} /> Risk alerts
              </h3>
              {briefing?.risk_alerts?.length ? (
                <ul className="ai-list ai-list--risk">
                  {briefing.risk_alerts.map((item, index) => (
                    <li key={`risk-${index}`}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="ai-muted">
                  No additional risk alerts were reported from the available facts.
                </p>
              )}
            </div>
          </div>

          <div className="ai-brief__interpretation">
            <h3 className="ai-block__title">
              <Brain size={14} /> AI interpretation
            </h3>
            <p>
              {briefing?.interpretation ??
                legacyText ??
                'No interpretation was returned. Review the factual observations above.'}
            </p>
            <p className="ai-brief__disclaimer">
              <Info size={13} /> {data.disclaimer}
            </p>
          </div>

          {data.note && (
            <Note tone="info" title="About this briefing">
              <span>{data.note}</span>
            </Note>
          )}

          <div className="ai-brief__footer">
            <span>
              Sources: {(data.data_sources ?? []).join(' · ') || 'Unavailable'}
            </span>
            <span>
              Facts as of {formatIstIso(data.timestamp_ist ?? data.timestamp)} IST
            </span>
            {data.market_status?.status && <span>Market: {data.market_status.status}</span>}
          </div>
        </div>
      )}
    </section>
  )
}

/* ================================================================ MARKET NEWS */

function NewsCard({ item }) {
  const hasUrl = Boolean(item.url)
  return (
    <article className="news-card">
      <div className="news-card__meta">
        <span className="news-card__source">{item.source || 'Unknown source'}</span>
        <span className="news-card__dot" aria-hidden="true">·</span>
        <span>
          <Clock size={11} /> {formatIst(item.published_at)} IST
        </span>
      </div>

      <h3 className="news-card__headline">
        {hasUrl ? (
          <a href={item.url} target="_blank" rel="noreferrer noopener">
            {item.title}
          </a>
        ) : (
          item.title
        )}
      </h3>

      {item.summary ? (
        <p className="news-card__summary">{item.summary}</p>
      ) : (
        <p className="news-card__summary news-card__summary--unavailable">
          Summary not provided by the source.
        </p>
      )}

      <div className="news-card__footer">
        <div className="news-card__tags">
          {(item.related_symbols ?? []).slice(0, 3).map((symbol) => (
            <span key={symbol} className="news-card__tag">
              {symbol.replace('.NS', '').replace('^', '')}
            </span>
          ))}
          {(item.related_sectors ?? []).slice(0, 2).map((sector) => (
            <span key={sector} className="news-card__tag news-card__tag--sector">
              {sector}
            </span>
          ))}
          {!item.related_symbols?.length && !item.related_sectors?.length && (
            <span className="news-card__tag">Market news</span>
          )}
        </div>
        {hasUrl && (
          <a
            className="news-card__link"
            href={item.url}
            target="_blank"
            rel="noreferrer noopener"
          >
            Read More <ExternalLink size={12} />
          </a>
        )}
      </div>
    </article>
  )
}

function MarketNewsSection() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchMarketNews({ limit: 20 })
      setData(result)
    } catch (err) {
      setError(err.message || 'News could not be fetched.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const news = (data?.news ?? []).slice(0, NEWS_LIMIT)
  const unavailable = !error && (!data || data.status === 'unavailable' || !news.length)

  return (
    <section className="panel dashboard-section" aria-labelledby="market-news">
      <div className="panel__head">
        <div>
          <h2 className="section-title" id="market-news">
            <Newspaper className="section-title__icon" size={ICON_SIZE} />
            Market News &amp; Events
          </h2>
          <p className="section-subtitle">
            Latest Indian market headlines · publication time shown, not retrieval time
          </p>
        </div>
        <div className="market-live__meta">
          <span className="disclaimer-text">
            {data?.retrieved_at
              ? `Retrieved ${formatIst(data.retrieved_at)} IST`
              : loading
                ? 'Retrieving headlines…'
                : 'Retrieval time unavailable'}
          </span>
          <button type="button" className="btn btn--sm btn--ghost" onClick={load} disabled={loading}>
            {loading ? <Loader2 size={14} className="spinner" /> : <RefreshCw size={14} />}
            Refresh
          </button>
        </div>
      </div>

      {loading && !data && (
        <div className="news-grid">
          {[0, 1, 2, 3].map((key) => (
            <div key={key} className="news-card">
              <div className="skeleton skeleton--line" />
              <div className="skeleton skeleton--line skeleton--line-lg" />
              <div className="skeleton skeleton--line" />
            </div>
          ))}
        </div>
      )}

      {error && (
        <Note tone="danger" title="News request failed">
          <span>{error}. No headlines are generated locally.</span>
        </Note>
      )}

      {unavailable && !error && (
        <Note tone="warning" title="No recent headlines available">
          <span>
            The news provider returned no usable Indian market headlines. This can happen when the
            provider is rate-limited or when no new articles are available. QuantNiti does not
            invent headlines or timestamps.
          </span>
        </Note>
      )}

      {news.length > 0 && (
        <>
          <div className="news-grid">
            {news.map((item, index) => (
              <NewsCard key={`${item.title}-${index}`} item={item} />
            ))}
          </div>
          <p className="news-disclaimer">
            <Info size={13} /> Headlines are aggregated from Yahoo Finance and Google News
            RSS, with a link to the original source. Publication time is when the article was
            published; the section header shows when QuantNiti retrieved the list. Some providers
            restrict full-text access behind the source link.
          </p>
        </>
      )}
    </section>
  )
}

/* ===================================================================== EXPORT */

export default function DashboardPage() {
  const [selectedIndex, setSelectedIndex] = useState('NIFTY50')
  const [overview, setOverview] = useState(null)
  const [overviewLoading, setOverviewLoading] = useState(true)
  const [overviewError, setOverviewError] = useState(null)

  const loadOverview = useCallback(async () => {
    setOverviewLoading(true)
    try {
      const result = await fetchMarketOverview()
      setOverview(result)
      setOverviewError(null)
    } catch (err) {
      setOverviewError(err.message || 'Could not refresh index quotes.')
    } finally {
      setOverviewLoading(false)
    }
  }, [])

  useEffect(() => {
    loadOverview()
    const timer = window.setInterval(loadOverview, 60000)
    return () => window.clearInterval(timer)
  }, [loadOverview])

  const marketStatus = overview?.market_status ?? null
  const selectedQuote = useMemo(() => {
    return overview?.indices?.find((index) => index.symbol === selectedIndex) ?? null
  }, [overview, selectedIndex])

  return (
    <div className="page dashboard-page dashboard-page--centered">
      <div className="dashboard-container">
        <MarketOverview
          data={overview}
          loading={overviewLoading}
          error={overviewError}
          selectedIndex={selectedIndex}
          onSelect={setSelectedIndex}
          onRetry={loadOverview}
        />

        <MarketLiveView
          selectedIndex={selectedIndex}
          quote={selectedQuote}
          marketStatus={marketStatus}
        />

        <MarketPulse />

        <AIMarketBriefing />

        <MarketNewsSection />
      </div>
    </div>
  )
}
