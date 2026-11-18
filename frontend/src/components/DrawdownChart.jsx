import { useCallback, useMemo, useRef, useState } from 'react'
import { formatDate, formatDateIso, formatMoney, formatPercent } from '../lib/format.js'

const W = 960
const H = 300
const PAD = { top: 16, right: 18, bottom: 28, left: 72 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom

export default function DrawdownChart({ curve, equityCurve }) {
  const [hover, setHover] = useState(null)
  const svgRef = useRef(null)
  const gradId = useMemo(() => `dd-fill-${Math.random().toString(36).slice(2, 9)}`, [])
  const points = useMemo(() => {
    if (!Array.isArray(curve)) return []
    return curve.map(([date, value]) => ({ date, value: Number(value) || 0 })).filter((p) => p.date)
  }, [curve])
  const eqMap = useMemo(() => {
    const m = new Map()
    if (Array.isArray(equityCurve)) for (const [d, v] of equityCurve) if (typeof d === 'string') m.set(d, Number(v))
    return m
  }, [equityCurve])

  const geometry = useMemo(() => {
    if (points.length < 2) return null
    const values = points.map((p) => p.value)
    const min = Math.min(...values, 0)
    const max = Math.max(...values, 0)
    const span = (max - min) || 1
    const yFor = (v) => PAD.top + (1 - (v - min) / span) * PLOT_H
    const xFor = (i) => PAD.left + (points.length === 1 ? PLOT_W / 2 : (i / (points.length - 1)) * PLOT_W)
    const coords = points.map((p, i) => ({ x: xFor(i), y: yFor(p.value) }))
    const line = coords.map((c) => `${c.x.toFixed(2)},${c.y.toFixed(2)}`).join(' ')
    const zeroY = yFor(0)
    const area = `${coords[0].x.toFixed(2)},${zeroY.toFixed(2)} ${line} ${coords[coords.length - 1].x.toFixed(2)},${zeroY.toFixed(2)}`
    const tickEvery = points.length > 12 ? Math.ceil(points.length / 6) : 1
    const xTicks = points.map((p, i) => ({ i, label: formatDate(p.date) || formatDateIso(p.date) })).filter((t, idx) => idx % tickEvery === 0 || idx === points.length - 1)
    return { coords, line, area, min, max, yFor, zeroY, xTicks, count: points.length }
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

  if (!geometry) return null
  const active = hover !== null && hover >= 0 && hover < geometry.count ? hover : null
  const activePt = active === null ? null : points[active]
  const activeCoord = active === null ? null : geometry.coords[active]
  const activeEq = activePt ? eqMap.get(activePt.date) : undefined

  return (
    <figure className="equity-chart">
      <figcaption className="equity-chart__head"><div><span className="equity-chart__title">Drawdown (genuine)</span><div className="equity-chart__subtle">From sampled equity curve; hover for date, drawdown %, and equity at point.</div></div><span className="equity-chart__readout">{formatPercent(Math.min(...points.map((p) => p.value)), 2)} worst</span></figcaption>
      <svg ref={svgRef} className="equity-chart__svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Drawdown chart" tabIndex={0} style={{ width: '100%', height: 'auto', display: 'block', background: '#FFFFFF' }}
        onPointerMove={(e) => setHover(indexFromClientX(e.clientX))} onPointerLeave={() => setHover(null)} onFocus={() => setHover(points.length - 1)} onBlur={() => setHover(null)}>
        <defs><linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#EF4444" stopOpacity="0.28" /><stop offset="100%" stopColor="#FCA5A5" stopOpacity="0.06" /></linearGradient></defs>
        <line className="equity-chart__grid" x1={PAD.left} x2={PAD.left + PLOT_W} y1={geometry.zeroY} y2={geometry.zeroY} stroke="#E2E8F0" strokeDasharray="4 3" strokeWidth="1" />
        {geometry.xTicks.map((t) => { const x = geometry.coords[t.i]?.x ?? PAD.left; return <text key={`${t.i}-${t.label}`} className="equity-chart__axis-text equity-chart__axis-text--x" x={x} y={H - 8} textAnchor="middle" fill="#475569" fontSize="11">{t.label}</text> })}
        <polygon className="equity-chart__area equity-chart__area--down" points={geometry.area} fill={`url(#${gradId})`} />
        <polyline className="equity-chart__line equity-chart__line--down" points={geometry.line} fill="none" stroke="#EF4444" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {activeCoord && <><line className="equity-chart__crosshair" x1={activeCoord.x} x2={activeCoord.x} y1={PAD.top} y2={PAD.top + PLOT_H} stroke="#94A3B8" strokeWidth="1" strokeDasharray="4 3" /><circle className="equity-chart__marker" cx={activeCoord.x} cy={activeCoord.y} r={4} fill="#DC2626" stroke="#FFFFFF" strokeWidth="1.5" /></>}
      </svg>
      {activePt && activeCoord && <div className="equity-chart__tooltip" style={{ left: `${(activeCoord.x / W) * 100}%`, top: `${(activeCoord.y / H) * 100}%` }}><div className="equity-chart__tooltip-date">{formatDate(activePt.date) || formatDateIso(activePt.date)}</div><div className="equity-chart__tooltip-value">Drawdown: {formatPercent(activePt.value, 2)}</div>{Number.isFinite(activeEq) ? <div className="equity-chart__tooltip-sub">Equity: {formatMoney(activeEq)}</div> : null}</div>}
      <div className="equity-chart__dates"><span>{formatDate(points[0].date)}</span><span className="chart-hint">Hover chart for exact values</span><span>{formatDate(points[points.length - 1].date)}</span></div>
    </figure>
  )
}
