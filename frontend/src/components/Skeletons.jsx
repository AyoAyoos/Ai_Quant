/** Real layout skeletons — never a lone spinner. */
export function SkeletonText({ lines = 3 }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <div
          key={index}
          className="skeleton skeleton--text"
          style={{ width: index === lines - 1 ? '62%' : '100%' }}
        />
      ))}
    </div>
  )
}

export function SkeletonTitle() {
  return (
    <div className="skeleton skeleton--title" aria-hidden="true" />
  )
}

export function SkeletonBlock({ height = 120 }) {
  return <div className="skeleton" style={{ height }} aria-hidden="true" />
}

/** Matches the real metrics-grid footprint so nothing jumps when data lands. */
export function SkeletonMetrics() {
  return (
    <div className="metrics-grid" aria-hidden="true">
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="metric">
          <div className="skeleton" style={{ height: 18, width: '70%' }} />
          <div className="skeleton" style={{ height: 9, width: '48%', marginTop: 6 }} />
        </div>
      ))}
    </div>
  )
}

export function SkeletonCards({ count = 3 }) {
  return (
    <div className="strategy-grid" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="skeleton skeleton--card" />
      ))}
    </div>
  )
}

/** Wraps skeletons with a live-region announcement for screen readers. */
export default function LoadingBlock({ label = 'Loading…', children }) {
  return (
    <div role="status" aria-live="polite">
      <span className="visually-hidden">{label}</span>
      {children}
    </div>
  )
}