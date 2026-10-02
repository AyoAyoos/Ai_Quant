import { useId, useState } from 'react'

/**
 * Generic collapsible section. Used for backtest parameters, the code viewer
 * and the trade table so disclosure behaviour is identical everywhere.
 */
export default function Disclosure({ title, meta, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()
  const buttonId = useId()

  return (
    <section className="disclosure">
      <button
        type="button"
        id={buttonId}
        className="disclosure__trigger"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <span>
          {title}
          {meta && <span className="panel__subtitle"> · {meta}</span>}
        </span>
        <span className={`disclosure__chevron${open ? ' disclosure__chevron--open' : ''}`} aria-hidden="true">
          ▶
        </span>
      </button>
      <div id={panelId} className="disclosure__panel" hidden={!open}>
        {open && children}
      </div>
    </section>
  )
}