import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BACKTEST_TIMEOUT_MS, fetchBacktestResults, runBacktest } from '../lib/api.js'
import { canPerform, explainUnavailable } from '../lib/actions.js'
import { formatDateTime, formatMoney, formatPercent, formatRatio, formatSignedMoney, formatSignedPercent, humanizeWarning } from '../lib/format.js'
import { removeCachedBacktest, setCachedBacktest } from '../lib/storage.js'
import { useCachedBacktest, useStrategyDetail } from '../lib/useStrategy.js'
import { useElapsedTimer } from '../lib/useElapsedTimer.js'
import BenchmarkVerdict from '../components/BenchmarkVerdict.jsx'
import Disclosure from '../components/Disclosure.jsx'
import DrawdownChart from '../components/DrawdownChart.jsx'
import EquityChart from '../components/EquityChart.jsx'
import Note from '../components/Note.jsx'
import StrategyTabs from '../components/StrategyTabs.jsx'
import TradeTable from '../components/TradeTable.jsx'
import ElapsedTimer from '../components/ElapsedTimer.jsx'
import LoadingBlock, { SkeletonBlock, SkeletonMetrics, SkeletonTitle } from '../components/Skeletons.jsx'
import './BacktestPage.css'

const DEFAULTS = { cash: 100000, commissionPct: 0.1, sizerPercent: 95, slippagePct: 0 }

function validate(values) {
  const errors = {}
  if (!Number.isFinite(values.cash) || values.cash <= 0) errors.cash = 'Cash must be greater than 0.'
  if (!Number.isFinite(values.commissionPct) || values.commissionPct <= 0 || values.commissionPct >= 100) {
    errors.commissionPct = 'Commission must be a percentage greater than 0 and less than 100.'
  }
  if (!Number.isFinite(values.sizerPercent) || values.sizerPercent <= 0 || values.sizerPercent >= 100) {
    errors.sizerPercent = 'Position size must be a percentage greater than 0 and less than 100.'
  }
  if (!Number.isFinite(values.slippagePct) || values.slippagePct < 0 || values.slippagePct >= 100) {
    errors.slippagePct = 'Slippage must be a percentage between 0 and 100.'
  }
  return errors
}


function KpiCard({ label, value, tone = 'neutral' }) {
  return (
    <div className="bt-v2-kpi-card">
      <div className="bt-v2-kpi-label">{label}</div>
      <div className={`bt-v2-kpi-value ${tone === 'pos' ? 'is-pos' : tone === 'neg' ? 'is-neg' : ''}`}>{value ?? 'N/A'}</div>
    </div>
  )
}

export default function BacktestPage() {
  const { id } = useParams()
  const { detail, status, loading, notFound } = useStrategyDetail(id)
  const cached = useCachedBacktest(id)

  const [values] = useState(DEFAULTS)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [ranAt, setRanAt] = useState(cached?.ranAt ?? null)
  const [showRaw, setShowRaw] = useState(false)
  const [activeTab, setActiveTab] = useState('summary')
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [selectedHistId, setSelectedHistId] = useState(null)
  const [histQuery, setHistQuery] = useState('')

  const abortRef = useRef(null)
  const elapsed = useElapsedTimer(running)
  const errors = useMemo(() => validate(values), [values])
  const invalid = Object.keys(errors).length > 0

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setHistoryLoading(true)
    fetchBacktestResults(id)
      .then((rows) => { if (!cancelled) setHistory(Array.isArray(rows) ? rows : []) })
      .catch(() => { if (!cancelled) setHistory([]) })
      .finally(() => { if (!cancelled) setHistoryLoading(false) })
    return () => { cancelled = true }
  }, [id, result, ranAt])


  const selectedHist = selectedHistId ? history.find((h) => h.id === selectedHistId) : null
  const shown = result ?? selectedHist ?? cached?.result ?? null
  const shownAt = ranAt ?? (selectedHist ? (selectedHist.created_at || null) : (cached?.ranAt ?? null))
  const isCached = !result && !selectedHist && Boolean(cached?.result)
  const warnings = shown?.warnings ?? []
  const noTradesWarning = warnings.some((w) => w === 'no_trades')

  const monthlyReturns = useMemo(() => {
    if (Array.isArray(shown?.monthly_returns) && shown.monthly_returns.length > 0) {
      return [...shown.monthly_returns]
        .map((m) => ({ month: String(m?.month ?? ''), ret: Number(m?.ret_pct ?? m?.ret) }))
        .filter((m) => /^\d{4}-\d{2}$/.test(m.month) && Number.isFinite(m.ret))
        .sort((a, b) => a.month.localeCompare(b.month))
    }
    const curve = shown?.equity_curve
    if (!Array.isArray(curve) || curve.length < 2) return []
    const byMonth = new Map()
    curve.forEach(([date, value]) => {
      if (!date || typeof value !== 'number') return
      const key = String(date).slice(0, 7)
      if (!/^\d{4}-\d{2}$/.test(key)) return
      if (!byMonth.has(key)) byMonth.set(key, { start: value, end: value })
      else byMonth.get(key).end = value
    })
    return Array.from(byMonth.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([month, v]) => ({ month, ret: v.start ? ((v.end / v.start) - 1) * 100 : 0 }))
  }, [shown])

  const yearlyReturns = useMemo(() => {
    if (Array.isArray(shown?.yearly_returns) && shown.yearly_returns.length > 0) {
      return [...shown.yearly_returns]
        .map((y) => ({ year: String(y?.year ?? ''), ret: Number(y?.ret_pct ?? y?.ret) }))
        .filter((y) => /^\d{4}$/.test(y.year) && Number.isFinite(y.ret))
        .sort((a, b) => a.year.localeCompare(b.year))
    }
    const byYear = new Map()
    monthlyReturns.forEach((m) => {
      const y = String(m.month).slice(0, 4)
      if (!/^\d{4}$/.test(y)) return
      byYear.set(y, (byYear.get(y) || 1) * (1 + (Number(m.ret) || 0) / 100))
    })
    return Array.from(byYear.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([year, factor]) => ({ year, ret: (factor - 1) * 100 }))
  }, [shown, monthlyReturns])

  function handleExport() {
    const data = shown
    if (!data) return
    const metrics = [['Metric', 'Value'], ['Total Return %', data.total_return_pct], ['Benchmark Return %', data.benchmark_return_pct], ['CAGR %', data.cagr_pct], ['Max Drawdown %', data.max_drawdown_pct], ['Sharpe', data.sharpe], ['Sortino', data.sortino], ['Win Rate %', data.win_rate_pct], ['Num Trades', data.num_trades], ['Profit Factor', data.profit_factor], ['Avg Win', data.avg_win], ['Avg Loss', data.avg_loss], ['Avg Trade PnL', data.avg_trade_pnl], ['Expectancy', data.expectancy]]
    const trades = data.trades || []
    const tradeHeader = ['Entry Date', 'Exit Date', 'Direction', 'Size', 'Entry Price', 'Exit Price', 'Bars Held', 'PnL Net', 'Won']
    const tradeRows = trades.map(t => [t.entry_date, t.exit_date, t.direction, t.size, t.entry_price, t.exit_price, t.bars_held, t.pnl_net, t.won])
    const csv = [metrics.map(r => r.join(',')).join('\n'), '\n\nTrades\n' + [tradeHeader.join(',')].concat(tradeRows.map(r => r.join(','))).join('\n')].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `backtest-${id}-${new Date().toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(url)
  }

  async function handleRun() {
    if (running || invalid) return
    setRunning(true); setError(null); setShowRaw(false)
    const controller = new AbortController(); abortRef.current = controller
    const timer = setTimeout(() => controller.abort(), BACKTEST_TIMEOUT_MS)
    try {
      const data = await runBacktest(id, values, { signal: controller.signal })
      setResult(data); setRanAt(new Date().toISOString()); setCachedBacktest(id, data); setSelectedHistId(null); setError(null)
    } catch (err) {
      if (err?.name === 'AbortError') setError({ message: 'The backtest exceeded the backend 120-second limit and was cancelled.', reasons: [] })
      else setError({ message: err?.message ?? 'Request failed.', reasons: err?.reasons ?? [] })
    } finally { clearTimeout(timer); abortRef.current = null; setRunning(false) }
  }
  function handleCancel() { abortRef.current?.abort() }
  function handleDiscard() { removeCachedBacktest(id); setResult(null); setRanAt(null); setError(null) }
  function handleNewRun() { setResult(null); setSelectedHistId(null); setError(null); setRanAt(null); setShowRaw(false) }

  if (loading) return <div className="bt-v2"><div className="bt-v2-container"><LoadingBlock label="Loading strategy"><div className="stack"><SkeletonTitle /><SkeletonBlock height={90} /></div></LoadingBlock></div></div>
  if (notFound || !detail) return <div className="bt-v2"><div className="bt-v2-container"><Note tone="danger" title="Strategy not found"><span>The backend has no strategy with id {id}.</span></Note><div><Link className="btn" to="/strategies">Back to library</Link></div></div></div>

  const allowed = canPerform(status, 'backtest')
  const tradesArr = Array.isArray(shown?.trades) ? shown.trades : []
  const winsCount = tradesArr.filter((t) => Number(t.pnl_net) > 0).length
  const lossesCount = tradesArr.filter((t) => Number(t.pnl_net) < 0).length
  const breakEvenCount = tradesArr.filter((t) => Number(t.pnl_net) === 0).length
  const grossProfit = tradesArr.filter((t) => Number(t.pnl_net) > 0).reduce((a, t) => a + Number(t.pnl_net || 0), 0)
  const grossLossAbs = Math.abs(tradesArr.filter((t) => Number(t.pnl_net) < 0).reduce((a, t) => a + Number(t.pnl_net || 0), 0))
  const netProfit = (shown?.raw_metrics?.value_end != null && shown?.raw_metrics?.value_start != null) ? Number(shown.raw_metrics.value_end) - Number(shown.raw_metrics.value_start) : null
  const netProfitPct = shown?.total_return_pct
  const avgWin = shown?.avg_win ?? (winsCount ? grossProfit / winsCount : null)
  const avgLoss = shown?.avg_loss ?? (lossesCount ? tradesArr.filter((t) => Number(t.pnl_net) < 0).reduce((a, t) => a + Number(t.pnl_net || 0), 0) / lossesCount : null)
  const cagr = shown?.cagr_pct
  const maxDD = shown?.max_drawdown_pct
  const mar = (Number.isFinite(Number(cagr)) && Number.isFinite(Number(maxDD)) && Number(maxDD) !== 0) ? (Number(cagr) / Number(maxDD)) : (shown?.raw_metrics?.calmar ?? null)
  const commissionNote = (shown?.raw_metrics?.commission != null) ? formatMoney(shown.raw_metrics.commission) : (Number.isFinite(values.commissionPct) ? `${values.commissionPct}% rate` : 'N/A')
  const ulcer = shown?.ulcer_index ?? shown?.raw_metrics?.ulcer_index ?? null
  const recoveryTime = shown?.recovery_time ?? shown?.raw_metrics?.recovery_time ?? null
  const filteredHistory = history.filter((h) => {
    const q = histQuery.trim().toLowerCase()
    if (!q) return true
    return String(h.id || '').toLowerCase().includes(q) || formatDateTime(h.created_at).toLowerCase().includes(q)
  })

  const segTabs = [{ key: 'summary', label: 'Summary' }, { key: 'dates', label: 'Dates' }, { key: 'analysis', label: 'Analysis' }]

  return (
    <div className="bt-v2"><div className="bt-v2-container bt-v2-container--wide">
      <div className="bt-v2-topbar">
        <div>
          <nav className="bt-v2-breadcrumb" aria-label="Breadcrumb"><Link to="/strategies">Strategies</Link><span aria-hidden="true">/</span><Link to={`/strategies/${id}`}>{detail.name}</Link><span aria-hidden="true">/</span><span>Backtest</span></nav>
          <h1 className="bt-v2-title">{detail.name}</h1>
          {shownAt && <p className="bt-v2-subtitle">Result from {formatDateTime(shownAt)}{isCached ? ' (cached)' : selectedHist ? ' (history)' : ''}</p>}
        </div>
        <div className="bt-v2-top-actions">
          <button type="button" className="bt-v2-btn-export" onClick={handleExport} disabled={!shown}>Export CSV</button>
          <StrategyTabs strategyId={id} />
        </div>
      </div>

      <div className="bt-v2-shell">
        <aside className="bt-v2-card bt-v2-history-panel" aria-label="Backtest History">
          <div className="bt-v2-history-head">
            <h3 className="bt-v2-card-title">Backtest History</h3>
            <button type="button" className="bt-v2-btn-run bt-v2-btn-run--sm" onClick={handleNewRun}>New Run</button>
          </div>
          <input className="bt-v2-search" placeholder="Search Runs" value={histQuery} onChange={(e) => setHistQuery(e.target.value)} />
          <div className="bt-v2-history-list">
            {historyLoading && <div className="bt-v2-muted">Loading…</div>}
            {!historyLoading && filteredHistory.length === 0 && <div className="bt-v2-muted">No saved runs.</div>}
            {filteredHistory.map((h, idx) => {
              const active = selectedHistId ? selectedHistId === h.id : (!result && idx === 0 && cached?.result == null)
              const ret = h.total_return_pct
              const dd = h.max_drawdown_pct
              return (
                <button key={h.id || idx} type="button" className={`bt-v2-history-item ${active ? 'is-active' : ''}`} onClick={() => { setSelectedHistId(h.id || null); setResult(null); setRanAt(h.created_at || null); setError(null) }}>
                  <div className="bt-v2-history-top"><span className="bt-v2-history-name">Run {String(h.id || '').slice(0, 8) || idx + 1}</span><span className={`bt-v2-pill ${Number(ret) >= 0 ? 'is-pos' : 'is-neg'}`}>{formatSignedPercent(ret, 2)}</span></div>
                  <div className="bt-v2-history-meta">DD {formatPercent(dd, 2)} · {Number.isFinite(Number(h.num_trades)) ? Number(h.num_trades) : 0} trades</div>
                  <div className="bt-v2-history-meta">{formatDateTime(h.created_at)}</div>
                </button>
              )
            })}
          </div>
          <div className="bt-v2-actions" style={{ marginTop: 10 }}>
            <button type="button" className="bt-v2-btn-run" onClick={handleRun} disabled={running || invalid || !allowed} style={{ width: '100%' }}>{running ? 'Running…' : 'Run Backtest'}</button>
            {running && <button type="button" className="bt-v2-btn-secondary" onClick={handleCancel} style={{ width: '100%' }}>Cancel</button>}
            {isCached && !running && <button type="button" className="bt-v2-btn-secondary" onClick={handleDiscard} style={{ width: '100%' }}>Discard</button>}
          </div>
        </aside>

        <main className="bt-v2-main">
          <div className="bt-v2-seg-tabs" role="tablist" aria-label="Backtest sections" style={{ marginBottom: 12 }}>
            {segTabs.map((t) => <button key={t.key} type="button" role="tab" aria-selected={activeTab === t.key} className={`bt-v2-seg-tab ${activeTab === t.key ? 'is-active' : ''}`} onClick={() => setActiveTab(t.key)}>{t.label}</button>)}
          </div>

          {!allowed && <Note tone="warning" title={`Not available at status "${status}"`}>{explainUnavailable(status, 'backtest')}</Note>}
          {error && <Note tone="danger" title="Backtest failed" reasons={error.reasons}><span>{typeof error === 'string' ? error : error.message}</span></Note>}
          {running && !shown && <div className="bt-v2-card"><LoadingBlock label="Running backtest"><div className="stack"><div className="running-state"><span className="spinner-inline" /><span>Running backtest…</span><ElapsedTimer seconds={elapsed} /></div><SkeletonMetrics /><SkeletonBlock height={180} /></div></LoadingBlock></div>}
          {!running && !shown && <div className="bt-v2-card bt-v2-empty">No backtest selected. Run a new backtest or pick one from history.</div>}

          {shown && activeTab === 'summary' && (<>
            <div className="bt-v2-kpi-grid bt-v2-kpi-grid--10">
              <KpiCard label="CAGR" value={formatPercent(cagr, 2)} tone={Number(cagr) >= 0 ? 'pos' : 'neg'} />
              <KpiCard label="MAR (CAGR + MaxDD)" value={formatRatio(mar)} tone={Number(mar) >= 0 ? 'pos' : 'neg'} />
              <KpiCard label="Net Profit" value={netProfit != null ? formatSignedMoney(netProfit) : 'N/A'} tone={Number(netProfit) >= 0 ? 'pos' : 'neg'} />
              <KpiCard label="Max Drawdown" value={formatPercent(maxDD, 2)} tone="neg" />
              <KpiCard label="Win Rate" value={formatPercent(shown.win_rate_pct, 1)} />
              <KpiCard label="Profit Factor" value={formatRatio(shown.profit_factor)} />
              <KpiCard label="Sharpe Ratio" value={formatRatio(shown.sharpe)} />
              <KpiCard label="Sortino Ratio" value={formatRatio(shown.sortino)} />
              <KpiCard label="Total Return" value={formatPercent(netProfitPct, 2)} tone={Number(netProfitPct) >= 0 ? 'pos' : 'neg'} />
              <KpiCard label="Average Trade P&L" value={shown.avg_trade_pnl != null ? formatSignedMoney(shown.avg_trade_pnl) : 'N/A'} tone={Number(shown.avg_trade_pnl) >= 0 ? 'pos' : 'neg'} />
            </div>

            <div className="bt-v2-card bt-v2-performance">
              <div className="bt-v2-perf-head"><h3 className="bt-v2-card-title-lg">Equity Curve</h3></div>
              {noTradesWarning && (shown?.total_return_pct ?? 0) !== 0 && <Note tone="warning" title="Zero trades, non-zero return">The strategy placed no trades yet still reports a {Number(shown.total_return_pct).toFixed(2)}% return.</Note>}
              <div className="bt-v2-chart-wrap bt-v2-chart-wrap--equity"><EquityChart curve={shown.equity_curve} /></div>
            </div>

            <div className="bt-v2-breakdown">
              <div className="bt-v2-card"><h3 className="bt-v2-card-title">P&amp;L Analysis</h3>
                <div className="bt-v2-kv"><span>Net Profit</span><b>{netProfit != null ? formatSignedMoney(netProfit) : 'N/A'}</b></div>
                <div className="bt-v2-kv"><span>Net Profit %</span><b>{formatPercent(netProfitPct, 2)}</b></div>
                <div className="bt-v2-kv"><span>Gross Profit</span><b>{formatSignedMoney(grossProfit)}</b></div>
                <div className="bt-v2-kv"><span>Gross Loss</span><b>{grossLossAbs ? `-${formatMoney(grossLossAbs)}` : formatMoney(0)}</b></div>
                <div className="bt-v2-kv"><span>Commissions</span><b>{commissionNote}</b></div>
              </div>
              <div className="bt-v2-card"><h3 className="bt-v2-card-title">Risk Analysis</h3>
                <div className="bt-v2-kv"><span>Max Drawdown</span><b>{formatPercent(maxDD, 2)}</b></div>
                <div className="bt-v2-kv"><span>Sharpe Ratio</span><b>{formatRatio(shown.sharpe)}</b></div>
                <div className="bt-v2-kv"><span>Sortino Ratio</span><b>{formatRatio(shown.sortino)}</b></div>
                <div className="bt-v2-kv"><span>Ulcer Index</span><b>{ulcer != null ? formatRatio(ulcer) : 'N/A'}</b></div>
                <div className="bt-v2-kv"><span>Recovery Time</span><b>{recoveryTime != null ? String(recoveryTime) : 'N/A'}</b></div>
              </div>
              <div className="bt-v2-card"><h3 className="bt-v2-card-title">Trade Statistics</h3>
                <div className="bt-v2-kv"><span>Total Trades</span><b>{Number.isFinite(Number(shown.num_trades)) ? Number(shown.num_trades) : tradesArr.length}</b></div>
                <div className="bt-v2-kv"><span>Winning</span><b>{winsCount}</b></div>
                <div className="bt-v2-kv"><span>Losing</span><b>{lossesCount}</b></div>
                <div className="bt-v2-kv"><span>Break-even</span><b>{breakEvenCount}</b></div>
                <div className="bt-v2-kv"><span>Average Win</span><b>{avgWin != null ? formatSignedMoney(avgWin) : 'N/A'}</b></div>
                <div className="bt-v2-kv"><span>Average Loss</span><b>{avgLoss != null ? formatSignedMoney(avgLoss) : 'N/A'}</b></div>
              </div>
            </div>

            <div className="bt-v2-card">
              <h3 className="bt-v2-card-title">Drawdown Analysis</h3>
              <div className="bt-v2-chart-wrap bt-v2-chart-wrap--drawdown"><DrawdownChart curve={shown.drawdown_curve} equityCurve={shown.equity_curve} /></div>
            </div>

            {warnings.length > 0 && <Note tone="warning" title={`${warnings.length} warning${warnings.length === 1 ? '' : 's'}`}><ul>{warnings.map((w, i) => <li key={i}>{humanizeWarning(w)}</li>)}</ul></Note>}
            <BenchmarkVerdict result={shown} />
          </>)}

          {shown && activeTab === 'dates' && (
            <div className="bt-v2-card"><h3 className="bt-v2-card-title">Date-based Performance</h3>
              <div className="bt-v2-dates-grid">
                <div><h4 className="bt-v2-subhead">Monthly Returns</h4><div className="bt-v2-table-wrap bt-v2-table-wrap--scroll"><table className="bt-v2-table"><thead><tr><th>Month</th><th className="num">Return %</th></tr></thead><tbody>{monthlyReturns.length === 0 ? <tr><td colSpan="2" className="bt-v2-muted">N/A</td></tr> : monthlyReturns.map((m) => <tr key={m.month}><td>{m.month}</td><td className={`num ${Number(m.ret) >= 0 ? 'bt-v2-cell-pos' : 'bt-v2-cell-neg'}`}>{formatPercent(m.ret, 2)}</td></tr>)}</tbody></table></div></div>
                <div><h4 className="bt-v2-subhead">Yearly Returns</h4><div className="bt-v2-table-wrap bt-v2-table-wrap--scroll"><table className="bt-v2-table"><thead><tr><th>Year</th><th className="num">Return %</th></tr></thead><tbody>{yearlyReturns.length === 0 ? <tr><td colSpan="2" className="bt-v2-muted">N/A</td></tr> : yearlyReturns.map((y) => <tr key={y.year}><td>{y.year}</td><td className={`num ${Number(y.ret) >= 0 ? 'bt-v2-cell-pos' : 'bt-v2-cell-neg'}`}>{formatPercent(y.ret, 2)}</td></tr>)}</tbody></table></div></div>
              </div>
            </div>
          )}

          {shown && activeTab === 'analysis' && (
            <div className="bt-v2-card"><h3 className="bt-v2-card-title">Detailed Analysis</h3>
              <div className="bt-v2-dates-grid" style={{ marginBottom: 16 }}>
                <div className="bt-v2-card bt-v2-card--inner"><h4 className="bt-v2-subhead">Performance</h4>
                  <div className="bt-v2-kv"><span>Total Return</span><b>{formatPercent(netProfitPct, 2)}</b></div>
                  <div className="bt-v2-kv"><span>CAGR</span><b>{formatPercent(cagr, 2)}</b></div>
                  <div className="bt-v2-kv"><span>Benchmark Return</span><b>{formatPercent(shown.benchmark_return_pct, 2)}</b></div>
                </div>
                <div className="bt-v2-card bt-v2-card--inner"><h4 className="bt-v2-subhead">Risk</h4>
                  <div className="bt-v2-kv"><span>Max Drawdown</span><b>{formatPercent(maxDD, 2)}</b></div>
                  <div className="bt-v2-kv"><span>Sharpe Ratio</span><b>{formatRatio(shown.sharpe)}</b></div>
                  <div className="bt-v2-kv"><span>Sortino Ratio</span><b>{formatRatio(shown.sortino)}</b></div>
                </div>
              </div>
              <Disclosure title="Trades" meta={`${shown.num_trades === 0 ? '0' : (shown.num_trades ?? tradesArr.length)} closed trades`} defaultOpen>
                <TradeTable trades={shown.trades} truncated={shown.trades_truncated} />
              </Disclosure>
              {shown.raw_metrics && <div style={{ marginTop: 12 }}><button type="button" className="btn btn--ghost btn--sm" onClick={() => setShowRaw((v) => !v)}>{showRaw ? 'Hide' : 'Show'} Raw Metrics JSON</button>{showRaw && <pre className="code-viewer__pre raw-metrics" style={{ marginTop: 8 }}><code>{JSON.stringify(shown.raw_metrics, null, 2)}</code></pre>}</div>}
            </div>
          )}
        </main>
      </div>


      <p className="disclaimer-text">Past performance does not guarantee future results. Educational prototype — paper trading only.</p>
    </div></div>
  )
}
