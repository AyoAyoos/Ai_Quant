import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createChart, CrosshairMode, LineStyle } from 'lightweight-charts'
import {
  AlertTriangle,
  Crosshair,
  Expand,
  Loader2,
  Maximize2,
  Minimize2,
  RefreshCw,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { fetchMarketChart } from '../lib/api.js'
import './LiveAlgoChart.css'

const TIMEFRAMES = [
  { key: '1m', label: '1m' },
  { key: '5m', label: '5m' },
  { key: '15m', label: '15m' },
  { key: '30m', label: '30m' },
  { key: '1h', label: '1h' },
  { key: '1d', label: '1D' },
  { key: '1w', label: '1W' },
]

const INDICATOR_TOGGLES = [
  { key: 'ema9', label: 'EMA 9', group: 'overlay' },
  { key: 'ema21', label: 'EMA 21', group: 'overlay' },
  { key: 'ema50', label: 'EMA 50', group: 'overlay' },
  { key: 'ema200', label: 'EMA 200', group: 'overlay' },
  { key: 'sma20', label: 'SMA 20', group: 'overlay' },
  { key: 'volume', label: 'Volume', group: 'panel' },
  { key: 'rsi', label: 'RSI 14', group: 'panel' },
  { key: 'macd', label: 'MACD', group: 'panel' },
]

const EMA_COLORS = {
  ema9: '#8b639b',
  ema21: '#403d88',
  ema50: '#af719d',
  ema200: '#b06a3c',
  sma20: '#1a4d8f',
}

const DEFAULT_INDICATORS = {
  ema9: true,
  ema21: true,
  ema50: true,
  ema200: false,
  sma20: false,
  volume: true,
  rsi: true,
  macd: true,
}

const INDEX_LABELS = {
  NIFTY50: 'NIFTY 50',
  BANKNIFTY: 'BANK NIFTY',
  SENSEX: 'SENSEX',
  FINNIFTY: 'FIN NIFTY',
  INDIAVIX: 'INDIA VIX',
  NIFTYIT: 'NIFTY IT',
}

const GRID_COLOR = '#efe9f4'
const BORDER_COLOR = '#e3d9e5'
const TEXT_COLOR = '#4a4360'
const UP_COLOR = '#1b6b4a'
const DOWN_COLOR = '#a01028'
const ACCENT = '#403d88'

const isDaily = (timeframe) => timeframe === '1d' || timeframe === '1w'

/** Date string in IST so a daily candle keeps its exchange date. */
function istDate(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleDateString('en-CA', {
    timeZone: 'Asia/Kolkata',
  })
}

function barTime(bar, timeframe) {
  return isDaily(timeframe) ? istDate(bar.time) : bar.time
}

/** Normalise a lightweight-charts logical time (string, number or business day). */
function timeKey(value) {
  if (value && typeof value === 'object' && value.year) {
    return `${value.year}-${String(value.month).padStart(2, '0')}-${String(value.day).padStart(2, '0')}`
  }
  return value
}

function istTimeLabel(value) {
  if (typeof value === 'string') {
    const parsed = new Date(`${value}T00:00:00+05:30`)
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        timeZone: 'Asia/Kolkata',
      })
    }
    return value
  }
  if (typeof value === 'number') {
    return new Date(value * 1000).toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  if (value && typeof value === 'object' && value.year) {
    return new Date(Date.UTC(value.year, value.month - 1, value.day)).toLocaleDateString(
      'en-IN',
      { day: '2-digit', month: 'short', timeZone: 'Asia/Kolkata' },
    )
  }
  return ''
}

function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatVolume(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const number = Number(value)
  if (number >= 1e7) return `${(number / 1e7).toFixed(2)} Cr`
  if (number >= 1e5) return `${(number / 1e5).toFixed(2)} L`
  if (number >= 1e3) return `${(number / 1e3).toFixed(1)} K`
  return number.toLocaleString('en-IN')
}

function formatStamp(unixSeconds, timeframe) {
  if (!unixSeconds) return '—'
  const date = new Date(unixSeconds * 1000)
  if (isDaily(timeframe)) {
    return date.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    })
  }
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

function pointsFrom(bars, values, timeframe) {
  if (!Array.isArray(values)) return []
  const points = []
  const length = Math.min(bars.length, values.length)
  for (let i = 0; i < length; i += 1) {
    const value = values[i]
    if (value === null || value === undefined || Number.isNaN(Number(value))) continue
    points.push({ time: barTime(bars[i], timeframe), value: Number(value) })
  }
  return points
}

function statusTone(status) {
  switch (status) {
    case 'LIVE':
    case 'OPEN':
      return 'live'
    case 'DELAYED':
    case 'PRE_OPEN':
    case 'PRE-OPEN':
      return 'delayed'
    case 'HISTORICAL':
    case 'CLOSED':
      return 'historical'
    case 'STALE':
      return 'stale'
    default:
      return 'unavailable'
  }
}

export default function LiveAlgoChart({ symbol = 'NIFTY50', quote = null, marketStatus = null }) {
  const rootRef = useRef(null)
  const mainRef = useRef(null)
  const volumeRef = useRef(null)
  const rsiRef = useRef(null)
  const macdRef = useRef(null)
  const chartsRef = useRef({})
  const crosshairRef = useRef(true)
  const dataRef = useRef(null)

  const [timeframe, setTimeframe] = useState('1d')
  const [chartType, setChartType] = useState('candle')
  const [indicators, setIndicators] = useState(DEFAULT_INDICATORS)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)
  const [hover, setHover] = useState(null)
  const [crosshairOn, setCrosshairOn] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const marketPhase = marketStatus?.status ?? null
  const displayName = quote?.name || INDEX_LABELS[symbol] || symbol

  // ---- Fetch the selected instrument's candles -------------------------
  useEffect(() => {
    const controller = new AbortController()
    let poller = null

    const load = async ({ quiet = false } = {}) => {
      if (!quiet) {
        setLoading(true)
        setError(null)
      }
      try {
        const result = await fetchMarketChart(symbol, {
          timeframe,
          limit: 500,
          signal: controller.signal,
        })
        if (controller.signal.aborted) return
        const bars = Array.isArray(result?.bars) ? result.bars : []
        if (!bars.length) {
          if (quiet && dataRef.current) return
          dataRef.current = null
          setData(null)
          setError(
            `The provider returned no ${timeframe.toUpperCase()} candles for ${displayName}. ` +
              'No synthetic candles are substituted.',
          )
        } else {
          dataRef.current = result
          setData(result)
          setError(null)
        }
      } catch (err) {
        if (controller.signal.aborted) return
        // Keep the last good chart visible during a failed background refresh.
        if (quiet && dataRef.current) return
        dataRef.current = null
        setData(null)
        setError(
          err?.message ||
            `Could not load ${timeframe.toUpperCase()} candles for ${displayName}.`,
        )
      } finally {
        if (!controller.signal.aborted && !quiet) setLoading(false)
      }
    }

    load()
    if (marketPhase === 'OPEN') {
      poller = window.setInterval(() => load({ quiet: true }), 30000)
    }
    return () => {
      controller.abort()
      if (poller) window.clearInterval(poller)
    }
  }, [symbol, timeframe, retryKey, marketPhase, displayName])

  const bars = data?.bars ?? []
  const indicatorData = data?.indicators ?? null
  const lastBar = bars.length ? bars[bars.length - 1] : null

  const headerPrice = quote?.price ?? lastBar?.close ?? null
  const headerChange =
    quote?.change ??
    (bars.length > 1 ? lastBar.close - bars[bars.length - 2].close : null)
  const headerChangePct =
    quote?.change_pct ??
    (headerChange !== null && bars.length > 1
      ? (headerChange / bars[bars.length - 2].close) * 100
      : null)

  const headerDataStatus = useMemo(() => {
    if (quote?.status === 'unavailable') return data?.data_status || 'UNAVAILABLE'
    if (quote?.data_status) return quote.data_status
    if (data?.data_status) return data.data_status
    if (!bars.length) return 'UNAVAILABLE'
    return marketPhase === 'OPEN' ? 'LIVE' : 'HISTORICAL'
  }, [quote, data, bars.length, marketPhase])

  const lastUpdated = quote?.timestamp ?? lastBar?.time ?? null

  // ---- Build the chart, panels and indicator series --------------------
  useEffect(() => {
    const mainEl = mainRef.current
    if (!mainEl || !bars.length) return undefined

    const daily = isDaily(timeframe)
    const mobile = window.matchMedia('(max-width: 760px)').matches
    const sizes = {
      main: mobile ? 300 : 430,
      volume: mobile ? 72 : 92,
      rsi: mobile ? 92 : 112,
      macd: mobile ? 104 : 124,
    }

    const showVolume = indicators.volume
    const showRsi = indicators.rsi
    const showMacd = indicators.macd
    const timeAxisOnMain = !showVolume && !showRsi && !showMacd
    const timeAxisOnVolume = showVolume && !showRsi && !showMacd
    const timeAxisOnRsi = showRsi && !showMacd

    const timeFormatter = (value) => istTimeLabel(value)

    const baseOptions = (height, showTimeAxis) => ({
      width: mainEl.clientWidth || 800,
      height,
      layout: {
        background: { type: 'solid', color: '#ffffff' },
        textColor: TEXT_COLOR,
        fontFamily: "'Hanken Grotesk', -apple-system, BlinkMacSystemFont, sans-serif",
        fontSize: 11,
      },
      localization: { timeFormatter },
      grid: {
        vertLines: { color: GRID_COLOR },
        horzLines: { color: GRID_COLOR },
      },
      crosshair: {
        mode: crosshairRef.current ? CrosshairMode.Normal : CrosshairMode.Hidden,
        vertLine: {
          color: '#8b639b',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: ACCENT,
        },
        horzLine: {
          color: '#8b639b',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: ACCENT,
        },
      },
      rightPriceScale: {
        borderColor: BORDER_COLOR,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderColor: BORDER_COLOR,
        timeVisible: !daily,
        secondsVisible: false,
        rightOffset: 5,
        barSpacing: daily ? 6 : 8,
        visible: showTimeAxis,
        tickMarkFormatter: timeFormatter,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    })

    const mainChart = createChart(mainEl, baseOptions(sizes.main, timeAxisOnMain))
    const chartMap = { main: mainChart }
    let priceSeries = null

    const barMap = new Map()
    bars.forEach((bar) => barMap.set(timeKey(barTime(bar, timeframe)), bar))

    if (chartType === 'line') {
      priceSeries = mainChart.addLineSeries({
        color: ACCENT,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4,
      })
      priceSeries.setData(
        bars.map((bar) => ({ time: barTime(bar, timeframe), value: bar.close })),
      )
    } else {
      priceSeries = mainChart.addCandlestickSeries({
        upColor: UP_COLOR,
        downColor: DOWN_COLOR,
        wickUpColor: 'rgba(27, 107, 74, 0.75)',
        wickDownColor: 'rgba(160, 16, 40, 0.75)',
        borderVisible: false,
        priceLineVisible: false,
      })
      priceSeries.setData(
        bars.map((bar) => ({
          time: barTime(bar, timeframe),
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
        })),
      )
    }

    // EMA / SMA overlays — computed by the backend from these same candles.
    const overlayKeys = ['ema9', 'ema21', 'ema50', 'ema200', 'sma20']
    overlayKeys.forEach((key) => {
      if (!indicators[key] || !indicatorData) return
      const points = pointsFrom(bars, indicatorData[key], timeframe)
      if (!points.length) return
      const line = mainChart.addLineSeries({
        color: EMA_COLORS[key],
        lineWidth: key === 'ema200' ? 1 : 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      line.setData(points)
    })

    // ---- Volume panel ---------------------------------------------------
    if (showVolume && volumeRef.current) {
      const volumeChart = createChart(
        volumeRef.current,
        baseOptions(sizes.volume, timeAxisOnVolume),
      )
      chartMap.volume = volumeChart
      const volumeSeries = volumeChart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceLineVisible: false,
        lastValueVisible: false,
      })
      volumeSeries.setData(
        bars.map((bar) => ({
          time: barTime(bar, timeframe),
          value: bar.volume || 0,
          color:
            bar.close >= bar.open
              ? 'rgba(27, 107, 74, 0.55)'
              : 'rgba(160, 16, 40, 0.5)',
        })),
      )
      volumeChart.priceScale('right').applyOptions({
        scaleMargins: { top: 0.15, bottom: 0 },
      })
    }

    // ---- RSI panel ------------------------------------------------------
    if (showRsi && rsiRef.current) {
      const rsiChart = createChart(
        rsiRef.current,
        baseOptions(sizes.rsi, timeAxisOnRsi),
      )
      chartMap.rsi = rsiChart
      const rsiPoints = indicatorData
        ? pointsFrom(bars, indicatorData.rsi, timeframe)
        : []
      if (rsiPoints.length) {
        const rsiSeries = rsiChart.addLineSeries({
          color: ACCENT,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
          crosshairMarkerVisible: false,
          autoscaleInfoProvider: () => ({
            priceRange: { minValue: 0, maxValue: 100 },
          }),
        })
        rsiSeries.setData(rsiPoints)
        rsiSeries.createPriceLine({
          price: 70,
          color: 'rgba(160, 16, 40, 0.45)',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: false,
          title: '70',
        })
        rsiSeries.createPriceLine({
          price: 30,
          color: 'rgba(27, 107, 74, 0.45)',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: false,
          title: '30',
        })
      }
    }

    // ---- MACD panel -----------------------------------------------------
    if (showMacd && macdRef.current) {
      const macdChart = createChart(macdRef.current, baseOptions(sizes.macd, true))
      chartMap.macd = macdChart
      if (indicatorData) {
        const histogramPoints = pointsFrom(
          bars,
          indicatorData.macd_histogram,
          timeframe,
        ).map((point) => ({
          ...point,
          color:
            point.value >= 0
              ? 'rgba(27, 107, 74, 0.5)'
              : 'rgba(160, 16, 40, 0.45)',
        }))
        if (histogramPoints.length) {
          const histogram = macdChart.addHistogramSeries({
            priceLineVisible: false,
            lastValueVisible: false,
          })
          histogram.setData(histogramPoints)
        }
        const macdPoints = pointsFrom(bars, indicatorData.macd, timeframe)
        if (macdPoints.length) {
          const macdLine = macdChart.addLineSeries({
            color: ACCENT,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          })
          macdLine.setData(macdPoints)
        }
        const signalPoints = pointsFrom(bars, indicatorData.macd_signal, timeframe)
        if (signalPoints.length) {
          const signalLine = macdChart.addLineSeries({
            color: '#af719d',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          })
          signalLine.setData(signalPoints)
        }
      }
    }

    chartsRef.current = chartMap

    // ---- Synchronised time axes ----------------------------------------
    const charts = Object.values(chartMap)
    charts.forEach((chart) => {
      chart.timeScale().fitContent()
    })
    const initialRange = mainChart.timeScale().getVisibleLogicalRange()
    if (initialRange) {
      charts.forEach((chart) => {
        if (chart !== mainChart) chart.timeScale().setVisibleLogicalRange(initialRange)
      })
    }

    let syncing = false
    charts.forEach((source) => {
      source.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (!range || syncing) return
        syncing = true
        charts.forEach((target) => {
          if (target !== source) target.timeScale().setVisibleLogicalRange(range)
        })
        syncing = false
      })
    })

    // ---- Crosshair readout ---------------------------------------------
    mainChart.subscribeCrosshairMove((param) => {
      if (!param?.time) {
        setHover(null)
        return
      }
      setHover(barMap.get(timeKey(param.time)) ?? null)
    })

    // ---- Responsive width ----------------------------------------------
    const resize = () => {
      const width = mainEl.clientWidth || rootRef.current?.clientWidth || 800
      Object.values(chartMap).forEach((chart) => chart.applyOptions({ width }))
    }
    const observer = new ResizeObserver(resize)
    if (rootRef.current) observer.observe(rootRef.current)

    return () => {
      observer.disconnect()
      Object.values(chartMap).forEach((chart) => {
        try {
          chart.remove()
        } catch {
          // Chart may already be disposed during a fast timeframe switch.
        }
      })
      chartsRef.current = {}
      setHover(null)
    }
  }, [bars, indicatorData, timeframe, chartType, indicators])

  // ---- Crosshair on/off applies without rebuilding the charts ----------
  useEffect(() => {
    crosshairRef.current = crosshairOn
    Object.values(chartsRef.current).forEach((chart) => {
      chart?.applyOptions({
        crosshair: {
          mode: crosshairOn ? CrosshairMode.Normal : CrosshairMode.Hidden,
        },
      })
    })
  }, [crosshairOn])

  // ---- Fullscreen ------------------------------------------------------
  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  const toggleFullscreen = useCallback(async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen()
      } else if (rootRef.current?.requestFullscreen) {
        await rootRef.current.requestFullscreen()
      }
    } catch {
      // Fullscreen can be blocked by the browser; the chart stays usable.
    }
  }, [])

  const zoomBy = useCallback((factor) => {
    const chart = chartsRef.current.main
    if (!chart) return
    const range = chart.timeScale().getVisibleLogicalRange()
    if (!range) return
    const span = range.to - range.from
    const next = Math.max(12, Math.min(span * factor, 5000))
    const mid = (range.from + range.to) / 2
    chart.timeScale().setVisibleLogicalRange({ from: mid - next / 2, to: mid + next / 2 })
  }, [])

  const resetView = useCallback(() => {
    chartsRef.current.main?.timeScale().fitContent()
  }, [])

  const toggleIndicator = (key) => {
    setIndicators((current) => ({ ...current, [key]: !current[key] }))
  }

  const activeBar = hover ?? lastBar
  const changeUp = (headerChange ?? 0) >= 0
  const statusClass = statusTone(headerDataStatus)
  const marketClass = statusTone(marketPhase === 'PRE-OPEN' ? 'PRE_OPEN' : marketPhase)

  return (
    <div
      className={`live-chart${isFullscreen ? ' live-chart--fullscreen' : ''}`}
      ref={rootRef}
    >
      <header className="live-chart__header">
        <div className="live-chart__identity">
          <div className="live-chart__name-row">
            <h3 className="live-chart__name">{displayName}</h3>
            <span className={`lc-badge lc-badge--${marketClass}`}>
              {marketPhase ?? 'UNKNOWN'}
            </span>
            <span className={`lc-badge lc-badge--${statusClass}`}>{headerDataStatus}</span>
          </div>
          <div className="live-chart__price-row">
            <span className="live-chart__price">₹{formatPrice(headerPrice)}</span>
            {headerChange !== null && (
              <span className={`live-chart__change ${changeUp ? 'is-up' : 'is-down'}`}>
                {changeUp ? '+' : ''}
                {formatPrice(headerChange)}{' '}
                ({changeUp ? '+' : ''}
                {Number(headerChangePct ?? 0).toFixed(2)}%)
              </span>
            )}
          </div>
        </div>
        <div className="live-chart__meta">
          <span>
            <strong>Source</strong> {quote?.source || data?.source || 'yfinance'}
          </span>
          <span>
            <strong>Quote</strong> {formatStamp(lastUpdated, timeframe)} IST
          </span>
          <span>
            <strong>Last candle</strong> {formatStamp(lastBar?.time, timeframe)} IST
          </span>
        </div>
      </header>

      <div className="live-chart__toolbar" role="toolbar" aria-label="Chart controls">
        <div className="lc-group">
          <span className="lc-group__label">Timeframe</span>
          <div className="lc-segmented">
            {TIMEFRAMES.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`lc-segment${timeframe === item.key ? ' is-active' : ''}`}
                onClick={() => setTimeframe(item.key)}
                aria-pressed={timeframe === item.key}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="lc-group">
          <span className="lc-group__label">Type</span>
          <div className="lc-segmented">
            <button
              type="button"
              className={`lc-segment${chartType === 'candle' ? ' is-active' : ''}`}
              onClick={() => setChartType('candle')}
              aria-pressed={chartType === 'candle'}
            >
              Candles
            </button>
            <button
              type="button"
              className={`lc-segment${chartType === 'line' ? ' is-active' : ''}`}
              onClick={() => setChartType('line')}
              aria-pressed={chartType === 'line'}
            >
              Line
            </button>
          </div>
        </div>

        <div className="lc-group lc-group--indicators">
          <span className="lc-group__label">Indicators</span>
          <div className="lc-chips">
            {INDICATOR_TOGGLES.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`lc-chip${indicators[item.key] ? ' is-active' : ''}`}
                onClick={() => toggleIndicator(item.key)}
                aria-pressed={Boolean(indicators[item.key])}
                title={`${indicators[item.key] ? 'Hide' : 'Show'} ${item.label}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="lc-group lc-group--actions">
          <span className="lc-group__label">View</span>
          <div className="lc-actions">
            <button type="button" className="lc-icon-btn" onClick={() => zoomBy(0.7)} title="Zoom in" aria-label="Zoom in">
              <ZoomIn size={15} />
            </button>
            <button type="button" className="lc-icon-btn" onClick={() => zoomBy(1.4)} title="Zoom out" aria-label="Zoom out">
              <ZoomOut size={15} />
            </button>
            <button type="button" className="lc-icon-btn" onClick={resetView} title="Reset view" aria-label="Reset view">
              <RotateCcw size={15} />
            </button>
            <button
              type="button"
              className={`lc-icon-btn${crosshairOn ? ' is-active' : ''}`}
              onClick={() => setCrosshairOn((value) => !value)}
              title="Toggle crosshair"
              aria-label="Toggle crosshair"
              aria-pressed={crosshairOn}
            >
              <Crosshair size={15} />
            </button>
            <button
              type="button"
              className="lc-icon-btn"
              onClick={toggleFullscreen}
              title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen chart'}
              aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen chart'}
            >
              {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            </button>
          </div>
        </div>
      </div>

      <div className="live-chart__legend" aria-live="off">
        <span className="lc-legend__symbol">{INDEX_LABELS[symbol] || symbol}</span>
        <span className="lc-legend__tf">{timeframe.toUpperCase()}</span>
        {activeBar ? (
          <>
            <span>O <strong>{formatPrice(activeBar.open)}</strong></span>
            <span>H <strong>{formatPrice(activeBar.high)}</strong></span>
            <span>L <strong>{formatPrice(activeBar.low)}</strong></span>
            <span>C <strong>{formatPrice(activeBar.close)}</strong></span>
            <span>Vol <strong>{formatVolume(activeBar.volume)}</strong></span>
            <span className="lc-legend__time">
              {formatStamp(activeBar.time, timeframe)} IST
            </span>
          </>
        ) : (
          <span className="lc-legend__muted">No candle data</span>
        )}
        <span className="lc-legend__hint">
          <Expand size={12} /> Scroll to zoom · drag to pan
        </span>
      </div>

      {isDaily(timeframe) &&
        quote?.timestamp &&
        lastBar?.time &&
        Number(quote.timestamp) - Number(lastBar.time) > 86400 && (
          <p className="live-chart__provider-note">
            <AlertTriangle size={12} />
            The provider has not returned a completed daily candle for the latest session
            (quote {formatStamp(quote.timestamp, timeframe)}; last completed candle{' '}
            {formatStamp(lastBar.time, timeframe)}). The chart does not synthesise an
            unfinished bar.
          </p>
        )}

      {loading && (
        <div className="live-chart__state">
          <Loader2 size={28} className="lc-spin" />
          <p>Loading {displayName} {timeframe.toUpperCase()} candles…</p>
        </div>
      )}

      {!loading && error && (
        <div className="live-chart__state live-chart__state--error">
          <AlertTriangle size={28} />
          <div>
            <strong>Chart data unavailable</strong>
            <p>{error}</p>
            <p className="lc-state__note">
              The chart never substitutes another instrument or synthetic candles.
            </p>
          </div>
          <button
            type="button"
            className="btn btn--sm btn--outline"
            onClick={() => setRetryKey((value) => value + 1)}
          >
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      )}

      {!loading && !error && bars.length > 0 && (
        <div className="live-chart__body">
          <div className="lc-panel lc-panel--main" ref={mainRef} />

          {indicators.volume && (
            <div className="lc-panel-wrap">
              <span className="lc-panel__label">Volume</span>
              <div className="lc-panel lc-panel--volume" ref={volumeRef} />
            </div>
          )}

          {indicators.rsi && (
            <div className="lc-panel-wrap">
              <span className="lc-panel__label">
                RSI (14) <em>70 / 30</em>
              </span>
              <div className="lc-panel lc-panel--rsi" ref={rsiRef} />
              {!indicatorData?.rsi?.some((v) => v !== null) && (
                <span className="lc-panel__empty">Not enough bars for RSI(14)</span>
              )}
            </div>
          )}

          {indicators.macd && (
            <div className="lc-panel-wrap">
              <span className="lc-panel__label">
                MACD (12, 26, 9) <em>line · signal · histogram</em>
              </span>
              <div className="lc-panel lc-panel--macd" ref={macdRef} />
              {!indicatorData?.macd?.some((v) => v !== null) && (
                <span className="lc-panel__empty">Not enough bars for MACD</span>
              )}
            </div>
          )}
        </div>
      )}

      <footer className="live-chart__note">
        {marketPhase === 'OPEN'
          ? 'Market open — candles refresh every 30 seconds during the session.'
          : marketPhase
            ? `Market ${marketPhase.toLowerCase()} — displaying the latest completed session candles, not a live feed.`
            : 'Session status unavailable — displaying the latest candles returned by the provider.'}{' '}
        Indicators are calculated from these same candles. Source: Yahoo Finance via yfinance.
      </footer>
    </div>
  )
}
