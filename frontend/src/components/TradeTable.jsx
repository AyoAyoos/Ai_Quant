import { useMemo } from 'react'
import { formatDate, formatMoney, formatSignedMoney } from '../lib/format.js'

function pnlTone(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) return 'pnl--flat'
  return value > 0 ? 'pnl--win' : 'pnl--loss'
}

/** Per-closed-trade breakdown. Sticky header, win/loss tinted net P&L. */
export default function TradeTable({ trades, truncated }) {
  const rows = useMemo(() => (Array.isArray(trades) ? trades : []), [trades])
  const hidden = typeof truncated === 'number' && truncated > 0 ? truncated : 0

  if (rows.length === 0) {
    return (
      <p className="table-footnote">
        The backtest returned no closed trades to list.
      </p>
    )
  }

  return (
    <div className="stack stack--tight">
      <div className="table-wrap">
        <table className="data-table">
          <caption className="visually-hidden">Closed trades for this backtest</caption>
          <thead>
            <tr>
              <th scope="col">Entry date</th>
              <th scope="col">Exit date</th>
              <th scope="col">Side</th>
              <th scope="col" className="num">Size</th>
              <th scope="col" className="num">Entry</th>
              <th scope="col" className="num">Exit</th>
              <th scope="col" className="num">Net P&amp;L</th>
              <th scope="col" className="num">Bars</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((trade, index) => (
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