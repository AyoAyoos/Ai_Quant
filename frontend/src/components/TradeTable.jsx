import { useMemo, useState } from 'react'
import { formatDate, formatMoney, formatSignedMoney } from '../lib/format.js'

function pnlTone(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) return 'pnl--flat'
  return value > 0 ? 'pnl--win' : 'pnl--loss'
}

/** Per-closed-trade breakdown. Sticky header, win/loss tinted net P&L. */
export default function TradeTable({ trades, truncated }) {
  const [filter, setFilter] = useState('all')
  const [sortKey, setSortKey] = useState('exit_date')
  const [sortDir, setSortDir] = useState('desc')

  const rows = useMemo(() => (Array.isArray(trades) ? trades : []), [trades])
  const hidden = typeof truncated === 'number' && truncated > 0 ? truncated : 0

  const filtered = useMemo(() => {
    let data = [...rows]
    if (filter === 'winning') data = data.filter(t => t.won)
    if (filter === 'losing') data = data.filter(t => !t.won)
    data.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return data
  }, [rows, filter, sortKey, sortDir])

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  if (rows.length === 0) {
    return (
      <p className="table-footnote">
        The backtest returned no closed trades to list.
      </p>
    )
  }

  return (
    <div className="stack stack--tight">
      <div className="row row--between" style={{ marginBottom: 'var(--sp-2)' }}>
        <div className="btn-group">
          {['all','winning','losing'].map(k => (
            <button
              key={k}
              className={`btn btn--sm ${filter===k ? 'btn--primary' : 'btn--ghost'}`}
              onClick={() => setFilter(k)}
              type="button"
            >
              {k[0].toUpperCase()+k.slice(1)}
            </button>
          ))}
        </div>
        <span className="disclaimer-text">{filtered.length} trades shown</span>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <caption className="visually-hidden">Closed trades for this backtest</caption>
          <thead>
            <tr>
              <th scope="col" onClick={() => toggleSort('entry_date')}>Entry date</th>
              <th scope="col" onClick={() => toggleSort('exit_date')}>Exit date</th>
              <th scope="col">Side</th>
              <th scope="col" className="num" onClick={() => toggleSort('size')}>Size</th>
              <th scope="col" className="num" onClick={() => toggleSort('entry_price')}>Entry</th>
              <th scope="col" className="num" onClick={() => toggleSort('exit_price')}>Exit</th>
              <th scope="col" className="num" onClick={() => toggleSort('pnl_net')}>Net P&amp;L</th>
              <th scope="col" className="num" onClick={() => toggleSort('bars_held')}>Bars</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((trade, index) => (
              <tr key={`${trade.entry_date}-${trade.exit_date}-${index}`}>
                <td>{formatDate(trade.entry_date)}</td>
                <td>{formatDate(trade.exit_date)}</td>
                <td>{trade.direction ?? '—'}</td>
                <td className="num">{trade.size ?? '—'}</td>
                <td className="num">{formatMoney(trade.entry_price)}</td>
                <td className="num">{formatMoney(trade.exit_price)}</td>
                <td className={`num pnl ${pnlTone(trade.pnl_net)}`}>{formatSignedMoney(trade.pnl_net)}</td>
                <td className="num">{trade.bars_held ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <p className="table-footnote">
          Showing the first {rows.length} of {rows.length + hidden} closed trades. The aggregate metrics above
          cover every trade.
        </p>
      )}
    </div>
  )
}