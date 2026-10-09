/**
 * LogoMark — QuantNiti trend-line icon, hero-weight edition.
 *
 * Inlined (rather than the public/*.svg file) so stroke weight, node size
 * and colours can be tuned directly. Bolder connecting lines, enlarged
 * nodes and high-contrast white/pink inks keep it legible over the bright
 * crystal-ball particle field.
 */
export default function LogoMark({ className = '', width = 128, height = 128, title = 'QuantNiti logo' }) {
  return (
    <svg
      className={className}
      width={width}
      height={height}
      viewBox="-52 -45 108 96"
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      {/* baseline */}
      <line
        x1="-42"
        y1="40"
        x2="42"
        y2="40"
        stroke="#ffffff"
        strokeOpacity="0.4"
        strokeWidth="2.5"
        strokeDasharray="4 4"
      />
      {/* trend segments — widened 5 → 8, solid white */}
      <path
        d="M-34.08 22.62L-23.92 13.38M-10.57 10.97L-5.43 13.03M7 9.75L21 -7.75M31.66 -19.66L35.64 -23.64"
        fill="none"
        stroke="#ffffff"
        strokeWidth="8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* nodes — enlarged r 6 → 7.5, ring 4 → 5.5, solid white */}
      <circle cx="-40" cy="28" r="7.5" fill="#1e1636" stroke="#ffffff" strokeWidth="5.5" />
      <circle cx="-18" cy="8" r="7.5" fill="#1e1636" stroke="#ffffff" strokeWidth="5.5" />
      <circle cx="2" cy="16" r="7.5" fill="#1e1636" stroke="#ffffff" strokeWidth="5.5" />
      <circle cx="26" cy="-14" r="7.5" fill="#1e1636" stroke="#ffffff" strokeWidth="5.5" />
      {/* terminal node — enlarged r 9 → 11, neon pink accent */}
      <circle cx="42" cy="-30" r="11" fill="#ffb3ba" />
    </svg>
  );
}
