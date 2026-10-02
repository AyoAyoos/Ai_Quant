import { useCallback, useMemo, useRef, useState } from 'react'
import { formatDate, formatDateIso, formatMoney } from '../lib/format.js'

const W = 720
const H = 260
const PAD = { top: 14, right: 14, bottom: 24, left: 56 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom

function toPoint(entry) {
  if (!Array.isArray(entry)) return null
  const [date, value] = entry
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return { date: typeof date === 'string' ? date : '', value }
}

/**
 * Hand-drawn SVG equity curve with a hover/keyboard crosshair.
 * No chart library: the backend caps the curve at 400 points, so plain
 * index-to-x scaling is accurate enough and keeps the payload small.
 */
export default function EquityChart({ curve }) {
  const [hover, setHover] = useState(null)
  const svgRef = useRef(null)

  const points = useMemo(
    () => (Array.isArray(curve) ? curve.map(toPoint).filter(Boolean) : []),
    [curve],
  )

  const geometry = useMemo(() => {
    if (points.length === 0) return null

    const values = points.map((p) => p.value)
    const rawMin = Math.min(...values)
    const rawMax = Math.max(...values)
    // Headroom so the line never touches the frame, and never divide by zero
    // on a perfectly flat equity path.
    const headroom = (rawMax - rawMin) * 0.12 || Math.max(Math.abs(rawMax) * 0.02, 1)
    const min = rawMin - headroom
    const max = rawMax + headroom
    const span = max - min || 1

    const xFor = (i) => (points.length === 1 ? PAD.left + PLOT_W / 2 : PAD.left + (i / (points.length - 1)) * PLOT_W)
    const yFor = (v) => PAD.top + (1 - (v - min) / span) * PLOT_H

    const coords = points.map((p, i) => ({ x: xFor(i), y: yFor(p.value) }))
    const line = coords.map((c) => `${c.x.toFixed(2)},${c.y.toFixed(2)}`).join(' ')
    const area = `${PAD.left},${PAD.top + PLOT_H} ${line} ${PAD.left + PLOT_W},${PAD.top + PLOT_H}`

    const gridLevels = [rawMax, (rawMax + rawMin) / 2, rawMin]
    const up = points[points.length - 1].value >= points[0].value

    return { coords, line, area, min, max, rawMin, rawMax, gridLevels, yFor, up, count: points.length }
  }, [points])

  const indexFromClientX = useCallback(
    (clientX) => {
      const svg = svgRef.current
      if (!svg || !geometry) return null
      const rect = svg.getBoundingClientRect()
      if (rect.width === 0) return null
      const viewBoxX = ((clientX - rect.left) / rect.width) * W
      const ratio = (viewBoxX - PAD.left) / PLOT_W
      const raw = Math.round(ratio * (geometry.count - 1))
      return Math.min(Math.max(raw, 0), geometry.count - 1)
    },
    [geometry],
  )

  if (!geometry || geometry.count < 2) return null

  const tone = geometry.up ? 'up' : 'down'
  const active = hover !== null && hover >= 0 && hover < geometry.count ? hover : null
  const activePoint = active === null ? null : points[active]
  const activeCoord = active === null ? null : geometry.coords[active]

  return (
    <figure className="equity-chart">
      <figcaption className="equity-chart__head">
        <span className="equity-chart__title">Portfolio value</span>
        <span className="equity-chart__readout">
          {formatMoney(geometry.rawMin)} → {formatMoney(geometry.rawMax)}
        </span>
      </figcaption>

      <svg
        ref={svgRef}
        data-equity-svg
        className="equity-chart__svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Equity curve from ${formatDate(points[0].date)} to ${formatDate(
          points[points.length - 1].date,
        )}, ${geometry.up ? 'up' : 'down'} over the backtest period.`}
        tabIndex={0}
        onPointerMove={(event) => setHover(indexFromClientX(event.clientX))}
        onPointerLeave={() => setHover(null)}
        onFocus={() => setHover(points.length - 1)}
        onBlur={() => setHover(null)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
            event.preventDefault()
            const base = hover === null ? points.length - 1 : hover
            const next = event.key === 'ArrowRight' ? base + 1 : base - 1
            setHover(Math.min(Math.max(next, 0), points.length - 1))
          } else if (event.key === 'Escape') {
            setHover(null)
          }
        }}
      >
        {geometry.gridLevels.map((level) => (
          <line
            key={level}
            className="equity-chart__grid"
            x1={PAD.left}
            x2={PAD.left + PLOT_W}
            y1={geometry.yFor(level)}
            y2={geometry.yFor(level)}
          />
        ))}

        {geometry.gridLevels.map((level) => (
          <text
            key={`label-${level}`}
            className="equity-chart__axis-text"
            x={PAD.left - 8}
            y={geometry.yFor(level) + 3}
            textAnchor="end"
          >
            {formatMoney(level)}
          </text>
        ))}

        <polygon className={`equity-chart__area equity-chart__area--${tone}`} points={geometry.area} />
        <polyline className={`equity-chart__line equity-chart__line--${tone}`} points={geometry.line} />

        {activeCoord && (
          <>
            <line
              className="equity-chart__crosshair"
              x1={activeCoord.x}
              x2={activeCoord.x}
              y1={PAD.top}
              y2={PAD.top + PLOT_H}
            />
            <circle
              className="equity-chart__marker"
              cx={activeCoord.x}
              cy={activeCoord.y}
              r={4}
              fill={tone === 'up' ? 'var(--positive)' : 'var(--negative)'}
            />
          </>
        )}
      </svg>

      {activePoint && activeCoord && (
        <div
          className="equity-chart__tooltip"
          style={{
            left: `${(activeCoord.x / W) * 100}%`,
            top: `${(activeCoord.y / H) * 100}%`,
          }}
        >
          <div className="equity-chart__tooltip-date">
            {formatDate(activePoint.date) || formatDateIso(activePoint.date)}
          </div>
          <div className="equity-chart__tooltip-value">{formatMoney(activePoint.value)}</div>
        </div>
      )}

      <div className="equity-chart__dates">
        <span>{formatDate(points[0].date)}</span>
        <span className="chart-hint">Hover or focus the chart and use ← → to inspect days</span>
        <span>{formatDate(points[points.length - 1].date)}</span>
      </div>
    </figure>
  )
}