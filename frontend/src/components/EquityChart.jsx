import { useCallback, useMemo, useRef, useState } from 'react'
import { formatDate, formatDateIso, formatMoney } from '../lib/format.js'

const W = 960
const H = 360
const PAD = { top: 16, right: 18, bottom: 28, left: 72 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom

function toPoint(entry) {
  if (!Array.isArray(entry)) return null
  const [date, value] = entry
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return { date: typeof date === 'string' ? date : '', value }
}

export default function EquityChart({ curve, title = 'Equity Curve', subtitle }) {
  const [hover, setHover] = useState(null)
  const svgRef = useRef(null)
  const gradId = useMemo(() => `eq-fill-${Math.random().toString(36).slice(2, 9)}`, [])

  const points = useMemo(() => (Array.isArray(curve) ? curve.map(toPoint).filter(Boolean) : []), [curve])

  const geometry = useMemo(() => {
    if (points.length === 0) return null
    const values = points.map((p) => p.value)
    const rawMin = Math.min(...values)
    const rawMax = Math.max(...values)
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
    const tickEvery = points.length > 12 ? Math.ceil(points.length / 6) : 1
    const xTicks = points.map((p, i) => ({ i, label: formatDate(p.date) || formatDateIso(p.date) })).filter((t, idx) => idx % tickEvery === 0 || idx === points.length - 1)
    return { coords, line, area, rawMin, rawMax, gridLevels, yFor, xTicks, count: points.length }
  }, [points])

  const indexFromClientX = useCallback((clientX) => {
    const svg = svgRef.current
    if (!svg || !geometry) return null
    const rect = svg.getBoundingClientRect()
    if (rect.width === 0) return null
    const viewBoxX = ((clientX - rect.left) / rect.width) * W
    const ratio = (viewBoxX - PAD.left) / PLOT_W
    const raw = Math.round(ratio * (geometry.count - 1))
    return Math.min(Math.max(raw, 0), geometry.count - 1)
  }, [geometry])

  if (!geometry || geometry.count < 2) return <div className="bt-empty-inline">Not enough equity points to draw the chart.</div>

  const active = hover !== null && hover >= 0 && hover < geometry.count ? hover : null
  const activePoint = active === null ? null : points[active]
  const activeCoord = active === null ? null : geometry.coords[active]

  return (
    <figure className="equity-chart equity-chart--equity equity-chart--lg">
      <figcaption className="equity-chart__head">
        <div><span className="equity-chart__title">{title}</span>{subtitle ? <div className="equity-chart__subtle">{subtitle}</div> : null}</div>
        <span className="equity-chart__readout">{formatMoney(geometry.rawMin)} → {formatMoney(geometry.rawMax)}</span>
      </figcaption>
      <svg ref={svgRef} data-equity-svg className="equity-chart__svg" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Equity curve from ${formatDate(points[0].date)} to ${formatDate(points[points.length - 1].date)}.`} tabIndex={0}
        style={{ width: '100%', height: 'auto', display: 'block', background: '#FFFFFF' }}
        onPointerMove={(event) => setHover(indexFromClientX(event.clientX))} onPointerLeave={() => setHover(null)} onFocus={() => setHover(points.length - 1)} onBlur={() => setHover(null)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
            event.preventDefault()
            const base = hover === null ? points.length - 1 : hover
            const next = event.key === 'ArrowRight' ? base + 1 : base - 1
            setHover(Math.min(Math.max(next, 0), points.length - 1))
          } else if (event.key === 'Escape') setHover(null)
        }}>
        <defs><linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#F59E0B" stopOpacity="0.28" /><stop offset="100%" stopColor="#FDE68A" stopOpacity="0.06" /></linearGradient></defs>
        {geometry.gridLevels.map((level) => <line key={level} className="equity-chart__grid" x1={PAD.left} x2={PAD.left + PLOT_W} y1={geometry.yFor(level)} y2={geometry.yFor(level)} stroke="#E2E8F0" strokeWidth="1" />)}
        {geometry.gridLevels.map((level) => <text key={`label-${level}`} className="equity-chart__axis-text" x={PAD.left - 8} y={geometry.yFor(level) + 3} textAnchor="end" fill="#475569" fontSize="11">{formatMoney(level)}</text>)}
        <text className="equity-chart__axis-title" x={12} y={H / 2} transform={`rotate(-90 12 ${H / 2})`} fill="#475569" fontSize="11">Portfolio value</text>
        {geometry.xTicks.map((t) => { const x = geometry.coords[t.i]?.x ?? PAD.left; return <text key={`${t.i}-${t.label}`} className="equity-chart__axis-text equity-chart__axis-text--x" x={x} y={H - 8} textAnchor="middle" fill="#475569" fontSize="11">{t.label}</text> })}
        <polygon className="equity-chart__area equity-chart__area--equity" points={geometry.area} fill={`url(#${gradId})`} />
        <polyline className="equity-chart__line equity-chart__line--equity" points={geometry.line} fill="none" stroke="#F59E0B" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
        {activeCoord && <><line className="equity-chart__crosshair" x1={activeCoord.x} x2={activeCoord.x} y1={PAD.top} y2={PAD.top + PLOT_H} stroke="#94A3B8" strokeWidth="1" strokeDasharray="4 3" /><circle className="equity-chart__marker" cx={activeCoord.x} cy={activeCoord.y} r={4} fill="#D97706" stroke="#FFFFFF" strokeWidth="1.5" /></>}
      </svg>
      {activePoint && activeCoord && <div className="equity-chart__tooltip" style={{ left: `${(activeCoord.x / W) * 100}%`, top: `${(activeCoord.y / H) * 100}%` }}><div className="equity-chart__tooltip-date">{formatDate(activePoint.date) || formatDateIso(activePoint.date)}</div><div className="equity-chart__tooltip-value">{formatMoney(activePoint.value)}</div></div>}
      <div className="equity-chart__dates"><span>{formatDate(points[0].date)}</span><span className="chart-hint">Hover/focus chart; use ← → keys to inspect points</span><span>{formatDate(points[points.length - 1].date)}</span></div>
    </figure>
  )
}
