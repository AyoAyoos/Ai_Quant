import { formatElapsed } from '../lib/format.js'

/** "12s elapsed" — makes a slow request feel bounded instead of hung. */
export default function ElapsedTimer({ seconds }) {
  return (
    <span className="tabular" style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)' }}>
      {formatElapsed(seconds)} elapsed
    </span>
  )
}