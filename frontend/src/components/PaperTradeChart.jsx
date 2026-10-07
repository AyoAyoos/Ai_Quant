import { useCallback, useMemo, useRef, useState } from 'react'
import { formatDate, formatMoney, formatSignedMoney } from '../lib/format.js'

const W = 720
const H = 300
const PAD = { top: 26, right: 14, bottom: 26, left: 58 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom

function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function cleanBar(entry) {
  if (!entry || typeof entry !== 'object') return null
  const open = num(entry.open)
  const high = num(entry.high)
  const low = num(entry.low)
  const close = num(entry.close)
  if (open === null || high === null || low === null || close === null) return null
  return { date: typeof entry.date === 'string' ? entry.date : '', open, high, low, close }
}

/**
 * Hand-drawn responsive SVG candlestick chart for simulated paper trading.
 * No chart library — same approach as EquityChart.
 *
 * `bars` are cached NIFTY OHLC bars (oldest first) from the SAME source the
 * paper engine ticks. `markers` are STORED filled executions only:
 *   { bar_date, side: 'BUY' | 'SELL', price, quantity, pnl_net? }
 * A marker renders on its execution bar: BUY ▲ below the low, SELL ▼ above
 * the high. Rejected orders and HOLDs never reach this component.
 */
export default function PaperTradeChart({ bars, markers }) {
  const [hover, setHover] = useState(null)
  const svgRef = useRef(null)

  const cleanBars = useMemo(
    () => (Array.isArray(bars) ? bars.map(cleanBar).filter(Boolean) : []),
    [bars],
  )

  const markerByIndex = useMemo(() => {
    const byDate = new Map()
    for (const marker of Array.isArray(markers) ? markers : []) {
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

  const geometry = useMemo(() => {
    if (cleanBars.length === 0) return null
    const lows = cleanBars.map((b) => b.low)
    const highs = cleanBars.map((b) => b.high)
    const rawMin = Math.min(...lows)
    const rawMax = Math.max(...highs)
    // Headroom for the SELL ▼ markers that sit above the highs and the
    // BUY ▲ markers below the lows.
    const span0 = rawMax - rawMin || Math.max(Math.abs(rawMax) * 0.02, 1)
    const min = rawMin - span0 * 0.14
    const max = rawMax + span0 * 0.14
    const span = max - min || 1

    const step = PLOT_W / cleanBars.length
    const xFor = (i) => PAD.left + step * (i + 0.5)
    const yFor = (v) => PAD.top + (1 - (v - min) / span) * PLOT_H
    const bodyWidth = Math.max(2, Math.min(14, step * 0.6))

    const gridLevels = [rawMax, (rawMax + rawMin) / 2, rawMin]
    return { xFor, yFor, step, bodyWidth, gridLevels, count: cleanBars.length }
  }, [cleanBars])

  const indexFromClientX = useCallback(
    (clientX) => {
      const svg = svgRef.current
      if (!svg || !geometry) return null
      const rect = svg.getBoundingClientRect()
      if (rect.width === 0) return null
      const viewBoxX = ((clientX - rect.left) / rect.width) * W
      const raw = Math.floor((viewBoxX - PAD.left) / geometry.step)
      return Math.min(Math.max(raw, 0), geometry.count - 1)
    },
    [geometry],
  )

  if (!geometry) return null

  const active = hover !== null && hover >= 0 && hover < geometry.count ? hover : null
  const activeBar = active === null ? null : cleanBars[active]
  const activeMarkers = active === null ? [] : (markerByIndex.get(active) ?? [])

  return (
    <figure className="candle-chart">
      <figcaption className="candle-chart__head">
        <span className="candle-chart__title">NIFTY 50 — simulated paper trading activity</span>
        <span className="candle-chart__badge">Simulated paper trading — no real money</span>
      </figcaption>

      <svg
        ref={svgRef}
        className="candle-chart__svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`NIFTY 50 candlestick chart from ${formatDate(
          cleanBars[0].date,
        )} to ${formatDate(cleanBars[cleanBars.length - 1].date)} with simulated trade markers.`}
        tabIndex={0}
        onPointerMove={(event) => setHover(indexFromClientX(event.clientX))}
        onPointerLeave={() => setHover(null)}
        onFocus={() => setHover(cleanBars.length - 1)}
        onBlur={() => setHover(null)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
            event.preventDefault()
            const base = hover === null ? cleanBars.length - 1 : hover
            const next = event.key === 'ArrowRight' ? base + 1 : base - 1
            setHover(Math.min(Math.max(next, 0), cleanBars.length - 1))
          } else if (event.key === 'Escape') {
            setHover(null)
          }
        }}
      >
        {geometry.gridLevels.map((level) => (
          <line
            key={level}
            className="candle-chart__grid"
            x1={PAD.left}
            x2={PAD.left + PLOT_W}
            y1={geometry.yFor(level)}
            y2={geometry.yFor(level)}
          />
        ))}
        {geometry.gridLevels.map((level) => (
          <text
            key={`label-${level}`}
            className="candle-chart__axis-text"
            x={PAD.left - 8}
            y={geometry.yFor(level) + 3}
            textAnchor="end"
          >
            {formatMoney(level)}
          </text>
        ))}

        {cleanBars.map((bar, i) => {
          const up = bar.close >= bar.open
          const tone = up ? 'up' : 'down'
          const x = geometry.xFor(i)
          const barMarkers = markerByIndex.get(i) ?? []
          const hasBuy = barMarkers.some((m) => m.side === 'BUY')
          const hasSell = barMarkers.some((m) => m.side === 'SELL')
          return (
            <g key={`${bar.date}-${i}`}>
              <line
                className={`candle-chart__wick candle-chart__wick--${tone}`}
                x1={x}
                x2={x}
                y1={geometry.yFor(bar.high)}
                y2={geometry.yFor(bar.low)}
              />
              <rect
                className={`candle-chart__body candle-chart__body--${tone}`}
                x={x - geometry.bodyWidth / 2}
                y={geometry.yFor(Math.max(bar.open, bar.close))}
                width={geometry.bodyWidth}
                height={Math.max(1.5, Math.abs(geometry.yFor(bar.open) - geometry.yFor(bar.close)))}
              />
              {hasBuy && (
                <polygon
                  className="candle-chart__marker candle-chart__marker--buy"
                  points={`${x},${geometry.yFor(bar.low) + 13} ${x - 6},${geometry.yFor(bar.low) + 4} ${x + 6},${geometry.yFor(bar.low) + 4}`}
                >
                  <title>Simulated BUY marker</title>
                </polygon>
              )}
              {hasSell && (
                <polygon
                  className="candle-chart__marker candle-chart__marker--sell"
                  points={`${x},${geometry.yFor(bar.high) - 13} ${x - 6},${geometry.yFor(bar.high) - 4} ${x + 6},${geometry.yFor(bar.high) - 4}`}
                >
                  <title>Simulated SELL marker</title>
                </polygon>
              )}
              {active === i && (
                <line
                  className="candle-chart__crosshair"
                  x1={x}
                  x2={x}
                  y1={PAD.top}
                  y2={PAD.top + PLOT_H}
                />
              )}
            </g>
          )
        })}
      </svg>

      {activeBar && (
        <div
          className="candle-chart__tooltip"
          style={{ left: `${(geometry.xFor(active) / W) * 100}%` }}
        >
          <div className="candle-chart__tooltip-date">{formatDate(activeBar.date)}</div>
          <div className="candle-chart__tooltip-row">
            O {formatMoney(activeBar.open)} · H {formatMoney(activeBar.high)} · L{' '}
            {formatMoney(activeBar.low)} · C {formatMoney(activeBar.close)}
          </div>
          {activeMarkers.map((marker, k) => (
            <div className="candle-chart__tooltip-trade" key={k}>
              <span>
                SIMULATED {marker.side} @ {formatMoney(marker.price)} ×{' '}
                {typeof marker.quantity === 'number' ? marker.quantity : '—'}
              </span>
              {marker.side === 'SELL' && typeof marker.pnl_net === 'number' && (
                <span>Virtual P&amp;L {formatSignedMoney(marker.pnl_net)}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="candle-chart__dates">
        <span>{formatDate(cleanBars[0].date)}</span>
        <span className="chart-hint">Hover or focus the chart and use ← → to inspect bars</span>
        <span>{formatDate(cleanBars[cleanBars.length - 1].date)}</span>
      </div>
    </figure>
  )
}
