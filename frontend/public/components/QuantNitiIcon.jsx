import React from "react";

const P = [[-40, 28], [-18, 8], [2, 16], [26, -14], [42, -30]];
const THEMES = {
  dark: { dash: "#403d88", line: "#8b639b", ring: "#8b639b", end: "#f8b2b2" },
  light: { dash: "#d9d4ec", line: "#8b639b", ring: "#403d88", end: "#f8b2b2" },
};

export default function QuantNitiIcon({ size = 64, theme = "dark", dash = true, ...rest }) {
  const t = THEMES[theme] || THEMES.dark;
  const segs = P.slice(0, 4).map(([x0, y0], i) => {
    const [x1, y1] = P[i + 1];
    const L = Math.hypot(x1 - x0, y1 - y0);
    const ux = (x1 - x0) / L, uy = (y1 - y0) / L;
    const a = 8, b = i === 3 ? 9 : 8;
    return `M${x0 + a * ux} ${y0 + a * uy}L${x1 - b * ux} ${y1 - b * uy}`;
  }).join("");
  return (
    <svg viewBox="-52 -45 108 96" width={size} height={(size * 96) / 108} role="img" aria-label="QuantNiti" {...rest}>
      {dash && <line x1="-42" y1="40" x2="42" y2="40" stroke={t.dash} strokeWidth="2" strokeDasharray="4 4" />}
      <path d={segs} fill="none" stroke={t.line} strokeWidth="5" />
      {P.slice(0, 4).map(([x, y]) => (
        <circle key={x} cx={x} cy={y} r="6" fill="none" stroke={t.ring} strokeWidth="4" />
      ))}
      <circle cx="42" cy="-30" r="9" fill={t.end} />
    </svg>
  );
}
