import { useState } from 'react'

/** Lazy, collapsible code viewer with copy-to-clipboard. */
export default function CodeViewer({ code, fileName = 'GeneratedStrategy.py' }) {
  const [copied, setCopied] = useState(false)

  if (typeof code !== 'string' || code.trim() === '') {
    return (
      <p className="table-footnote">
        No code is stored for this strategy. Ask the assistant to finalize one in chat.
      </p>
    )
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="code-viewer">
      <div className="code-viewer__bar">
        <span className="code-viewer__name">{fileName}</span>
        <button type="button" className="btn btn--ghost btn--sm" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="code-viewer__pre">
        <code>{code}</code>
      </pre>
    </div>
  )
}