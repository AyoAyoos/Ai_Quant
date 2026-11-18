import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { formatDate, formatMoney, formatSignedMoney } from '../lib/format.js'

const PAD = { top: 28, right: 72, bottom: 48, left: 72 }
const MIN_CANDLE_WIDTH = 4
const MAX_CANDLE_WIDTH = 18
const CANDLE_SPACING_RATIO = 0.3
const TOOLBAR_HEIGHT = 36

function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function cleanBar(entry) {
  if (!entry || typeof entry !== 'object') return null
  const open = num(entry.open)
  const high = num(entry.high)
  const low = num(entry.low)
  const close = num(entry.close)
  const volume = num(entry.volume)
  if (open === null || high === null || low === null || close === null) return null
  return { date: typeof entry.date === 'string' ? entry.date : '', open, high, low, close, volume }
}

function formatVolume(v) {
  if (v === null || v === undefined) return ''
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`
  return String(v)
}

function formatINR(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return `₹${formatMoney(value)}`
}

function catmullRomToBezier(points, tension = 0.5) {
  if (points.length < 2) return ''
  if (points.length === 2) {
    return `M${points[0].x},${points[0].y} L${points[1].x},${points[1].y}`
  }
  let path = `M${points[0].x},${points[0].y}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i > 0 ? i - 1 : 0]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2 < points.length ? i + 2 : points.length - 1]
    const cp1x = p1.x + (p2.x - p0.x) * tension / 6
    const cp1y = p1.y + (p2.y - p0.y) * tension / 6
    const cp2x = p2.x - (p3.x - p1.x) * tension / 6
    const cp2y = p2.y - (p3.y - p1.y) * tension / 6
    path += ` C${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`
  }
  return path
}

export default function PaperTradeChart({
  bars,
  markers,
  mode = 'candle',
  title,
  showVolume = false,
  showLastPriceLine = true,
  isEquityChart = false,
  watermarkDate = null,
  startingCapital = null,
}) {
  const chartTitle = title ?? (isEquityChart ? 'PORTFOLIO EQUITY — HISTORICAL' : mode === 'line' ? 'NIFTY 50 — HISTORICAL PRICE' : 'NIFTY 50 — HISTORICAL OHLC')
  const [hover, setHover] = useState(null)
  const [viewStart, setViewStart] = useState(0)
  const [viewSize, setViewSize] = useState(null)
  const [svgRect, setSvgRect] = useState(null)
  const svgRef = useRef(null)
  const containerRef = useRef(null)

  const cleanBars = useMemo(
    () => (Array.isArray(bars) ? bars.map(cleanBar).filter(Boolean) : []),
    [bars],
  )

  const markerByIndex = useMemo(() => {
    if (!markers || !markers.length) return new Map()
    const byDate = new Map()
    for (const marker of markers) {
      if (!marker || (marker.side !== 'BUY' && marker.side !== 'SELL')) continue
      if (typeof marker.bar_date !== 'string' || !marker.bar_date) continue
      if (!byDate.has(marker.bar_date)) byDate.set(marker.bar_date, [])
      byDate.get(marker.bar_date).push(marker)
    }
    const indexMap = new Map()
    cleanBars.forEach((bar, i) => {
      if (byDate.has(bar.date)) indexMap.set(i, byDate.get(bar.date))
    })
    return indexMap
  }, [cleanBars, markers])

  const markerDates = useMemo(() => {
    if (!markers || !markers.length) return new Set()
    const dates = new Set()
    for (const marker of markers) {
      if (marker?.bar_date) dates.add(marker.bar_date)
    }
    return dates
  }, [markers])

  useEffect(() => {
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    setSvgRect({ width: rect.width, height: rect.height })
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setSvgRect({ width, height })
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  const geometry = useMemo(() => {
    if (cleanBars.length === 0 || !svgRect) return null

    const W = svgRect.width
    const H = svgRect.height - TOOLBAR_HEIGHT
    const PLOT_W = W - PAD.left - PAD.right
    const PLOT_H = H - PAD.top - PAD.bottom

    if (PLOT_W <= 0 || PLOT_H <= 0) return null

    const visibleBars = viewSize ? cleanBars.slice(viewStart, viewStart + viewSize) : cleanBars
    if (visibleBars.length === 0) return null

    const values = isEquityChart
      ? visibleBars.map(b => b.close)
      : visibleBars.flatMap(b => [b.low, b.high])

    const rawMin = Math.min(...values)
    const rawMax = Math.max(...values)
    const span0 = rawMax - rawMin || Math.max(Math.abs(rawMax) * 0.02, 1)
    const headroom = isEquityChart ? span0 * 0.1 : span0 * 0.14
    const min = rawMin - headroom
    const max = rawMax + headroom
    const span = max - min || 1

    const step = PLOT_W / visibleBars.length
    const candleWidth = Math.max(MIN_CANDLE_WIDTH, Math.min(MAX_CANDLE_WIDTH, step * (1 - CANDLE_SPACING_RATIO)))
    const xFor = (i) => PAD.left + step * i + step * 0.5
    const yFor = (v) => PAD.top + (1 - (v - min) / span) * PLOT_H

    const priceLevels = []
    const ticks = 5
    for (let i = 0; i <= ticks; i++) {
      priceLevels.push(min + (span * i) / ticks)
    }

    const dateIndices = []
    const maxLabels = 8
    for (let i = 0; i < Math.min(maxLabels, visibleBars.length); i++) {
      dateIndices.push(Math.floor((visibleBars.length - 1) * i / (maxLabels - 1)))
    }
    if (visibleBars.length > 1 && dateIndices[dateIndices.length - 1] !== visibleBars.length - 1) {
      dateIndices.push(visibleBars.length - 1)
    }

    return {
      W,
      H,
      PLOT_W,
      PLOT_H,
      step,
      candleWidth,
      xFor,
      yFor,
      min,
      max,
      span,
      priceLevels,
      dateIndices,
      visibleCount: visibleBars.length,
      visibleBars,
      containerWidth: W,
      containerHeight: H + TOOLBAR_HEIGHT,
    }
  }, [cleanBars, viewStart, viewSize, svgRect, isEquityChart])

  const lineData = useMemo(() => {
    if (!geometry || geometry.visibleBars.length === 0) return null
    const points = geometry.visibleBars.map((bar, i) => ({
      x: geometry.xFor(i),
      y: geometry.yFor(bar.close),
    }))
    const linePath = isEquityChart
      ? catmullRomToBezier(points, 0.5)
      : points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
    const areaPath = `${linePath} L ${points[points.length - 1].x},${PAD.top + geometry.PLOT_H} L ${points[0].x},${PAD.top + geometry.PLOT_H} Z`
    return { linePath, areaPath, points }
  }, [geometry, isEquityChart])

  const indexFromClientX = useCallback(
    (clientX) => {
      const svg = svgRef.current
      if (!svg || !geometry) return null
      const rect = svg.getBoundingClientRect()
      if (rect.width === 0) return null
      const viewBoxX = ((clientX - rect.left) / rect.width) * geometry.W
      const raw = Math.floor((viewBoxX - PAD.left) / geometry.step)
      return Math.min(Math.max(raw, 0), geometry.visibleCount - 1)
    },
    [geometry],
  )

  const handleWheel = useCallback((e) => {
    if (!e.ctrlKey && !e.metaKey) return
    e.preventDefault()
    if (!geometry) return
    const newSize = Math.max(2, Math.min(geometry.visibleCount, Math.round(geometry.visibleCount * (e.deltaY > 0 ? 1.2 : 0.83))))
    const center = viewStart + geometry.visibleCount / 2
    const newStart = Math.max(0, Math.min(center - newSize / 2, geometry.visibleCount - newSize))
    setViewSize(newSize)
    setViewStart(newStart)
  }, [geometry, viewStart])

  const resetView = useCallback(() => {
    setViewSize(null)
    setViewStart(0)
  }, [])

  const zoomIn = useCallback(() => {
    if (!geometry) return
    const newSize = Math.max(2, Math.floor(geometry.visibleCount * 0.7))
    const center = viewStart + geometry.visibleCount / 2
    const newStart = Math.max(0, Math.min(center - newSize / 2, geometry.visibleCount - newSize))
    setViewSize(newSize)
    setViewStart(newStart)
  }, [geometry, viewStart])

  const zoomOut = useCallback(() => {
    if (!geometry) return
    const newSize = Math.min(cleanBars.length, Math.ceil(geometry.visibleCount * 1.4))
    const center = viewStart + geometry.visibleCount / 2
    const newStart = Math.max(0, Math.min(center - newSize / 2, geometry.visibleCount - newSize))
    setViewSize(newSize)
    setViewStart(newStart)
  }, [geometry, viewStart, cleanBars.length])

  const panLeft = useCallback(() => {
    const step = Math.max(1, Math.floor((viewSize || cleanBars.length) * 0.2))
    setViewStart(Math.max(0, viewStart - step))
  }, [viewStart, viewSize, cleanBars.length])

  const panRight = useCallback(() => {
    const maxStart = cleanBars.length - (viewSize || cleanBars.length)
    const step = Math.max(1, Math.floor((viewSize || cleanBars.length) * 0.2))
    setViewStart(Math.min(maxStart, viewStart + step))
  }, [viewStart, viewSize, cleanBars.length])

  if (!geometry) {
    return (
      <div className="tv-chart" ref={containerRef} style={{ width: '100%', height: '100%', minHeight: '380px', aspectRatio: '16 / 9' }}>
        <div className="tv-chart__empty">No data available</div>
      </div>
    )
  }

  const active = hover !== null && hover >= 0 && hover < geometry.visibleCount ? hover : null
  const activeBar = active === null ? null : geometry.visibleBars[active]
  const activeMarkers = active === null ? [] : (markerByIndex.get(active + viewStart) ?? [])
  const lastBar = geometry.visibleBars[geometry.visibleBars.length - 1]
  const lastClose = lastBar.close
  const lastDate = lastBar.date

  return (
    <div
      className="tv-chart"
      ref={containerRef}
      onWheel={handleWheel}
      onMouseLeave={() => setHover(null)}
      style={{ width: '100%', height: '100%', minHeight: '380px', aspectRatio: '16 / 9' }}
    >
      <div className="tv-chart__toolbar" role="toolbar" aria-label="Chart controls">
        <div className="tv-chart__toolbar-group">
          {!isEquityChart && (
            <>
              <button type="button" className={`tv-btn ${mode === 'candle' ? 'tv-btn--active' : ''}`} onClick={() => {}} disabled={isEquityChart} title="Candlestick">🕯</button>
              <button type="button" className={`tv-btn ${mode === 'line' ? 'tv-btn--active' : ''}`} onClick={() => {}} disabled={isEquityChart} title="Line">📈</button>
            </>
          )}
          {isEquityChart && <button type="button" className="tv-btn tv-btn--active" disabled title="Area">📊</button>}
        </div>
        <div className="tv-chart__toolbar-divider" />
        <div className="tv-chart__toolbar-group">
          <button type="button" className="tv-btn" onClick={zoomIn} title="Zoom In (Ctrl+Wheel)" aria-label="Zoom In">🔍+</button>
          <button type="button" className="tv-btn" onClick={zoomOut} title="Zoom Out (Ctrl+Wheel)" aria-label="Zoom Out">🔍−</button>
          <button type="button" className="tv-btn" onClick={resetView} title="Reset View" aria-label="Reset View">⟲</button>
        </div>
        <div className="tv-chart__toolbar-divider" />
        <div className="tv-chart__toolbar-group">
          <button type="button" className="tv-btn" onClick={panLeft} title="Pan Left" aria-label="Pan Left">◀</button>
          <button type="button" className="tv-btn" onClick={panRight} title="Pan Right" aria-label="Pan Right">▶</button>
        </div>
        <div className="tv-chart__toolbar-spacer" />
        <div className="tv-chart__last-price" style={{ color: isEquityChart ? '#15803d' : lastClose >= (cleanBars[0]?.close ?? lastClose) ? '#15803d' : '#dc2626' }}>
          {isEquityChart ? 'Equity: ' : 'Last: '}{isEquityChart ? formatINR(lastClose) : formatMoney(lastClose)}
        </div>
      </div>

      <svg
        ref={svgRef}
        className="tv-chart__svg"
        viewBox={`0 0 ${geometry.W} ${geometry.containerHeight}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${chartTitle} chart from ${formatDate(geometry.visibleBars[0]?.date ?? '—')} to ${formatDate(geometry.visibleBars[geometry.visibleBars.length - 1]?.date ?? '—')}${markers?.length ? ' with trade markers' : ''}`}
        tabIndex={0}
        onPointerMove={(event) => setHover(indexFromClientX(event.clientX))}
        onPointerLeave={() => setHover(null)}
        onFocus={() => setHover(geometry.visibleCount - 1)}
        onBlur={() => setHover(null)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
            event.preventDefault()
            const base = hover === null ? geometry.visibleCount - 1 : hover
            const next = event.key === 'ArrowRight' ? base + 1 : base - 1
            setHover(Math.min(Math.max(next, 0), geometry.visibleCount - 1))
          } else if (event.key === 'Escape') {
            setHover(null)
          }
        }}
      >
        <defs>
          <clipPath id="tv-plot-clip">
            <rect x={PAD.left} y={PAD.top} width={geometry.PLOT_W} height={geometry.PLOT_H} />
          </clipPath>
          <linearGradient id="price-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="equity-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#15803d" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#15803d" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        <rect
          x={PAD.left}
          y={PAD.top}
          width={geometry.PLOT_W}
          height={geometry.PLOT_H}
          fill="#fafafa"
        />

        {geometry.priceLevels.map((level) => (
          <line
            key={level}
            className="tv-grid__line tv-grid__line--horizontal"
            x1={PAD.left}
            x2={PAD.left + geometry.PLOT_W}
            y1={geometry.yFor(level)}
            y2={geometry.yFor(level)}
          />
        ))}

        {geometry.dateIndices.map((idx) => {
          const x = geometry.xFor(idx)
          return (
            <g key={`date-${idx}`}>
              <line
                className="tv-grid__line tv-grid__line--vertical"
                x1={x}
                x2={x}
                y1={PAD.top}
                y2={PAD.top + geometry.PLOT_H}
              />
              <text
                className="tv-axis__label tv-axis__label--date"
                x={x}
                y={PAD.top + geometry.PLOT_H + 20}
                textAnchor="middle"
                dominantBaseline="hanging"
              >
                {formatDate(geometry.visibleBars[idx].date)}
              </text>
            </g>
          )
        })}

        {geometry.priceLevels.map((level) => (
          <text
            key={`price-${level}`}
            className="tv-axis__label tv-axis__label--price"
            x={PAD.left + geometry.PLOT_W + 8}
            y={geometry.yFor(level) + 4}
            textAnchor="start"
            dominantBaseline="middle"
          >
            {isEquityChart ? formatINR(level) : formatMoney(level)}
          </text>
        ))}

        {watermarkDate && geometry.visibleBars.some(b => b.date === watermarkDate) && (() => {
          const watermarkIndex = geometry.visibleBars.findIndex(b => b.date === watermarkDate)
          if (watermarkIndex === -1) return null
          const x = geometry.xFor(watermarkIndex)
          return (
            <g key="watermark-line">
              <line
                className="tv-watermark__line"
                x1={x}
                x2={x}
                y1={PAD.top}
                y2={PAD.top + geometry.PLOT_H}
              />
              <text
                className="tv-watermark__label"
                x={x}
                y={PAD.top - 8}
                textAnchor="middle"
                dominantBaseline="baseline"
              >
                Replay Boundary
              </text>
              <rect
                className="tv-watermark__bg"
                x={x - 50}
                y={PAD.top - 22}
                width={100}
                height={18}
                rx={3}
                ry={3}
              />
              <text
                className="tv-watermark__label"
                x={x}
                y={PAD.top - 8}
                textAnchor="middle"
                dominantBaseline="baseline"
              >
                Replay Boundary
              </text>
            </g>
          )
        })()}

        {active !== null && (
          <>
            <line
              className="tv-crosshair tv-crosshair--vertical"
              x1={geometry.xFor(active)}
              x2={geometry.xFor(active)}
              y1={PAD.top}
              y2={PAD.top + geometry.PLOT_H}
            />
            <line
              className="tv-crosshair tv-crosshair--horizontal"
              x1={PAD.left}
              x2={PAD.left + geometry.PLOT_W}
              y1={geometry.yFor(activeBar.close)}
              y2={geometry.yFor(activeBar.close)}
            />
            <text
              className="tv-crosshair__label tv-crosshair__label--price"
              x={PAD.left + geometry.PLOT_W + 8}
              y={geometry.yFor(activeBar.close) + 4}
              textAnchor="start"
              dominantBaseline="middle"
            >
              {isEquityChart ? formatINR(activeBar.close) : formatMoney(activeBar.close)}
            </text>
            <text
              className="tv-crosshair__label tv-crosshair__label--date"
              x={geometry.xFor(active)}
              y={PAD.top + geometry.PLOT_H + 20}
              textAnchor="middle"
              dominantBaseline="hanging"
            >
              {formatDate(activeBar.date)}
            </text>
          </>
        )}

        {showLastPriceLine && !isEquityChart && (
          <line
            className="tv-last-price__line"
            x1={PAD.left}
            x2={PAD.left + geometry.PLOT_W}
            y1={geometry.yFor(lastClose)}
            y2={geometry.yFor(lastClose)}
          />
        )}

        {showLastPriceLine && !isEquityChart && (
          <text
            className="tv-last-price__label"
            x={PAD.left + geometry.PLOT_W + 8}
            y={geometry.yFor(lastClose) + 4}
            textAnchor="start"
            dominantBaseline="middle"
          >
            {formatMoney(lastClose)}
          </text>
        )}

        {isEquityChart && (
          <>
            <line
              className="tv-reference__line"
              x1={PAD.left}
              x2={PAD.left + geometry.PLOT_W}
              y1={geometry.yFor(startingCapital !== null ? startingCapital : geometry.visibleBars[0].close)}
              y2={geometry.yFor(startingCapital !== null ? startingCapital : geometry.visibleBars[0].close)}
            />
            <text
              className="tv-reference__label"
              x={PAD.left + geometry.PLOT_W + 8}
              y={geometry.yFor(startingCapital !== null ? startingCapital : geometry.visibleBars[0].close) + 4}
              textAnchor="start"
              dominantBaseline="middle"
            >
              {formatINR(startingCapital !== null ? startingCapital : geometry.visibleBars[0].close)}
            </text>
            {startingCapital !== null && (
              <text
                className="tv-reference__label tv-reference__label--caption"
                x={PAD.left - 8}
                y={geometry.yFor(startingCapital) - 8}
                textAnchor="end"
                dominantBaseline="baseline"
                style={{ fontSize: 10, fill: '#15803d', fontWeight: 600 }}
              >
                Starting Capital
              </text>
            )}
          </>
        )}

        <g clipPath="url(#tv-plot-clip)">
          {mode === 'line' && lineData ? (
            <>
              <path
                className="tv-series__area"
                d={lineData.areaPath}
                fill={isEquityChart ? 'url(#equity-gradient)' : 'url(#price-gradient)'}
              />
              <path
                className="tv-series__line"
                d={lineData.linePath}
                stroke={isEquityChart ? '#15803d' : '#2563eb'}
                strokeWidth={2}
                fill="none"
              />
              {active !== null && (
                <circle
                  className="tv-series__dot"
                  cx={geometry.xFor(active)}
                  cy={geometry.yFor(activeBar.close)}
                  r={5}
                  fill={isEquityChart ? '#15803d' : '#2563eb'}
                  stroke="#fff"
                  strokeWidth={2}
                />
              )}
            </>
          ) : (
            geometry.visibleBars.map((bar, i) => {
              const up = bar.close >= bar.open
              const x = geometry.xFor(i)
              const yOpen = geometry.yFor(bar.open)
              const yClose = geometry.yFor(bar.close)
              const yHigh = geometry.yFor(bar.high)
              const yLow = geometry.yFor(bar.low)
              const bodyTop = Math.min(yOpen, yClose)
              const bodyHeight = Math.max(1.5, Math.abs(yOpen - yClose))
              const barMarkers = markerByIndex.get(i + viewStart) ?? []
              const hasBuy = barMarkers.some((m) => m.side === 'BUY')
              const hasSell = barMarkers.some((m) => m.side === 'SELL')

              return (
                <g key={`${bar.date}-${i}`} className="tv-candle">
                  <line
                    className={`tv-candle__wick ${up ? 'tv-candle__wick--up' : 'tv-candle__wick--down'}`}
                    x1={x}
                    x2={x}
                    y1={yHigh}
                    y2={yLow}
                  />
                  <rect
                    className={`tv-candle__body ${up ? 'tv-candle__body--up' : 'tv-candle__body--down'}`}
                    x={x - geometry.candleWidth / 2}
                    y={bodyTop}
                    width={geometry.candleWidth}
                    height={bodyHeight}
                    rx={1}
                    ry={1}
                  />
                  {hasBuy && (
                    <polygon
                      className="tv-candle__marker tv-candle__marker--buy"
                      points={`${x},${yLow + 10} ${x - 5},${yLow + 2} ${x + 5},${yLow + 2}`}
                    >
                      <title>Simulated BUY</title>
                    </polygon>
                  )}
                  {hasSell && (
                    <polygon
                      className="tv-candle__marker tv-candle__marker--sell"
                      points={`${x},${yHigh - 10} ${x - 5},${yHigh - 2} ${x + 5},${yHigh - 2}`}
                    >
                      <title>Simulated SELL</title>
                    </polygon>
                  )}
                </g>
              )
            })
          )}
        </g>
      </svg>

      {activeBar && (
        <div
          className="tv-tooltip"
          style={{
            left: `${(geometry.xFor(active) / geometry.W) * 100}%`,
            top: `${(geometry.yFor(activeBar.close) / geometry.containerHeight) * 100}%`,
          }}
        >
          <div className="tv-tooltip__header">
            <span className="tv-tooltip__date">{formatDate(activeBar.date)}</span>
            <span className="tv-tooltip__close">{isEquityChart ? formatINR(activeBar.close) : formatMoney(activeBar.close)}</span>
          </div>
          {!isEquityChart && (
            <div className="tv-tooltip__ohlc">
              <div className="tv-tooltip__row"><span>O</span><span>{formatMoney(activeBar.open)}</span></div>
              <div className="tv-tooltip__row"><span>H</span><span>{formatMoney(activeBar.high)}</span></div>
              <div className="tv-tooltip__row"><span>L</span><span>{formatMoney(activeBar.low)}</span></div>
              <div className="tv-tooltip__row"><span>C</span><span>{formatMoney(activeBar.close)}</span></div>
              {activeBar.volume !== null && activeBar.volume !== undefined && (
                <div className="tv-tooltip__row"><span>Vol</span><span>{formatVolume(activeBar.volume)}</span></div>
              )}
            </div>
          )}
          {isEquityChart && (
            <div className="tv-tooltip__equity">
              <div className="tv-tooltip__row"><span>Equity</span><span>{formatINR(activeBar.close)}</span></div>
            </div>
          )}
          {activeMarkers.map((marker, k) => (
            <div key={k} className={`tv-tooltip__trade tv-tooltip__trade--${marker.side.toLowerCase()}`}>
              <span>SIMULATED {marker.side} @ {formatMoney(marker.price)}</span>
              {typeof marker.quantity === 'number' && <span>Qty: {marker.quantity}</span>}
              {marker.side === 'SELL' && typeof marker.pnl_net === 'number' && (
                <span className="tv-tooltip__pnl">{formatSignedMoney(marker.pnl_net)}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="tv-chart__watermark">
        {isEquityChart
          ? `Portfolio Equity — Historical Replay — ${geometry.visibleBars[0]?.date ?? '—'} to ${geometry.visibleBars[geometry.visibleBars.length - 1]?.date ?? '—'}`
          : `Historical Replay — ${title ? '' : 'NIFTY 50'} — ${geometry.visibleBars[0]?.date ?? '—'} to ${geometry.visibleBars[geometry.visibleBars.length - 1]?.date ?? '—'}`}
      </div>
    </div>
  )
}