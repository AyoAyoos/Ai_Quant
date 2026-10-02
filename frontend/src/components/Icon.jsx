/**
 * Material Symbols Outlined icon.
 *
 * The font is a ligature font: the child string is swapped for a glyph at paint
 * time by the `liga` feature (see `.ms` in tokens.css). Because that swap is a
 * CDN font load, the raw text is always in the accessibility tree as a word —
 * so icons here are decorative only and must never be the sole carrier of
 * meaning. Every icon in this app sits next to a text label.
 *
 * `fill` switches the FILL axis to 1 for the selected/active state.
 */
export default function Icon({ name, size = 20, fill = false, weight = 400, className = '', style }) {
  return (
    <span
      className={`ms${className ? ` ${className}` : ''}`}
      aria-hidden="true"
      style={{
        fontSize: `${size}px`,
        fontVariationSettings: `'FILL' ${fill ? 1 : 0}, 'wght' ${weight}, 'GRAD' 0, 'opsz' 24`,
        ...style,
      }}
    >
      {name}
    </span>
  )
}