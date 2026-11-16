import { useMemo } from 'react'
import { formatDate, formatPercent } from '../lib/format.js'

const W = 720
const H = 220
const PAD = { top: 14, right: 14, bottom: 24, left: 56 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom

export default function DrawdownChart({ curve }) {
  const points = useMemo(() => {
    if (!Array.isArray(curve)) return []
    return curve.map(([date, value]) => ({ date, value: Number(value) || 0 })).filter(p => p.date)
  }, [curve])

  if (points.length < 2) return null

  const values = points.map(p => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const yFor = v => PAD.top + (1 - (v - min) / span) * PLOT_H
  const xFor = i => PAD.left + (points.length === 1 ? PLOT_W/2 : (i / (points.length - 1)) * PLOT_W)

  const coords = points.map((p,i)=>({x:xFor(i),y:yFor(p.value)}))
  const line = coords.map(c=>`${c.x.toFixed(2)},${c.y.toFixed(2)}`).join(' ')
  const area = `${PAD.left},${PAD.top+PLOT_H} ${line} ${PAD.left+PLOT_W},${PAD.top+PLOT_H}`

  return (
    <figure className="equity-chart">
      <figcaption className="equity-chart__head">
        <span className="equity-chart__title">Drawdown</span>
        <span className="equity-chart__readout">
          {formatPercent(max,2)} → {formatPercent(min,2)}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="equity-chart__svg">
        <polygon className="equity-chart__area equity-chart__area--down" points={area}/>
        <polyline className={`equity-chart__line equity-chart__line--down`} points={line}/>
      </svg>
      <div className="equity-chart__dates">
        <span>{formatDate(points[0].date)}</span>
        <span>{formatDate(points[points.length-1].date)}</span>
      </div>
    </figure>
  )
}
