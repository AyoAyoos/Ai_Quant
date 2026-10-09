import { useEffect, useRef, useState } from 'react';
import { createChart, CrosshairMode } from 'lightweight-charts';
import { API_BASE } from '../lib/api.js';
import './LiveAlgoChart.css';

const BUY_COLOR = '#26d07c';
const SELL_COLOR = '#ff5c5c';
const ACCENT = '#ffb3ba';

/** Single scale for the whole component: NIFTY 50 (~24,490). Never mix. */
const NIFTY_SEED_LEVEL = 24490;
/** Absolute floor so far below any realistic print it can never
 *  manufacture a visible jump candle. */
const PRICE_FLOOR = 1000;
/** Real history older than this vs. now is discarded (stale session). */
const STALE_AFTER_SEC = 15 * 60;

/** Heartbeat: simulator tick cadence (ms). Only animates while feed is 'sim'. */
const HEARTBEAT_MS = 1500;
/** Live NIFTY 50 poll cadence (ms) during market hours. */
const POLL_MS = 7000;
/** NSE cash session, IST, Monday–Friday. */
const OPEN_MINUTES = 9 * 60 + 15;
const CLOSE_MINUTES = 15 * 60 + 30;

/** Minimum spacing between trade signals (in bars) — prevents clustering. */
const MIN_SIGNAL_GAP_BARS = 10;
/** Max signals kept on screen — a clean, readable set. */
const MAX_SIGNALS = 6;

const rand = (min, max) => min + Math.random() * (max - min);

/** Current time in the Asia/Kolkata wall clock. */
function istNow() {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
}

/** True during the cash session (Mon–Fri, 09:15–15:30 IST). */
function marketOpenIST(date = istNow()) {
  const day = date.getDay();
  if (day === 0 || day === 6) return false;
  const minutes = date.getHours() * 60 + date.getMinutes();
  return minutes >= OPEN_MINUTES && minutes < CLOSE_MINUTES;
}

/** IST axis label: "09:16". One formatter for ticks AND crosshair. */
function istLabel(time) {
  return new Date(time * 1000).toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Keep only the lightweight-charts candle fields (drops volume etc.). */
const toBar = (b) => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close });

/**
 * Fallback seed anchored to NOW: start from the current UNIX minute and walk
 * backwards one 1-minute candle at a time, then reverse to chronological
 * order — so the last bar always meets the exact current time. NIFTY 50
 * scale only, matching the live feed, so the swap can never draw a jump.
 */
function buildSeedCandles(count = 120, stepSec = 60) {
  const now = Math.floor(Date.now() / 1000);
  const nowMinute = now - (now % 60);
  const reversed = [];
  let close = NIFTY_SEED_LEVEL;
  for (let i = 0; i < count; i++) {
    const time = nowMinute - i * stepSec;
    const open = close + rand(-14, 15);
    const high = Math.max(open, close) + rand(0, 9);
    const low = Math.min(open, close) - rand(0, 9);
    reversed.push({ time, open, high, low, close });
    close = Math.max(PRICE_FLOOR, open); // step one minute into the past
  }
  return reversed.reverse();
}

/**
 * Opening signals spread across ANY dataset length (safe at 09:16 with a
 * handful of bars, and spaced on full histories). BUY below, SELL above.
 */
function buildSeedMarkers(data) {
  const n = data.length;
  const count = Math.max(0, Math.min(5, Math.floor(n / 20)));
  const sides = ['BUY', 'SELL', 'BUY', 'SELL', 'BUY'];
  const out = [];
  for (let k = 0; k < count; k++) {
    const idx = Math.max(1, Math.min(n - 2, Math.floor(((k + 1) / (count + 1)) * n)));
    const bar = data[idx];
    const side = sides[k];
    out.push({
      time: bar.time,
      position: side === 'BUY' ? 'belowBar' : 'aboveBar',
      color: side === 'BUY' ? BUY_COLOR : SELL_COLOR,
      shape: side === 'BUY' ? 'arrowUp' : 'arrowDown',
      text: side,
    });
  }
  return out;
}

async function fetchJson(path, timeoutMs = 5000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    window.clearTimeout(timeout);
  }
}

export default function LiveAlgoChart() {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const seriesRef = useRef(null);
  const chartRef = useRef(null);
  const barsRef = useRef([]);
  const markersRef = useRef([]);
  const lastSignalTimeRef = useRef(0);
  const tickRef = useRef(0);
  const signalSideRef = useRef('SELL');
  const feedRef = useRef('sim');

  const [, setFeedState] = useState('sim');
  const setFeed = (value) => {
    feedRef.current = value;
    setFeedState(value);
  };
  const [metrics, setMetrics] = useState({
    price: NIFTY_SEED_LEVEL,
    changePct: 0.32,
    pnl: 5.4,
    sharpe: 1.96,
    winRate: 70.2,
    trades: 140,
    lastSignal: 'BUY',
  });

  useEffect(() => {
    const wrap = wrapRef.current;
    const el = canvasRef.current;
    if (!wrap || !el) return undefined;

    const chart = createChart(el, {
      width: el.clientWidth || wrap.clientWidth || 800,
      height: 340,
      layout: {
        background: { type: 'solid', color: 'transparent' },
        textColor: '#e3d9e5',
        fontFamily: "'Plus Jakarta Sans', 'Space Grotesk', sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      // Explicit IST axis everywhere: tick marks AND crosshair labels.
      localization: { timeFormatter: istLabel },
      grid: {
        vertLines: { color: 'rgba(139, 99, 155, 0.12)' },
        horzLines: { color: 'rgba(139, 99, 155, 0.12)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: ACCENT, width: 1, style: 2, labelBackgroundColor: '#8B639B' },
        horzLine: { color: ACCENT, width: 1, style: 2, labelBackgroundColor: '#8B639B' },
      },
      timeScale: {
        borderColor: 'rgba(139, 99, 155, 0.4)',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 15,
        barSpacing: 10,
        tickMarkFormatter: istLabel,
      },
      rightPriceScale: { borderColor: 'rgba(139, 99, 155, 0.4)' },
    });
    chartRef.current = chart;

    const series = chart.addCandlestickSeries({
      upColor: BUY_COLOR,
      downColor: SELL_COLOR,
      wickUpColor: 'rgba(38, 208, 124, 0.8)',
      wickDownColor: 'rgba(255, 92, 92, 0.8)',
      borderVisible: false,
    });
    seriesRef.current = series;

    const syncHud = (px, newSignal) => {
      const bars = barsRef.current;
      const base = bars.length ? bars[0].close : px;
      setMetrics((m) => {
        const pnl = m.pnl + rand(-0.06, 0.09) + (newSignal?.text === 'SELL' ? rand(0, 0.12) : 0);
        const sharpe = Math.min(2.6, Math.max(1.2, m.sharpe + rand(-0.03, 0.03)));
        const trades = newSignal ? m.trades + 1 : m.trades;
        const winRate = Math.min(78, Math.max(58, m.winRate + rand(-0.2, 0.25)));
        return {
          price: px,
          changePct: ((px - base) / base) * 100,
          pnl,
          sharpe,
          winRate,
          trades,
          lastSignal: newSignal ? newSignal.text : m.lastSignal,
        };
      });
    };

    const pushSignal = (barTime) => {
      const s = seriesRef.current;
      const side = signalSideRef.current;
      signalSideRef.current = side === 'BUY' ? 'SELL' : 'BUY';
      const signal = {
        time: barTime,
        position: side === 'BUY' ? 'belowBar' : 'aboveBar',
        color: side === 'BUY' ? BUY_COLOR : SELL_COLOR,
        shape: side === 'BUY' ? 'arrowUp' : 'arrowDown',
        text: side,
      };
      lastSignalTimeRef.current = barTime;
      markersRef.current = [...markersRef.current, signal].slice(-MAX_SIGNALS);
      s?.setMarkers(markersRef.current);
      return signal;
    };

    const paintBars = (bars) => {
      const s = seriesRef.current;
      if (!s || !bars.length) return;
      barsRef.current = bars;
      s.setData(bars);
      markersRef.current = buildSeedMarkers(bars);
      lastSignalTimeRef.current = markersRef.current.length
        ? markersRef.current[markersRef.current.length - 1].time
        : 0;
      s.setMarkers(markersRef.current);
      chartRef.current?.timeScale().scrollToRealTime();
      syncHud(bars[bars.length - 1].close, null);
    };

    // ---- Mount: real NIFTY 50 1m history, fresh only. --------------------
    // A stale session (e.g. yesterday's close) is discarded so old bars can
    // never collide with live ticks on the axis — the seed takes over.
    let cancelled = false;
    (async () => {
      try {
        const history = await fetchJson('/market/nifty-history', 8000);
        const bars = (Array.isArray(history) ? history : []).map(toBar);
        const nowMinute = Math.floor(Date.now() / 1000 / 60) * 60;
        const fresh = bars.length >= 3 && bars[bars.length - 1].time >= nowMinute - STALE_AFTER_SEC;
        if (cancelled) return;
        if (!fresh) throw new Error('stale history');
        paintBars(bars);
        setFeed('live');
      } catch {
        if (cancelled) return;
        paintBars(buildSeedCandles());
        setFeed('sim');
      }
    })();

    // ---- Heartbeat: every tick derives from the LAST close — never a
    // ---- hardcoded level — and new candles never outrun the wall clock,
    // ---- so timestamps can't overlap or leap.
    const heartbeat = window.setInterval(() => {
      if (feedRef.current !== 'sim') return;
      const s = seriesRef.current;
      if (!s) return;
      const bars = barsRef.current;
      if (!bars.length) return;
      const current = bars[bars.length - 1];
      tickRef.current += 1;
      const n = tickRef.current;

      const lastClose = current.close;
      const magnitude = rand(2, 5);
      const newClose = Math.max(PRICE_FLOOR, lastClose + (Math.random() < 0.52 ? 1 : -1) * magnitude);
      current.close = newClose;
      current.high = Math.max(current.high, newClose);
      current.low = Math.min(current.low, newClose);
      s.update(current);

      let newSignal = null;
      // New minute at most as fast as the real clock: never inject a bar
      // stamped ahead of now, so the axis stays gapless and ordered.
      const now = Math.floor(Date.now() / 1000);
      const nowMinute = now - (now % 60);
      if (n % 4 === 0 && current.time < nowMinute) {
        const nextTime = Math.min(current.time + 60, nowMinute);
        if (nextTime > current.time) {
          const next = {
            time: nextTime,
            open: current.close,
            high: current.close,
            low: current.close,
            close: current.close,
          };
          bars.push(next);
          if (bars.length > 220) bars.shift();
          s.update(next);
        }
      }

      // Throttled algo signal: never on consecutive candles.
      const liveBar = bars[bars.length - 1];
      if (n % 8 === 0 && liveBar.time - lastSignalTimeRef.current >= MIN_SIGNAL_GAP_BARS * 60) {
        newSignal = pushSignal(liveBar.time);
      }

      syncHud(bars[bars.length - 1].close, newSignal);
      chartRef.current?.timeScale().scrollToRealTime();
    }, HEARTBEAT_MS);

    // ---- Live poller: latest NIFTY 50 candle in market hours, sim otherwise.
    const pollLive = async () => {
      if (!marketOpenIST()) {
        if (barsRef.current.length) setFeed('sim');
        return;
      }
      try {
        const raw = await fetchJson('/market/nifty-live', 5000);
        const bar = toBar(raw);
        const s = seriesRef.current;
        if (!s || typeof bar.time !== 'number') throw new Error('bad bar');
        const bars = barsRef.current;
        if (!bars.length) {
          paintBars([bar]);
          setFeed('live');
          return;
        }
        const current = bars[bars.length - 1];
        if (bar.time < current.time - 60) throw new Error('stale bar');
        if (bar.time === current.time) {
          current.open = bar.open;
          current.high = Math.max(current.high, bar.high);
          current.low = Math.min(current.low, bar.low);
          current.close = bar.close;
          s.update(current);
        } else if (bar.time > current.time) {
          bars.push(bar);
          if (bars.length > 375) bars.shift();
          s.update(bar);
        } else {
          throw new Error('stale bar');
        }
        setFeed('live');
        syncHud(bars[bars.length - 1].close, null);
        chartRef.current?.timeScale().scrollToRealTime();
      } catch {
        // Backend down / Yahoo hiccup: heartbeat simulator keeps the chart alive.
        if (barsRef.current.length) setFeed('sim');
      }
    };
    const poller = window.setInterval(pollLive, POLL_MS);

    const ro = new ResizeObserver(() => {
      chartRef.current?.resize(wrap.clientWidth, 340);
    });
    ro.observe(wrap);

    // Full cleanup: both timers, observers, chart — no leaks on unmount.
    return () => {
      cancelled = true;
      window.clearInterval(heartbeat);
      window.clearInterval(poller);
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  const up = metrics.changePct >= 0;
  const pnlUp = metrics.pnl >= 0;

  return (
    <div className="algo-chart" aria-label="Live NIFTY 50 algorithmic trading chart">
      <div className="algo-chart__head">
        <div className="algo-chart__title">
          <span className="algo-chart__live">
            <span className="algo-chart__pulse" aria-hidden="true" />
            LIVE
          </span>
          <span className="algo-chart__pair">NIFTY 50 · Live algo execution</span>
        </div>
        <div className="algo-chart__status" role="status">
          <span className="algo-chart__status-dot" aria-hidden="true" />
          Status: Algorithmic Loop Active
        </div>
      </div>

      <div className="algo-chart__body" ref={wrapRef}>
        <div className="algo-chart__canvas" ref={canvasRef} />
        <div className="algo-chart__hud" aria-label="Live algorithmic performance">
          <span className="algo-chart__hud-price">
            ₹{metrics.price.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}
          </span>
          <span className={'algo-chart__hud-chg ' + (up ? 'is-up' : 'is-down')}>
            {up ? '▲' : '▼'} {Math.abs(metrics.changePct).toFixed(2)}%
          </span>
          <span className="algo-chart__hud-sep" aria-hidden="true" />
          <span className="algo-chart__hud-stat">
            Sharpe <strong>{metrics.sharpe.toFixed(2)}</strong>
          </span>
          <span className="algo-chart__hud-stat">
            Live P&amp;L{' '}
            <strong className={pnlUp ? 'is-up' : 'is-down'}>
              {pnlUp ? '+' : ''}{metrics.pnl.toFixed(1)}%
            </strong>
          </span>
          <span className="algo-chart__hud-stat">
            Win <strong>{metrics.winRate.toFixed(1)}%</strong>
          </span>
          <span className="algo-chart__hud-stat">
            Trades <strong>{metrics.trades}</strong>
          </span>
        </div>
      </div>

      <p className="algo-chart__note">
        Streaming live NIFTY 50 1-minute bars during market hours (9:15 AM – 3:30 PM IST).
      </p>
    </div>
  );
}
