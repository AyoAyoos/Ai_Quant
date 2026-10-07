import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchMarketBars,
  fetchPaperAccount,
  fetchPaperOrders,
  fetchPaperPositions,
  fetchPaperTrades,
  runPaperTick,
} from '../lib/api.js'
import {
  formatDate,
  formatDateTime,
  formatInt,
  formatMoney,
  formatPercent,
  formatSignedMoney,
} from '../lib/format.js'
import Note from './Note.jsx'
import StatusBadge from './StatusBadge.jsx'
import PaperTradeChart from './PaperTradeChart.jsx'

function settled(promise) {
  return promise.then(
    (value) => ({ ok: true, value }),
    (error) => ({ ok: false, error }),
  )
}

function errorMessage(err) {
  if (!err) return 'Request failed.'
  if (typeof err.message === 'string' && err.message) return err.message
  return 'Request failed.'
}

/**
 * Expandable paper-deployment details: virtual account, positions, orders,
 * trades, a Run-Paper-Tick control and the NIFTY candlestick chart with
 * stored-execution markers. Every number comes from the backend; nothing is
 * computed or invented here.
 */
export default function PaperDeploymentDetails({ deployment, onChanged }) {
  const strategyId = deployment.strategy_id
  const deploymentId = deployment.id
  const isActive = deployment.status === 'active'

  const [account, setAccount] = useState(null)
  const [positions, setPositions] = useState([])
  const [orders, setOrders] = useState([])
  const [trades, setTrades] = useState([])
  const [bars, setBars] = useState([])
  const [barsTruncated, setBarsTruncated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sectionErrors, setSectionErrors] = useState({})
  const [tickBusy, setTickBusy] = useState(false)
  const [tickResult, setTickResult] = useState(null)
  const [tickError, setTickError] = useState(null)

  const load = useCallback(
    async (signal) => {
      setLoading(true)
      const opts = { deploymentId, signal }
      const [accountRes, positionsRes, ordersRes, tradesRes, barsRes] = await Promise.all([
        settled(fetchPaperAccount(strategyId, opts)),
        settled(fetchPaperPositions(strategyId, opts)),
        settled(fetchPaperOrders(strategyId, opts)),
        settled(fetchPaperTrades(strategyId, opts)),
        settled(fetchMarketBars(strategyId, opts)),
      ])
      if (signal?.aborted) return
      const errors = {}
      if (accountRes.ok) setAccount(accountRes.value)
      else errors.account = errorMessage(accountRes.error)
      if (positionsRes.ok) setPositions(Array.isArray(positionsRes.value) ? positionsRes.value : [])
      else errors.positions = errorMessage(positionsRes.error)
      if (ordersRes.ok) setOrders(Array.isArray(ordersRes.value) ? ordersRes.value : [])
      else errors.orders = errorMessage(ordersRes.error)
      if (tradesRes.ok) setTrades(Array.isArray(tradesRes.value) ? tradesRes.value : [])
      else errors.trades = errorMessage(tradesRes.error)
      if (barsRes.ok) {
        setBars(Array.isArray(barsRes.value?.bars) ? barsRes.value.bars : [])
        setBarsTruncated(Boolean(barsRes.value?.truncated))
      } else {
        errors.bars = errorMessage(barsRes.error)
      }
      setSectionErrors(errors)
      setLoading(false)
    },
    [strategyId, deploymentId],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  async function handleTick() {
    if (tickBusy || !isActive) return
    setTickBusy(true)
    setTickError(null)
    setTickResult(null)
    try {
      const result = await runPaperTick(strategyId, { deploymentId })
      setTickResult(result)
      await load()
      if (typeof onChanged === 'function') {
        try {
          await onChanged()
        } catch {
          // Parent summary refresh is best-effort; details already reloaded.
        }
      }
    } catch (err) {
      setTickError(err)
    } finally {
      setTickBusy(false)
    }
  }

  const markers = useMemo(() => {
    const pnlByExitOrder = new Map()
    for (const trade of trades) {
      if (trade?.exit_order_id) pnlByExitOrder.set(trade.exit_order_id, trade.pnl_net)
    }
    return orders
      .filter((order) => order?.status === 'filled')
      .map((order) => ({
        bar_date: order.bar_date,
        side: order.side,
        price: order.price,
        quantity: order.quantity,
        pnl_net: pnlByExitOrder.get(order.id) ?? null,
      }))
  }, [orders, trades])

  const filledCount = markers.length
  const rejectedCount = useMemo(
    () => orders.filter((order) => order?.status === 'rejected').length,
    [orders],
  )

  return (
    <div className="paper-details">
      {isActive ? (
        <div className="paper-details__tick">
          <div className="paper-details__tick-row">
            <button
              type="button"
              className="btn btn--sm btn--positive"
              onClick={handleTick}
              disabled={tickBusy}
            >
              {tickBusy && <span className="btn__spinner" aria-hidden="true" />}
              {tickBusy ? 'Running paper tick…' : 'Run paper tick'}
            </button>
          </div>
          <p className="disclaimer-text">
            Advances the next cached NIFTY bar through the strategy&apos;s own simulation.
            No broker, no real money.
          </p>
          {tickResult && (
            <Note
              tone={tickResult.action === 'HOLD' ? 'warning' : 'success'}
              title={`Paper tick ${tickResult.bar_date}: ${tickResult.action}`}
            >
              <span>
                Signal {tickResult.signal} → {tickResult.action}.{' '}
                {tickResult.note ?? ''}
                {tickResult.order_status === 'rejected' ? ' (order stored as rejected)' : ''}
              </span>
            </Note>
          )}
          {tickError && (
            <Note tone="danger" title="Paper tick failed" reasons={tickError.reasons}>
              <span>{errorMessage(tickError)}</span>
            </Note>
          )}
        </div>
      ) : (
        <div>
          <Note tone="info" title="Paper Trading stopped">
            <span>
              This deployment is stopped, so paper ticks are disabled. Its stored history is
              shown below.
              {deployment.stopped_at ? ` Stopped at: ${formatDateTime(deployment.stopped_at)}.` : ''}
              {deployment.stop_reason ? ` Reason: ${deployment.stop_reason}` : ''}
            </span>
          </Note>
        </div>
      )}

      {loading ? (
        <p className="disclaimer-text">Loading deployment details…</p>
      ) : (
        <>
          <section aria-label="Virtual paper account">
            <h4 className="paper-details__heading">Account</h4>
            {sectionErrors.account ? (
              <Note tone="danger" title="Account failed to load">
                <span>
                  {sectionErrors.account}{' '}
                  <button type="button" className="btn btn--sm" onClick={() => load()}>
                    Retry
                  </button>
                </span>
              </Note>
            ) : account ? (
              <div className="kv">
                <div className="kv__item">
                  <span className="kv__key">Starting capital (virtual)</span>
                  <span className="kv__value tabular">₹{formatMoney(account.starting_cash)}</span>
                </div>
                <div className="kv__item">
                  <span className="kv__key">Cash / balance (virtual)</span>
                  <span className="kv__value tabular">₹{formatMoney(account.cash_balance)}</span>
                </div>
                <div className="kv__item">
                  <span className="kv__key">Equity (virtual)</span>
                  <span className="kv__value tabular">₹{formatMoney(account.equity)}</span>
                </div>
                <div className="kv__item">
                  <span className="kv__key">Realized P&amp;L</span>
                  <span className="kv__value tabular">{formatSignedMoney(account.realized_pnl)}</span>
                </div>
                <div className="kv__item">
                  <span className="kv__key">Unrealized P&amp;L</span>
                  <span className="kv__value tabular">
                    {account.unrealized_pnl === null || account.unrealized_pnl === undefined
                      ? '—'
                      : formatSignedMoney(account.unrealized_pnl)}
                  </span>
                </div>
                <div className="kv__item">
                  <span className="kv__key">Total P&amp;L</span>
                  <span className="kv__value tabular">{formatSignedMoney(account.total_pnl)}</span>
                </div>
                <div className="kv__item">
                  <span className="kv__key">Return</span>
                  <span className="kv__value tabular">{formatPercent(account.return_pct)}</span>
                </div>
                <div className="kv__item">
                  <span className="kv__key">Last processed bar</span>
                  <span className="kv__value tabular">
                    {account.last_bar_date ? formatDate(account.last_bar_date) : '—'}
                  </span>
                </div>
                {account.last_error && (
                  <div className="kv__item">
                    <span className="kv__key">Latest execution error</span>
                    <span className="kv__value">{account.last_error}</span>
                  </div>
                )}
              </div>
            ) : null}
          </section>

          <section aria-label="Open simulated positions">
            <h4 className="paper-details__heading">Positions</h4>
            {sectionErrors.positions ? (
              <Note tone="danger" title="Positions failed to load">
                <span>{sectionErrors.positions}</span>
              </Note>
            ) : positions.length === 0 ? (
              <p className="disclaimer-text">No open simulated positions.</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Symbol</th>
                      <th scope="col">Qty</th>
                      <th scope="col">Avg price</th>
                      <th scope="col">Entry date</th>
                      <th scope="col">Market value</th>
                      <th scope="col">Unrealized P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((position) => (
                      <tr key={position.id}>
                        <td>{position.symbol}</td>
                        <td className="tabular">{formatInt(position.quantity)}</td>
                        <td className="tabular">₹{formatMoney(position.avg_price)}</td>
                        <td className="tabular">{formatDate(position.entry_date)}</td>
                        <td className="tabular">
                          {position.market_value == null
                            ? '—'
                            : `₹${formatMoney(position.market_value)}`}
                        </td>
                        <td className="tabular">
                          {position.unrealized_pnl == null
                            ? '—'
                            : formatSignedMoney(position.unrealized_pnl)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section aria-label="Simulated orders">
            <h4 className="paper-details__heading">Orders</h4>
            {sectionErrors.orders ? (
              <Note tone="danger" title="Orders failed to load">
                <span>{sectionErrors.orders}</span>
              </Note>
            ) : orders.length === 0 ? (
              <p className="disclaimer-text">
                No simulated orders yet. HOLD ticks never create orders.
              </p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Bar date</th>
                      <th scope="col">Side</th>
                      <th scope="col">Qty</th>
                      <th scope="col">Fill price</th>
                      <th scope="col">Status</th>
                      <th scope="col">Commission</th>
                      <th scope="col">Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((order) => (
                      <tr key={order.id}>
                        <td className="tabular">{formatDate(order.bar_date)}</td>
                        <td>
                          <StatusBadge status={order.side} />
                        </td>
                        <td className="tabular">{formatInt(order.quantity)}</td>
                        <td className="tabular">₹{formatMoney(order.price)}</td>
                        <td>
                          <StatusBadge status={order.status} />
                        </td>
                        <td className="tabular">₹{formatMoney(order.commission)}</td>
                        <td>{order.note || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section aria-label="Completed simulated trades">
            <h4 className="paper-details__heading">Trades</h4>
            {sectionErrors.trades ? (
              <Note tone="danger" title="Trades failed to load">
                <span>{sectionErrors.trades}</span>
              </Note>
            ) : trades.length === 0 ? (
              <p className="disclaimer-text">
                No completed simulated trades yet. A trade needs a BUY fill and a later SELL
                fill.
              </p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Entry</th>
                      <th scope="col">Exit</th>
                      <th scope="col">Qty</th>
                      <th scope="col">Entry price</th>
                      <th scope="col">Exit price</th>
                      <th scope="col">Net P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((trade) => (
                      <tr key={trade.id}>
                        <td className="tabular">{formatDate(trade.entry_date)}</td>
                        <td className="tabular">{formatDate(trade.exit_date)}</td>
                        <td className="tabular">{formatInt(trade.quantity)}</td>
                        <td className="tabular">₹{formatMoney(trade.entry_price)}</td>
                        <td className="tabular">₹{formatMoney(trade.exit_price)}</td>
                        <td className="tabular">{formatSignedMoney(trade.pnl_net)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section aria-label="NIFTY paper trading chart">
            <h4 className="paper-details__heading">NIFTY 50 — simulated paper trading activity</h4>
            {sectionErrors.bars ? (
              <Note tone="danger" title="Chart data failed to load">
                <span>
                  {sectionErrors.bars}{' '}
                  <button type="button" className="btn btn--sm" onClick={() => load()}>
                    Retry
                  </button>
                </span>
              </Note>
            ) : bars.length === 0 ? (
              <p className="disclaimer-text">
                No processed market bars yet — run a paper tick to start the simulation.
              </p>
            ) : (
              <>
                <dl className="kv">
                  <div className="kv__item">
                    <span className="kv__key">Strategy</span>
                    <span className="kv__value">
                      {deployment.strategy_name ?? deployment.strategy_id}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__key">Instrument</span>
                    <span className="kv__value">NIFTY 50</span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__key">Paper trading start</span>
                    <span className="kv__value tabular">
                      {formatDateTime(deployment.deployed_at)}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__key">Paper trading end</span>
                    <span className="kv__value tabular">
                      {isActive
                        ? 'Running'
                        : deployment.stopped_at
                          ? formatDateTime(deployment.stopped_at)
                          : '—'}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__key">Starting capital (virtual)</span>
                    <span className="kv__value tabular">
                      ₹{formatMoney(deployment.starting_cash)}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__key">Current equity (virtual)</span>
                    <span className="kv__value tabular">
                      {account ? `₹${formatMoney(account.equity)}` : '—'}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__key">Virtual P&amp;L</span>
                    <span className="kv__value tabular">
                      {account ? formatSignedMoney(account.total_pnl) : '—'}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__key">Return</span>
                    <span className="kv__value tabular">
                      {account ? formatPercent(account.return_pct) : '—'}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__key">Completed paper trades</span>
                    <span className="kv__value tabular">
                      {account ? formatInt(account.completed_trades) : '—'}
                    </span>
                  </div>
                </dl>
                <PaperTradeChart bars={bars} markers={markers} />
                {barsTruncated && (
                  <Note tone="warning" title="Chart range truncated">
                    <span>
                      The backend capped the returned bars; markers beyond the shown range are
                      still stored and listed under Orders.
                    </span>
                  </Note>
                )}
                {filledCount === 0 && (
                  <p className="disclaimer-text">
                    No filled simulated executions yet — HOLD-only history shows no markers.
                  </p>
                )}
                {rejectedCount > 0 && (
                  <p className="disclaimer-text">
                    {rejectedCount} rejected simulated order{rejectedCount === 1 ? '' : 's'}{' '}
                    listed under Orders — rejected orders never appear as chart markers.
                  </p>
                )}
              </>
            )}
          </section>
        </>
      )}
    </div>
  )
}
