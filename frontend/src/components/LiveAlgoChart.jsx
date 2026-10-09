import { useEffect, useRef, useState } from 'react';
import { createChart, CrosshairMode } from 'lightweight-charts';
import './LiveAlgoChart.css';

const BUY_COLOR = '#26d07c';
const SELL_COLOR = '#ff5c5c';
const ACCENT = '#ffb3ba';

/** Minimum spacing between trade signals (in bars) — prevents clustering. */
const MIN_SIGNAL_GAP_BARS = 10;
/** Max signals kept on screen — a clean, readable set. */
const MAX_SIGNALS = 6;

const rand = (min, max) => min + Math.random() * (max - min);

/** Seeded-looking random walk around a Nifty 50 spot level. */
function buildSeedCandles(count = 120, stepSec = 60) {
  const now = Math.floor(Date.now() / 1000);
  const start = now - count * stepSec;
  let price = 25750;
  const candles = [];
  for (let i = 0; i < count; i++) {
    const open = price;
    const drift = rand(-14, 15);
    const close = Math.max(24000, open + drift);
    const high = Math.max(open, close) + rand(0, 9);
    const low = Math.min(open, close) - rand(0, 9);
    candles.push({ time: start + i * stepSec, open, high, low, close });
    price = close;
  }
  return candles;
}

/** 5 well-spaced opening signals across the seed dataset (BUY below, SELL above). */
function buildSeedMarkers(seed) {
  const at = (offsetFromEnd, side) => {
    const bar = seed[seed.length - 1 - offsetFromEnd];
    return {
      time: bar.time,
      position: side === 'BUY' ? 'belowBar' : 'aboveBar',
      color: side === 'BUY' ? BUY_COLOR : SELL_COLOR,
      shape: side === 'BUY' ? 'arrowUp' : 'arrowDown',
      text: side,
    };
  };
  return [
    at(100, 'BUY'),
    at(78, 'SELL'),
    at(56, 'BUY'),
    at(34, 'SELL'),
    at(12, 'BUY'),
  ];
}

export default function LiveAlgoChart() {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const seriesRef = useRef(null);
  const barsRef = useRef([]);
  const markersRef = useRef([]);
  const lastSignalTimeRef = useRef(0);
  const tickRef = useRef(0);
  const signalSideRef = useRef('SELL');

  const [metrics, setMetrics] = useState({
    price: 25750,
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

    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

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
      },
      rightPriceScale: { borderColor: 'rgba(139, 99, 155, 0.4)' },
    });

    const series = chart.addCandlestickSeries({
      upColor: BUY_COLOR,
      downColor: SELL_COLOR,
      wickUpColor: 'rgba(38, 208, 124, 0.8)',
      wickDownColor: 'rgba(255, 92, 92, 0.8)',
      borderVisible: false,
    });
    seriesRef.current = series;

    const seed = buildSeedCandles();
    barsRef.current = seed;
    series.setData(seed);

    markersRef.current = buildSeedMarkers(seed);
    lastSignalTimeRef.current = markersRef.current[markersRef.current.length - 1].time;
    series.setMarkers(markersRef.current);
    chart.timeScale().scrollToRealTime();

    const first = seed[0].close;
    const last = seed[seed.length - 1].close;
    setMetrics((m) => ({
      ...m,
      price: last,
      changePct: ((last - first) / first) * 100,
    }));

    const ro = new ResizeObserver(() => {
      chart.resize(wrap.clientWidth, 340);
    });
    ro.observe(wrap);

    if (reduced) {
      return () => {
        ro.disconnect();
        chart.remove();
      };
    }

    const interval = window.setInterval(() => {
      const s = seriesRef.current;
      if (!s) return;
      const bars = barsRef.current;
      const current = bars[bars.length - 1];
      tickRef.current += 1;
      const n = tickRef.current;

      // Live tick: jitter the forming candle.
      const delta = rand(-9, 9.5);
      current.close = Math.max(24000, current.close + delta);
      current.high = Math.max(current.high, current.close);
      current.low = Math.min(current.low, current.close);
      s.update(current);

      let newSignal = null;
      // Roll to a fresh candle every 4 ticks (~6s) to keep the feed alive.
      if (n % 4 === 0) {
        const next = {
          time: current.time + 60,
          open: current.close,
          high: current.close,
          low: current.close,
          close: current.close,
        };
        bars.push(next);
        if (bars.length > 220) bars.shift();
        s.update(next);
      }

      // Throttled algo signal: at most one per MIN_SIGNAL_GAP_BARS, so
      // markers never cluster on consecutive candles. Keeps 4–6 on screen.
      const liveBar = bars[bars.length - 1];
      if (n % 8 === 0 && liveBar.time - lastSignalTimeRef.current >= MIN_SIGNAL_GAP_BARS * 60) {
        const side = signalSideRef.current;
        signalSideRef.current = side === 'BUY' ? 'SELL' : 'BUY';
        newSignal = {
          time: liveBar.time,
          position: side === 'BUY' ? 'belowBar' : 'aboveBar',
          color: side === 'BUY' ? BUY_COLOR : SELL_COLOR,
          shape: side === 'BUY' ? 'arrowUp' : 'arrowDown',
          text: side,
        };
        lastSignalTimeRef.current = liveBar.time;
        markersRef.current = [...markersRef.current, newSignal].slice(-MAX_SIGNALS);
        s.setMarkers(markersRef.current);
      }

      const base = bars[0].close;
      const px = bars[bars.length - 1].close;
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

      chart.timeScale().scrollToRealTime();
    }, 1500);

    return () => {
      window.clearInterval(interval);
      ro.disconnect();
      chart.remove();
      seriesRef.current = null;
    };
  }, []);

  const up = metrics.changePct >= 0;
  const pnlUp = metrics.pnl >= 0;

  return (
    <div className="algo-chart" aria-label="Live simulated Nifty 50 algorithmic trading demo">
      <div className="algo-chart__head">
        <div className="algo-chart__title">
          <span className="algo-chart__live">
            <span className="algo-chart__pulse" aria-hidden="true" />
            LIVE
          </span>
          <span className="algo-chart__pair">NIFTY 50 · Simulated algo execution</span>
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
          <span className={`algo-chart__hud-chg ${up ? 'is-up' : 'is-down'}`}>
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
        Simulated tick feed for illustration — connect a paper-trading deployment for live orders.
      </p>
    </div>
  );
}
