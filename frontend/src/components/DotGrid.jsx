import { useRef, useEffect, useCallback, useMemo } from 'react';
import { gsap } from 'gsap';
import './DotGrid.css';

function hexToRgb(hex) {
  let h = hex.replace('#', '');
  if (h.length === 3) {
    h = h
      .split('')
      .map((c) => c + c)
      .join('');
  }
  const n = parseInt(h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

const throttle = (fn, limit) => {
  let last = 0;
  let timer = null;
  return (...args) => {
    const now = performance.now();
    const remaining = limit - (now - last);
    if (remaining <= 0) {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      last = now;
      fn(...args);
    } else if (!timer) {
      timer = setTimeout(() => {
        last = performance.now();
        timer = null;
        fn(...args);
      }, remaining);
    }
  };
};

/**
 * DotGrid — canvas dot-grid background (React Bits API).
 *
 * Dots repel from the cursor within `proximity`, ripple outward from clicks
 * (`shockRadius` / `shockStrength`) and ease back home over `returnDuration`.
 * Dot colour interpolates `baseColor` -> `activeColor` with displacement.
 */
export default function DotGrid({
  dotSize = 16,
  gap = 32,
  baseColor = '#5227FF',
  activeColor = '#5227FF',
  proximity = 150,
  speedTrigger = 100,
  shockRadius = 250,
  shockStrength = 5,
  maxSpeed = 5000,
  resistance = 750,
  returnDuration = 1.5,
  className = '',
  style,
}) {
  const wrapperRef = useRef(null);
  const canvasRef = useRef(null);
  const dotsRef = useRef([]);
  const sizeRef = useRef({ width: 0, height: 0 });
  const pointerRef = useRef({
    x: -9999,
    y: -9999,
    speed: 0,
    lastX: -9999,
    lastY: -9999,
    lastTime: 0,
  });
  const shockRef = useRef(null);

  const baseRgb = useMemo(() => hexToRgb(baseColor), [baseColor]);
  const activeRgb = useMemo(() => hexToRgb(activeColor), [activeColor]);

  const propsRef = useRef({});
  propsRef.current = {
    dotSize,
    gap,
    proximity,
    speedTrigger,
    shockRadius,
    shockStrength,
    maxSpeed,
    resistance,
    returnDuration,
  };

  const buildGrid = useCallback(() => {
    const wrapper = wrapperRef.current;
    const canvas = canvasRef.current;
    if (!wrapper || !canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const { width, height } = wrapper.getBoundingClientRect();
    if (width === 0 || height === 0) return;
    sizeRef.current = { width, height };
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const g = propsRef.current.gap;
    const cols = Math.max(1, Math.floor((width + g) / g));
    const rows = Math.max(1, Math.floor((height + g) / g));
    const ox = (width - (cols - 1) * g) / 2;
    const oy = (height - (rows - 1) * g) / 2;
    const dots = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const x = ox + c * g;
        const y = oy + r * g;
        dots.push({ x0: x, y0: y, x, y, vx: 0, vy: 0 });
      }
    }
    dotsRef.current = dots;
  }, []);

  const drawStatic = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const { width, height } = sizeRef.current;
    const { dotSize: ds } = propsRef.current;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = `rgb(${baseRgb.r}, ${baseRgb.g}, ${baseRgb.b})`;
    for (const d of dotsRef.current) {
      ctx.beginPath();
      ctx.arc(d.x0, d.y0, ds / 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [baseRgb]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrapper = wrapperRef.current;
    if (!canvas || !wrapper) return undefined;

    buildGrid();

    // Reduced motion: render one static frame, no animation loop.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      drawStatic();
      const ro = new ResizeObserver(() => {
        buildGrid();
        drawStatic();
      });
      ro.observe(wrapper);
      return () => ro.disconnect();
    }

    const onResize = throttle(() => buildGrid(), 200);
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(onResize) : null;
    ro?.observe(wrapper);
    window.addEventListener('resize', onResize);

    const updatePointer = (clientX, clientY) => {
      const rect = canvas.getBoundingClientRect();
      const p = pointerRef.current;
      const now = performance.now();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      if (p.lastTime) {
        const dt = Math.max(1, now - p.lastTime) / 1000;
        const vx = (x - p.lastX) / dt;
        const vy = (y - p.lastY) / dt;
        p.speed = Math.min(Math.hypot(vx, vy), propsRef.current.maxSpeed);
      }
      p.x = x;
      p.y = y;
      p.lastX = x;
      p.lastY = y;
      p.lastTime = now;
    };

    const throttledMove = throttle((e) => updatePointer(e.clientX, e.clientY), 16);
    const onLeave = () => {
      const p = pointerRef.current;
      p.x = -9999;
      p.y = -9999;
      p.speed = 0;
      p.lastTime = 0;
    };
    const onClick = (e) => {
      const rect = canvas.getBoundingClientRect();
      shockRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top, r: 0 };
    };

    window.addEventListener('mousemove', throttledMove);
    document.documentElement.addEventListener('mouseleave', onLeave);
    canvas.addEventListener('click', onClick);

    const tick = (_time, deltaMS) => {
      const dt = Math.min(0.05, deltaMS / 1000);
      const ctx = canvas.getContext('2d');
      const pr = propsRef.current;
      const p = pointerRef.current;
      const { width, height } = sizeRef.current;
      if (width === 0 || height === 0) return;
      ctx.clearRect(0, 0, width, height);

      const shock = shockRef.current;
      if (shock) {
        shock.r += dt * 900;
        if (shock.r > pr.shockRadius * 2.4) shockRef.current = null;
      }

      const damp = Math.exp(-dt * (pr.resistance / 120));
      const home = 1 - Math.exp((-dt * 3.5) / Math.max(0.01, pr.returnDuration));
      const radius = pr.dotSize / 2;

      for (const d of dotsRef.current) {
        let fx = 0;
        let fy = 0;

        const dx = d.x - p.x;
        const dy = d.y - p.y;
        const dist = Math.hypot(dx, dy);
        if (dist < pr.proximity && dist > 0.01) {
          const falloff = 1 - dist / pr.proximity;
          const boost = 1 + Math.min(p.speed / Math.max(1, pr.speedTrigger), 4);
          const f = falloff * falloff * 2600 * boost * dt;
          fx += (dx / dist) * f;
          fy += (dy / dist) * f;
        }

        if (shock) {
          const sx = d.x - shock.x;
          const sy = d.y - shock.y;
          const sd = Math.hypot(sx, sy) || 0.01;
          const band = Math.abs(sd - shock.r);
          if (band < pr.shockRadius) {
            const f = (1 - band / pr.shockRadius) * pr.shockStrength * 900 * dt;
            fx += (sx / sd) * f;
            fy += (sy / sd) * f;
          }
        }

        d.vx = (d.vx + fx) * damp;
        d.vy = (d.vy + fy) * damp;
        d.x += d.vx * dt * 60 + (d.x0 - d.x) * home;
        d.y += d.vy * dt * 60 + (d.y0 - d.y) * home;

        const disp = Math.hypot(d.x - d.x0, d.y - d.y0);
        const t = Math.min(1, disp / (pr.proximity * 0.6));
        const r = Math.round(baseRgb.r + (activeRgb.r - baseRgb.r) * t);
        const g = Math.round(baseRgb.g + (activeRgb.g - baseRgb.g) * t);
        const b = Math.round(baseRgb.b + (activeRgb.b - baseRgb.b) * t);
        ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
        ctx.beginPath();
        ctx.arc(d.x, d.y, radius * (1 + 0.6 * t), 0, Math.PI * 2);
        ctx.fill();
      }
    };

    gsap.ticker.add(tick);
    return () => {
      gsap.ticker.remove(tick);
      window.removeEventListener('mousemove', throttledMove);
      window.removeEventListener('resize', onResize);
      document.documentElement.removeEventListener('mouseleave', onLeave);
      canvas.removeEventListener('click', onClick);
      ro?.disconnect();
    };
  }, [buildGrid, drawStatic, baseRgb, activeRgb]);

  return (
    <section ref={wrapperRef} className={`dot-grid${className ? ` ${className}` : ''}`} style={style}>
      <canvas ref={canvasRef} className="dot-grid__canvas" />
    </section>
  );
}
