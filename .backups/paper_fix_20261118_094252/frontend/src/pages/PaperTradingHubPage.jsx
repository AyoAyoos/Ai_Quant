import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  fetchAllPaperDeployments,
  fetchMarketBars,
  fetchMarketOverview,
  fetchPaperAccount,
  fetchPaperOrders,
  fetchPaperPositions,
  fetchPaperTrades,
  runPaperTick,
  stopDeployment,
} from '../lib/api.js'
import {
  formatDate,
  formatDateTime,
  formatInt,
  formatMoney,
  formatPercent,
  formatSignedMoney,
} from '../lib/format.js'
import { useAuth } from '../context/AuthContext.jsx'
import Note from '../components/Note.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import PaperDeploymentDetails from '../components/PaperDeploymentDetails.jsx'
import './PaperTradingHubPage.css'

const NAV_SECTIONS = [
  {
    label: 'Trading',
    items: [
      { label: 'Dashboard', to: '/dashboard' },
      { label: 'Paper Desk', to: '/paper-trading', active: true },
      { label: 'Journal', to: '/analytics' },
      { label: 'Reports', to: '/backtests' },
      { label: 'Insights', to: '/news' },
      { label: 'Smart Money', to: '/dashboard' },
      { label: 'Learn', to: '/docs' },
    ],
  },
  {
    label: 'AI Engines',
    items: [
      { label: 'Quant Lite', to: '/studio' },
      { label: 'DeepQuant', to: '/studio/builder' },
    ],
  },
  {
    label: 'Account',
    items: [
      { label: 'Pricing', to: '/settings' },
      { label: 'Account', to: '/settings' },
    ],
  },
]

function settled(promise) {
  return promise.then(
    (value) => ({ ok: true, value }),
    (error) => ({ ok: false, error }),
  )
}

function errMsg(err) {
  if (!err) return 'Request failed.'
  return err.message || 'Request failed.'
}

function pnlClass(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) return ''
  return value > 0 ? 'pd-pos' : 'pd-neg'
}

function initials(name) {
  return String(name || 'U')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join('')
}

export default function PaperTradingHubPage() {
  const { pathname } = useLocation()
  const { userName, user, logout } = useAuth()

  const [deployments, setDeployments] = useState([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  const [account, setAccount] = useState(null)
  const [positions, setPositions] = useState([])
  const [orders, setOrders] = useState([])
  const [trades, setTrades] = useState([])
  const [bars, setBars] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailErrors, setDetailErrors] = useState({})

  const [marketIndices, setMarketIndices] = useState([])
  const [marketStatus, setMarketStatus] = useState(null)
  const [watchQuery, setWatchQuery] = useState('')

  const [bottomTab, setBottomTab] = useState('positions')
  const [tickBusy, setTickBusy] = useState(false)
  const [tickResult, setTickResult] = useState(null)
  const [tickError, setTickError] = useState(null)
  const [stopTarget, setStopTarget] = useState(null)
  const [stopReason, setStopReason] = useState('')
  const [stopBusy, setStopBusy] = useState(false)
  const [stopError, setStopError] = useState(null)
  const [clock, setClock] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const loadDeployments = useCallback(async (signal) => {
    setListLoading(true)
    setListError(null)
    try {
      const data = await fetchAllPaperDeployments({ signal })
      if (signal?.aborted) return
      const list = Array.isArray(data) ? data : []
      setDeployments(list)
      setSelectedId((prev) => {
        if (prev && list.some((d) => d.id === prev)) return prev
        const active = list.find((d) => d.status === 'active')
        return (active || list[0] || {}).id || null
      })
    } catch (err) {
      if (err?.name === 'AbortError' || signal?.aborted) return
      setDeployments([])
      setListError(err)
    } finally {
      if (!signal?.aborted) setListLoading(false)
    }
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    loadDeployments(ctrl.signal)
    return () => ctrl.abort()
  }, [loadDeployments])

  useEffect(() => {
    const ctrl = new AbortController()
    async function loadMarket() {
      try {
        const data = await fetchMarketOverview({ signal: ctrl.signal })
        if (ctrl.signal.aborted) return
        const indices = Array.isArray(data?.indices) ? data.indices : Array.isArray(data) ? data : []
        setMarketIndices(indices)
        setMarketStatus(data?.market_status || data?.marketStatus || null)
      } catch {
        if (!ctrl.signal.aborted) setMarketIndices([])
      }
    }
    loadMarket()
    return () => ctrl.abort()
  }, [])

  const activeDeployments = useMemo(() => deployments.filter((d) => d.status === 'active'), [deployments])
  const historyDeployments = useMemo(() => deployments.filter((d) => d.status !== 'active'), [deployments])
  const selected = useMemo(
    () => deployments.find((d) => d.id === selectedId) || null,
    [deployments, selectedId],
  )

  const loadDetails = useCallback(async (signal) => {
    if (!selected) {
      setAccount(null); setPositions([]); setOrders([]); setTrades([]); setBars([]); setDetailErrors({})
      return
    }
    setDetailLoading(true)
    try {
      const opts = { deploymentId: selected.id, signal }
      const [a, p, o, t, b] = await Promise.all([
        settled(fetchPaperAccount(selected.strategy_id, opts)),
        settled(fetchPaperPositions(selected.strategy_id, opts)),
        settled(fetchPaperOrders(selected.strategy_id, opts)),
        settled(fetchPaperTrades(selected.strategy_id, opts)),
        settled(fetchMarketBars(selected.strategy_id, opts)),
      ])
      if (signal?.aborted) return
      const errs = {}
      if (a.ok) setAccount(a.value); else errs.account = errMsg(a.error)
      if (p.ok) setPositions(Array.isArray(p.value) ? p.value : []); else errs.positions = errMsg(p.error)
      if (o.ok) setOrders(Array.isArray(o.value) ? o.value : []); else errs.orders = errMsg(o.error)
      if (t.ok) setTrades(Array.isArray(t.value) ? t.value : []); else errs.trades = errMsg(t.error)
      if (b.ok) setBars(Array.isArray(b.value?.bars) ? b.value.bars : []); else errs.bars = errMsg(b.error)
      setDetailErrors(errs)
    } finally {
      if (!signal?.aborted) setDetailLoading(false)
    }
  }, [selected])

  useEffect(() => {
    const ctrl = new AbortController()
    loadDetails(ctrl.signal)
    return () => ctrl.abort()
  }, [loadDetails])

  const refreshSummaries = useCallback(async () => {
    try {
      const data = await fetchAllPaperDeployments()
      const list = Array.isArray(data) ? data : []
      setDeployments(list)
      setSelectedId((prev) => {
        if (prev && list.some((d) => d.id === prev)) return prev
        const active = list.find((d) => d.status === 'active')
        return (active || list[0] || {}).id || null
      })
    } catch {
      /* best effort */
    }
  }, [])

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshSummaries(), loadDetails()])
  }, [refreshSummaries, loadDetails])

  async function handleTick() {
    if (!selected || selected.status !== 'active' || tickBusy) return
    setTickBusy(true)
    setTickError(null)
    setTickResult(null)
    try {
      const result = await runPaperTick(selected.strategy_id, { deploymentId: selected.id })
      setTickResult(result)
      await refreshAll()
    } catch (err) {
      setTickError(err)
    } finally {
      setTickBusy(false)
    }
  }

  function askStop(dep) {
    setStopTarget(dep)
    setStopReason('')
    setStopError(null)
  }
  function cancelStop() {
    if (stopBusy) return
    setStopTarget(null); setStopReason(''); setStopError(null)
  }
  async function confirmStop() {
    if (!stopTarget || stopBusy) return
    setStopBusy(true); setStopError(null)
    try {
      await stopDeployment(stopTarget.strategy_id, stopReason.trim() || null)
      setStopTarget(null); setStopReason('')
      await refreshSummaries()
      await loadDetails()
    } catch (err) {
      setStopError(err)
    } finally {
      setStopBusy(false)
    }
  }

  async function handleLogout() {
    await logout()
    window.location.href = '/'
  }

  const winRate = useMemo(() => {
    const closed = trades.filter((t) => typeof t.pnl_net === 'number')
    if (closed.length === 0) return null
    const wins = closed.filter((t) => t.pnl_net > 0).length
    return (wins / closed.length) * 100
  }, [trades])

  const unrealized = account?.unrealized_pnl
  const exposure = useMemo(() => {
    let mv = 0
    let any = false
    for (const p of positions) {
      if (typeof p.market_value === 'number') { mv += p.market_value; any = true }
    }
    return any ? mv : null
  }, [positions])
  const capacityUsed = useMemo(() => {
    if (!account || !exposure || !account.equity || account.equity <= 0) return null
    return Math.max(0, Math.min(100, (exposure / account.equity) * 100))
  }, [account, exposure])

  const lastBar = bars.length ? bars[bars.length - 1] : null
  const prevBar = bars.length > 1 ? bars[bars.length - 2] : null
  const instrumentMovePct = useMemo(() => {
    if (!lastBar || !prevBar || !prevBar.close) return null
    return ((lastBar.close - prevBar.close) / prevBar.close) * 100
  }, [lastBar, prevBar])

  const filledOrders = useMemo(() => orders.filter((o) => o?.status === 'filled'), [orders])
  const openOrdersCount = useMemo(() => orders.filter((o) => o?.status && o.status !== 'filled' && o.status !== 'rejected' && o.status !== 'cancelled').length, [orders])

  const watchItems = useMemo(() => {
    const q = watchQuery.trim().toLowerCase()
    const fromMarket = marketIndices.map((idx) => {
      const sym = idx.symbol || idx.name || 'INDEX'
      const price = idx.price ?? idx.close ?? idx.ltp
      const chg = idx.change_pct ?? idx.changePct ?? idx.percent_change
      return {
        key: `m-${sym}`,
        symbol: sym,
        type: 'Index',
        changePct: typeof chg === 'number' ? chg : null,
        subtitle: typeof price === 'number' ? `₹${formatMoney(price)}` : '—',
        onClick: null,
      }
    })
    const fromDeps = deployments.map((d) => ({
      key: `d-${d.id}`,
      symbol: d.strategy_name || d.strategy_id,
      type: d.market || 'Strategy',
      changePct: typeof d.return_pct === 'number' ? d.return_pct : null,
      subtitle: d.status === 'active' ? 'Active deployment' : 'Stopped',
      onClick: () => setSelectedId(d.id),
      active: d.id === selectedId,
    }))
    const all = [...fromDeps, ...fromMarket]
    if (!q) return all
    return all.filter((i) => `${i.symbol} ${i.type}`.toLowerCase().includes(q))
  }, [marketIndices, deployments, watchQuery, selectedId])

  const sessionLabel = clock.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata', weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit'
  })

  const isActive = selected?.status === 'active'
  const buyingPower = account?.cash_balance ?? selected?.cash_balance ?? null
  const dayPnl = account?.total_pnl ?? selected?.total_pnl ?? null
  const profileName = userName || user?.name || 'Local user'

  return (
    <div className="paper-desk">
      <div className="paper-desk__layout">
        <aside className="paper-desk__nav pd-panel" aria-label="Paper Desk navigation">
          <div className="paper-desk__brand">
            <div className="paper-desk__brand-mark">Q</div>
            <div>
              <div className="paper-desk__brand-name">QuantNiti</div>
              <div className="paper-desk__brand-sub">Paper Trading</div>
            </div>
          </div>
          {NAV_SECTIONS.map((sec) => (
            <div className="paper-desk__nav-section" key={sec.label}>
              <div className="paper-desk__nav-label">{sec.label}</div>
              {sec.items.map((item) => {
                const active = item.to === '/paper-trading' ? pathname.startsWith('/paper-trading') : pathname === item.to
                return (
                  <Link
                    key={`${sec.label}-${item.label}`}
                    to={item.to}
                    className={`paper-desk__nav-link${active ? ' paper-desk__nav-link--active' : ''}`}
                  >
                    <span>{item.label}</span>
                  </Link>
                )
              })}
            </div>
          ))}
          <div className="paper-desk__nav-foot">
            <div className="paper-desk__user">
              <div className="paper-desk__avatar">{initials(profileName)}</div>
              <div>
                <div className="paper-desk__user-name">{profileName}</div>
                <div className="paper-desk__user-sub">{user?.email || 'Signed in'}</div>
              </div>
            </div>
            <button type="button" className="paper-desk__btn paper-desk__btn--sm" style={{marginTop:8, width:'100%'}} onClick={handleLogout}>
              Sign out
            </button>
          </div>
        </aside>

        <aside className="paper-desk__watch pd-panel" aria-label="Watchlist">
          <div className="pd-panel__head">
            <h2 className="pd-panel__title">Watchlist</h2>
            <span className="pd-faint">{marketStatus?.status || marketStatus || 'Market'}</span>
          </div>
          <div style={{padding:'8px 10px', borderBottom:'1px solid var(--pd-border)'}}>
            <input
              className="paper-desk__input"
              placeholder="Search instruments"
              value={watchQuery}
              onChange={(e)=>setWatchQuery(e.target.value)}
              aria-label="Search watchlist"
            />
          </div>
          <div className="paper-desk__watch-list">
            {watchItems.length === 0 ? (
              <div className="pd-muted" style={{padding:'10px'}}>No instruments available.</div>
            ) : watchItems.map((item) => (
              <div
                key={item.key}
                className={`paper-desk__watch-row${item.active ? ' paper-desk__watch-row--active' : ''}`}
                role={item.onClick ? 'button' : undefined}
                tabIndex={item.onClick ? 0 : undefined}
                onClick={item.onClick || undefined}
                onKeyDown={item.onClick ? (e)=>{ if(e.key==='Enter'||e.key===' ') item.onClick() } : undefined}
              >
                <div className="paper-desk__watch-sym">{item.symbol}</div>
                <div className="paper-desk__watch-type">{item.type} · {item.subtitle}</div>
                <div className={`paper-desk__watch-chg ${pnlClass(item.changePct)}`}>
                  {typeof item.changePct === 'number' ? `${item.changePct >= 0 ? '+' : ''}${item.changePct.toFixed(2)}%` : '—'}
                </div>
              </div>
            ))}
          </div>
        </aside>

        <main className="paper-desk__main" aria-label="Paper Desk workspace">
          {listError && (
            <Note tone="danger" title="Paper deployments failed to load">
              <span>{errMsg(listError)} <button type="button" className="paper-desk__btn paper-desk__btn--sm" onClick={()=>loadDeployments()}>Retry</button></span>
            </Note>
          )}

          <section className="pd-panel paper-desk__header">
            <div>
              <div className="paper-desk__title-row">
                <h1 className="paper-desk__title">Paper Desk</h1>
                <span className="paper-desk__pill"><span className="paper-desk__pill-dot" aria-hidden="true"></span>Simulated execution</span>
              </div>
              <p className="paper-desk__subtitle">
                {selected ? `${selected.strategy_name || selected.strategy_id} · ${selected.market || 'Market'}` : 'Paper trading workspace'} · Virtual account
              </p>
            </div>
            <div className="paper-desk__header-meta">
              <div className="paper-desk__time">IST {sessionLabel}</div>
              <div style={{display:'flex', gap:8}}>
                <button type="button" className="paper-desk__btn paper-desk__btn--sm" onClick={refreshAll}>Refresh</button>
                <button type="button" className="paper-desk__btn paper-desk__btn--sm" onClick={()=>{ setTickResult(null); setTickError(null); refreshAll() }} title="Reset view state and refresh data">Reset</button>
              </div>
            </div>
          </section>

          <section className="paper-desk__metrics" aria-label="Key metrics">
            <div className="pd-panel paper-desk__metric">
              <p className="paper-desk__metric-label">Buying Power</p>
              <p className="paper-desk__metric-value">{buyingPower == null ? '—' : `₹${formatMoney(buyingPower)}`}</p>
              <p className="paper-desk__metric-sub">Available cash (virtual)</p>
            </div>
            <div className="pd-panel paper-desk__metric">
              <p className="paper-desk__metric-label">Day P/L</p>
              <p className={`paper-desk__metric-value ${pnlClass(dayPnl)}`}>{dayPnl == null ? '—' : formatSignedMoney(dayPnl)}</p>
              <p className="paper-desk__metric-sub">Total P&amp;L (virtual) · {formatPercent(account?.return_pct ?? selected?.return_pct)}</p>
            </div>
            <div className="pd-panel paper-desk__metric">
              <p className="paper-desk__metric-label">Win Rate</p>
              <p className="paper-desk__metric-value">{winRate == null ? '—' : `${winRate.toFixed(1)}%`}</p>
              <p className="paper-desk__metric-sub">{trades.length ? `${trades.filter(t=>t.pnl_net>0).length}/${trades.length} profitable closed trades` : 'No completed trades yet'}</p>
            </div>
          </section>

          <section className="paper-desk__split" aria-label="Focus and execution quality">
            <div className="pd-panel">
              <div className="pd-panel__head"><h2 className="pd-panel__title">Active focus</h2>{selected && <StatusBadge status={selected.status} />}</div>
              <div className="pd-panel__body">
                {!selected ? <p className="pd-muted">Select a deployment from the watchlist.</p> : (
                  <div className="paper-desk__kv">
                    <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Selected instrument</span><span className="paper-desk__kv-v">{selected.market || 'NIFTY50'}</span></div>
                    <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Current price movement</span><span className={`paper-desk__kv-v ${pnlClass(instrumentMovePct)}`}>{lastBar ? `₹${formatMoney(lastBar.close)} (${instrumentMovePct==null?'—':`${instrumentMovePct>=0?'+':''}${instrumentMovePct.toFixed(2)}%`})` : '—'}</span></div>
                    <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Available cash</span><span className="paper-desk__kv-v">{buyingPower==null?'—':`₹${formatMoney(buyingPower)}`}</span></div>
                    <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Exposure</span><span className="paper-desk__kv-v">{exposure==null?'—':`₹${formatMoney(exposure)}`}</span></div>
                    <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Open positions</span><span className="paper-desk__kv-v">{positions.length}</span></div>
                    <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Last processed bar</span><span className="paper-desk__kv-v">{account?.last_bar_date ? formatDate(account.last_bar_date) : (selected.last_bar_date ? formatDate(selected.last_bar_date) : '—')}</span></div>
                  </div>
                )}
              </div>
            </div>
            <div className="pd-panel">
              <div className="pd-panel__head"><h2 className="pd-panel__title">Execution quality</h2></div>
              <div className="pd-panel__body">
                <div className="paper-desk__kv">
                  <div className="paper-desk__kv-item" style={{gridColumn:'1 / -1'}}>
                    <span className="paper-desk__kv-k">Capacity used</span>
                    <span className="paper-desk__kv-v">{capacityUsed==null?'—':`${capacityUsed.toFixed(1)}%`}</span>
                    <div className="paper-desk__bar"><div className="paper-desk__bar-fill" style={{width:`${capacityUsed||0}%`}} /></div>
                  </div>
                  <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Open positions</span><span className="paper-desk__kv-v">{positions.length}</span></div>
                  <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Filled orders</span><span className="paper-desk__kv-v">{filledOrders.length}</span></div>
                  <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Orders queued</span><span className="paper-desk__kv-v">{openOrdersCount}</span></div>
                  <div className="paper-desk__kv-item"><span className="paper-desk__kv-k">Completed trades</span><span className="paper-desk__kv-v">{trades.length}</span></div>
                </div>
              </div>
            </div>
          </section>

          <section className="pd-panel" aria-label="Positions and orders">
            <div className="pd-panel__head">
              <div>
                <h2 className="pd-panel__title">Portfolio activity</h2>
                <div className="pd-muted" style={{marginTop:2}}>
                  {positions.length} open position{positions.length===1?'':'s'} · Unrealized P&amp;L {unrealized==null?'—':formatSignedMoney(unrealized)}
                </div>
              </div>
              <div className="paper-desk__tabs" role="tablist" aria-label="Positions and orders">
                <button type="button" role="tab" aria-selected={bottomTab==='positions'} className={`paper-desk__tab${bottomTab==='positions'?' paper-desk__tab--active':''}`} onClick={()=>setBottomTab('positions')}>Positions</button>
                <button type="button" role="tab" aria-selected={bottomTab==='orders'} className={`paper-desk__tab${bottomTab==='orders'?' paper-desk__tab--active':''}`} onClick={()=>setBottomTab('orders')}>Orders</button>
              </div>
            </div>
            <div className="pd-panel__body" style={{padding:0}}>
              {detailErrors.positions && bottomTab==='positions' && <div style={{padding:12}}><Note tone="danger" title="Positions failed to load"><span>{detailErrors.positions}</span></Note></div>}
              {detailErrors.orders && bottomTab==='orders' && <div style={{padding:12}}><Note tone="danger" title="Orders failed to load"><span>{detailErrors.orders}</span></Note></div>}
              {bottomTab==='positions' ? (
                <div className="pd-table-wrap">
                  {positions.length===0 ? <p className="pd-muted" style={{padding:14}}>No open simulated positions.</p> : (
                    <table className="pd-table"><thead><tr><th>Instrument</th><th>Side</th><th className="pd-right">Qty</th><th className="pd-right">Avg entry</th><th className="pd-right">Current mark</th><th className="pd-right">P/L</th></tr></thead><tbody>
                      {positions.map((p)=>(
                        <tr key={p.id}>
                          <td>{p.symbol}</td>
                          <td><span className="pd-chip pd-chip--buy">LONG</span></td>
                          <td className="pd-right pd-mono">{formatInt(p.quantity)}</td>
                          <td className="pd-right pd-mono">₹{formatMoney(p.avg_price)}</td>
                          <td className="pd-right pd-mono">{p.market_value!=null && p.quantity ? `₹${formatMoney(p.market_value/p.quantity)}` : '—'}</td>
                          <td className={`pd-right pd-mono ${pnlClass(p.unrealized_pnl)}`}>{p.unrealized_pnl==null?'—':formatSignedMoney(p.unrealized_pnl)}</td>
                        </tr>
                      ))}
                    </tbody></table>
                  )}
                </div>
              ) : (
                <div className="pd-table-wrap">
                  {orders.length===0 ? <p className="pd-muted" style={{padding:14}}>No simulated orders yet.</p> : (
                    <table className="pd-table"><thead><tr><th>Bar date</th><th>Instrument</th><th>Side</th><th className="pd-right">Qty</th><th className="pd-right">Fill price</th><th>Status</th><th>Note</th></tr></thead><tbody>
                      {orders.map((o)=>(
                        <tr key={o.id}>
                          <td className="pd-mono">{formatDate(o.bar_date)}</td>
                          <td>{o.symbol}</td>
                          <td><span className={`pd-chip ${o.side==='BUY'?'pd-chip--buy':'pd-chip--sell'}`}>{o.side}</span></td>
                          <td className="pd-right pd-mono">{formatInt(o.quantity)}</td>
                          <td className="pd-right pd-mono">₹{formatMoney(o.price)}</td>
                          <td><StatusBadge status={o.status} /></td>
                          <td className="pd-muted">{o.note || '—'}</td>
                        </tr>
                      ))}
                    </tbody></table>
                  )}
                </div>
              )}
            </div>
          </section>

          {selected && (
            <section className="pd-panel" aria-label="Deployment details and charts">
              <div className="pd-panel__head">
                <h2 className="pd-panel__title">Execution history, charts &amp; controls</h2>
                <span className="pd-muted">Preserved paper-trading functionality</span>
              </div>
              <div className="pd-panel__body">
                {tickResult && (
                  <Note tone={tickResult.warmup_mode ? 'info' : tickResult.action === 'HOLD' ? 'warning' : 'success'} title={`Paper tick ${tickResult.bar_date}: ${tickResult.action}${tickResult.warmup_mode ? ' — warmup' : ''}`}>
                    <span>Signal {tickResult.signal} → {tickResult.action}. {tickResult.warmup_mode ? 'Warmup mode — indicator history insufficient.' : ''} {tickResult.note ?? ''} {tickResult.order_status === 'rejected' ? '(order stored as rejected)' : ''}</span>
                  </Note>
                )}
                {tickError && <Note tone="danger" title="Paper tick failed" reasons={tickError.reasons}><span>{errMsg(tickError)}</span></Note>}
                <PaperDeploymentDetails key={selected.id} deployment={selected} onChanged={refreshAll} />
              </div>
            </section>
          )}

          <section className="pd-panel" aria-label="Deployment history">
            <div className="pd-panel__head">
              <h2 className="pd-panel__title">Deployment history</h2>
              <button type="button" className="paper-desk__btn paper-desk__btn--sm" onClick={()=>setHistoryOpen(v=>!v)}>{historyOpen ? 'Hide' : 'Show'} ({historyDeployments.length})</button>
            </div>
            {historyOpen && (
              <div className="pd-panel__body" style={{padding:0}}>
                {listLoading ? <p className="pd-muted" style={{padding:14}}>Loading…</p> : historyDeployments.length===0 ? <p className="pd-muted" style={{padding:14}}>No stopped deployments yet.</p> : (
                  <div className="pd-table-wrap"><table className="pd-table"><thead><tr><th>Strategy</th><th>Status</th><th className="pd-right">Starting cash</th><th className="pd-right">Equity</th><th className="pd-right">Trades</th><th>Deployed</th><th>Stopped</th></tr></thead><tbody>
                    {historyDeployments.map((d)=>(
                      <tr key={d.id} onClick={()=>setSelectedId(d.id)} style={{cursor:'pointer'}}>
                        <td><Link to={`/strategies/${d.strategy_id}`} onClick={(e)=>e.stopPropagation()}>{d.strategy_name ?? d.strategy_id}</Link></td>
                        <td><StatusBadge status={d.status} /></td>
                        <td className="pd-right pd-mono">{d.starting_cash==null?'—':`₹${formatMoney(d.starting_cash)}`}</td>
                        <td className="pd-right pd-mono">{d.equity==null?'—':`₹${formatMoney(d.equity)}`}</td>
                        <td className="pd-right pd-mono">{d.completed_trades ?? '—'}</td>
                        <td className="pd-mono">{formatDateTime(d.deployed_at)}</td>
                        <td className="pd-mono">{formatDateTime(d.stopped_at)}</td>
                      </tr>
                    ))}
                  </tbody></table></div>
                )}
              </div>
            )}
          </section>
        </main>

        <aside className="paper-desk__order" aria-label="Order entry and execution">
          <section className="pd-panel">
            <div className="pd-panel__head">
              <h2 className="pd-panel__title">Order entry</h2>
              <span className="pd-faint">Simulated</span>
            </div>
            <div className="pd-panel__body">
              <div>
                <div className="paper-desk__label">Buying power</div>
                <div className="paper-desk__kv-v" style={{fontSize:18}}>{buyingPower==null?'—':`₹${formatMoney(buyingPower)}`}</div>
              </div>

              <div className="paper-desk__seg" role="group" aria-label="Side">
                <button type="button" className="paper-desk__seg-btn paper-desk__seg-btn--buy paper-desk__seg-btn--active" disabled title="Side determined by strategy signal">Buy / Long</button>
                <button type="button" className="paper-desk__seg-btn paper-desk__seg-btn--sell" disabled title={positions.length===0?'No short/borrow capability in current simulation':'Sell follows strategy signal'}>Sell</button>
              </div>

              <div className="paper-desk__field">
                <label className="paper-desk__label" htmlFor="pd-instrument">Instrument</label>
                <select id="pd-instrument" className="paper-desk__select" value={selected?.id || ''} onChange={(e)=>setSelectedId(e.target.value)}>
                  {deployments.length===0 && <option value="">No deployments</option>}
                  {activeDeployments.length>0 && <optgroup label="Active">
                    {activeDeployments.map(d=> <option key={d.id} value={d.id}>{d.strategy_name || d.strategy_id} · {d.market||'NIFTY50'}</option>)}
                  </optgroup>}
                  {historyDeployments.length>0 && <optgroup label="History">
                    {historyDeployments.map(d=> <option key={d.id} value={d.id}>{d.strategy_name || d.strategy_id} · {d.market||'NIFTY50'}</option>)}
                  </optgroup>}
                </select>
              </div>

              <div className="paper-desk__price-card">
                <div className="paper-desk__label">{selected?.market || 'Instrument'} · Processed mark</div>
                <div className="paper-desk__price-main">{lastBar ? `₹${formatMoney(lastBar.close)}` : '—'}</div>
                <div className={`pd-muted ${pnlClass(instrumentMovePct)}`} style={{marginTop:4}}>
                  {instrumentMovePct==null ? 'No live feed; uses processed bar data' : `${instrumentMovePct>=0?'+':''}${instrumentMovePct.toFixed(2)}% vs prior processed bar`}
                </div>
                <div className="pd-faint" style={{marginTop:4}}>Bid/Ask: — (not provided by simulated data)</div>
              </div>

              <div className="paper-desk__field">
                <label className="paper-desk__label" htmlFor="pd-ordertype">Order type</label>
                <select id="pd-ordertype" className="paper-desk__select" disabled><option>Simulated market (strategy tick)</option></select>
              </div>

              <div className="paper-desk__field">
                <span className="paper-desk__label">Quantity</span>
                <div className="paper-desk__qty">
                  <button type="button" className="paper-desk__qty-btn" disabled title="Quantity determined by strategy/sizer">−</button>
                  <input className="paper-desk__input" value="Strategy-determined" readOnly aria-label="Quantity" />
                  <button type="button" className="paper-desk__qty-btn" disabled title="Quantity determined by strategy/sizer">+</button>
                </div>
              </div>

              <div className="paper-desk__field">
                <div className="paper-desk__label">Estimated order value</div>
                <div className="paper-desk__kv-v">{(lastBar && positions[0]?.quantity) ? `₹${formatMoney(lastBar.close * positions[0].quantity)} (open position ref)` : '— (determined at tick execution)'}</div>
              </div>

              <p className="paper-desk__note">
                Execution uses the existing simulated paper-trading backend. “Run paper tick” advances the next cached bar through the strategy; orders/fills come from strategy signals (no broker, no real money).
              </p>

              <button type="button" className="paper-desk__btn paper-desk__btn--primary paper-desk__btn--block" onClick={handleTick} disabled={!isActive || tickBusy}>
                {tickBusy ? 'Running paper tick…' : isActive ? 'Run paper tick' : 'Deployment not active'}
              </button>

              {isActive && (
                <button type="button" className="paper-desk__btn paper-desk__btn--danger paper-desk__btn--block" onClick={()=>askStop(selected)}>Stop paper trading</button>
              )}

              <Link className="paper-desk__btn paper-desk__btn--block" to="/strategies">View approved strategies</Link>

              {stopTarget && (
                <div style={{borderTop:'1px solid var(--pd-border)', paddingTop:10, display:'flex', flexDirection:'column', gap:8}}>
                  <div className="paper-desk__label">Stop {stopTarget.strategy_name || 'deployment'}</div>
                  <input className="paper-desk__input" placeholder="Reason (optional)" maxLength={500} value={stopReason} onChange={(e)=>setStopReason(e.target.value)} disabled={stopBusy} />
                  {stopError && <div className="paper-desk__error">{errMsg(stopError)}</div>}
                  <div style={{display:'flex', gap:8}}>
                    <button type="button" className="paper-desk__btn paper-desk__btn--danger paper-desk__btn--sm" onClick={confirmStop} disabled={stopBusy}>{stopBusy?'Stopping…':'Confirm stop'}</button>
                    <button type="button" className="paper-desk__btn paper-desk__btn--sm" onClick={cancelStop} disabled={stopBusy}>Cancel</button>
                  </div>
                </div>
              )}
            </div>
          </section>

          <section className="pd-panel">
            <div className="pd-panel__head"><h2 className="pd-panel__title">Deployments</h2></div>
            <div className="pd-panel__body">
              <div className="paper-desk__dep-list">
                {listLoading ? <p className="pd-muted">Loading…</p> : deployments.length===0 ? <p className="pd-muted">No paper deployments.</p> : deployments.map((d)=>(
                  <button type="button" key={d.id} className={`paper-desk__dep${d.id===selectedId?' paper-desk__dep--active':''}`} onClick={()=>setSelectedId(d.id)}>
                    <span className="paper-desk__dep-name">{d.strategy_name || d.strategy_id}</span>
                    <span className={`paper-desk__dep-pnl ${pnlClass(d.total_pnl)}`}>{d.total_pnl==null?'—':formatSignedMoney(d.total_pnl)}</span>
                    <span className="paper-desk__dep-meta">{d.market||'—'} · {d.status} · {d.completed_trades ?? 0} trades</span>
                  </button>
                ))}
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
