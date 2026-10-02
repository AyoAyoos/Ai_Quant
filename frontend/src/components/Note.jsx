const TONES = {
  info: { cls: 'note note--info', icon: 'ℹ' },
  warning: { cls: 'note note--warning', icon: '⚠' },
  danger: { cls: 'note note--danger', icon: '✕' },
  success: { cls: 'note note--success', icon: '✓' },
}

/** Inline callout. Errors never use alert(); they render next to the action. */
export default function Note({ tone = 'info', title, children, reasons }) {
  const { cls, icon } = TONES[tone] ?? TONES.info

  return (
    <div className={cls} role={tone === 'danger' ? 'alert' : 'status'}>
      <span className="note__icon" aria-hidden="true">
        {icon}
      </span>
      <div className="note__body">
        {title && <strong>{title}</strong>}
        {children}
        {Array.isArray(reasons) && reasons.length > 0 && (
          <ul>
            {reasons.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}