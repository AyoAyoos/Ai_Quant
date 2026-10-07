import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Icon from './Icon.jsx'

/**
 * LineSidebar — vertical dashboard rail with a physics-smoothed marker line.
 *
 * The marker rests on the active route and glides toward the cursor:
 * hovering a row retargets it, and moving near (but not on) a row pulls it
 * partway with a smooth falloff, clamped to `maxShift`. Positions are
 * measured from the live DOM so collapsing/rail layouts keep working.
 *
 * Props mirror the requested configuration:
 *   items            [{ label, to, icon?, match?: string[], badge?: number }]
 *   defaultActive    index used when no route matches
 *   accentColor      tick / secondary accents
 *   markerColor      the travelling marker line
 *   textColor        item labels
 *   fontSize         item label size in rem
 *   itemGap          vertical gap between rows, px
 *   markerGap        marker offset from the rail's left edge, px
 *   markerLength     marker line length, px
 *   maxShift         max proximity pull from rest, px
 *   proximityRadius  cursor influence radius around the nearest row, px
 *   showIndex        render `01`-style indices
 *   showMarker       render the travelling marker line
 *   smoothing        higher = slower glide (rate-normalised per second)
 *   tickScale        tick mark width multiplier
 *   scaleTick        render per-row scale ticks
 *   falloff          'smooth' (quadratic) or 'linear' proximity falloff
 *   onItemClick      (index, label) => void — extra hook alongside routing
 */
export default function LineSidebar({
  items = [],
  defaultActive = 0,
  accentColor = '#AF719D',
  markerColor = '#8B639B',
  textColor = '#403D88',
  fontSize = 1.1,
  itemGap = 24,
  markerGap = 10,
  markerLength = 40,
  maxShift = 20,
  proximityRadius = 100,
  showIndex = true,
  showMarker = true,
  smoothing = 100,
  tickScale = 0.5,
  scaleTick = true,
  falloff = 'smooth',
  onItemClick,
  open = false,
  onNavigate,
  id = 'app-sidebar',
}) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const listRef = useRef(null)
  const rowRefs = useRef([])
  const markerRef = useRef(null)
  const [hoverIndex, setHoverIndex] = useState(null)
  const animRef = useRef({ y: null, raf: 0, mouseY: null })

  const isActive = (item) => {
    if (item.end) return pathname === item.to
    if (Array.isArray(item.match) && item.match.length > 0) {
      return item.match.some((p) => (p === '/' ? pathname === '/' : pathname.startsWith(p)))
    }
    if (!item.to) return false
    return pathname === item.to || pathname.startsWith(`${item.to}/`)
  }

  let activeIndex = items.findIndex(isActive)
  if (activeIndex < 0) activeIndex = Math.min(defaultActive, items.length - 1)
  // Prefer the longest matching route so /studio/builder highlights Builder,
  // not its Studio parent.
  else {
    let best = activeIndex
    items.forEach((item, i) => {
      if (i !== activeIndex && isActive(item) && (item.to || '').length > (items[best].to || '').length) {
        best = i
      }
    })
    activeIndex = best
  }

  const centers = () => {
    const list = listRef.current
    if (!list) return []
    return rowRefs.current.map((row) => {
      if (!row) return 0
      return row.offsetTop + row.offsetHeight / 2
    })
  }

  useEffect(() => {
    const state = animRef.current
    const rate = 18 * (100 / Math.max(1, smoothing))
    let last = performance.now()
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

    const frame = (now) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const list = centers()
      if (list.length > 0 && markerRef.current) {
        const rest = list[Math.min(activeIndex, list.length - 1)] ?? 0
        let target = rest
        if (hoverIndex != null && list[hoverIndex] != null) {
          target = list[hoverIndex]
        } else if (state.mouseY != null) {
          let nearest = 0
          let best = Infinity
          list.forEach((c, i) => {
            const d = Math.abs(state.mouseY - c)
            if (d < best) {
              best = d
              nearest = i
            }
          })
          if (best < proximityRadius && list[nearest] != null) {
            const t = 1 - best / proximityRadius
            const pull = falloff === 'smooth' ? t * t : t
            const dir = state.mouseY - rest
            const shift = Math.max(-maxShift, Math.min(maxShift, dir * pull))
            target = rest + shift
          }
        }
        if (state.y == null || reduced) {
          state.y = target
        } else {
          const alpha = 1 - Math.exp(-dt * rate)
          state.y += (target - state.y) * alpha
        }
        markerRef.current.style.transform = `translateY(${state.y - markerLength / 2}px)`
      }
      state.raf = requestAnimationFrame(frame)
    }

    state.raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(state.raf)
    // Re-target when route/hover/geometry inputs change; the loop reads refs live.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, hoverIndex, markerLength, maxShift, proximityRadius, falloff, smoothing])

  const handleMouseMove = (event) => {
    const list = listRef.current
    if (!list) return
    const rect = list.getBoundingClientRect()
    animRef.current.mouseY = event.clientY - rect.top
  }

  const handleMouseLeave = () => {
    animRef.current.mouseY = null
    setHoverIndex(null)
  }

  const handleClick = (index, item) => {
    onItemClick?.(index, item.label)
    onNavigate?.()
    if (item.to) navigate(item.to)
  }

  return (
    <>
      <div
        className={`ls__scrim${open ? ' ls__scrim--open' : ''}`}
        aria-hidden="true"
        onClick={onNavigate}
      />
      <nav
        id={id}
        className={`ls${open ? ' ls--open' : ''}`}
        aria-label="Dashboard"
        style={{ fontSize: `${fontSize}rem` }}
      >
        <div
          ref={listRef}
          className="ls__list"
          style={{ gap: `${itemGap}px` }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          {showMarker && (
            <span
              ref={markerRef}
              className="ls__marker"
              aria-hidden="true"
              style={{
                left: `${markerGap}px`,
                height: `${markerLength}px`,
                background: markerColor,
                boxShadow: `0 0 12px ${markerColor}`,
              }}
            />
          )}
          {items.map((item, i) => {
            const active = i === activeIndex
            return (
              <Link
                key={item.to || item.label}
                ref={(el) => {
                  rowRefs.current[i] = el
                }}
                to={item.to || '#'}
                aria-current={active ? 'page' : undefined}
                className={`ls__item${active ? ' ls__item--active' : ''}`}
                style={{ color: textColor }}
                onMouseEnter={() => setHoverIndex(i)}
                onFocus={() => setHoverIndex(i)}
                onBlur={() => setHoverIndex(null)}
                onClick={() => handleClick(i, item)}
              >
                {scaleTick && (
                  <span
                    className="ls__tick"
                    aria-hidden="true"
                    style={{
                      background: accentColor,
                      width: `${Math.max(2, 14 * tickScale)}px`,
                    }}
                  />
                )}
                {showIndex && (
                  <span className="ls__index" aria-hidden="true">
                    {i + 1}.
                  </span>
                )}
                {item.icon && (
                  <span className="ls__icon" aria-hidden="true">
                    <Icon name={item.icon} size={19} fill={active} />
                  </span>
                )}
                <span className="ls__label">{item.label}</span>
                {item.badge > 0 && <span className="ls__count">{item.badge}</span>}
              </Link>
            )
          })}
        </div>
      </nav>
    </>
  )
}
