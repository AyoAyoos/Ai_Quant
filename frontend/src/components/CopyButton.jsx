import { useEffect, useRef, useState } from 'react'
import Icon from './Icon.jsx'

/**
 * Copies `text` to the clipboard and confirms it for two seconds.
 *
 * navigator.clipboard needs a secure context, so plain-HTTP LAN hosts fall back
 * to a hidden textarea + execCommand. If both paths fail the button says so
 * rather than silently claiming success.
 */
export default function CopyButton({ text, label = 'Copy', className = '' }) {
  const [state, setState] = useState('idle')
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    clearTimeout(timer.current)

    let ok = false
    try {
      await navigator.clipboard.writeText(text)
      ok = true
    } catch {
      try {
        const area = document.createElement('textarea')
        area.value = text
        area.setAttribute('readonly', '')
        area.style.position = 'fixed'
        area.style.opacity = '0'
        document.body.appendChild(area)
        area.select()
        ok = document.execCommand('copy')
        document.body.removeChild(area)
      } catch {
        ok = false
      }
    }

    setState(ok ? 'done' : 'failed')
    timer.current = setTimeout(() => setState('idle'), 2000)
  }

  const copyState =
    state === 'done'
      ? { cls: 'copy-btn copy-btn--done', text: 'Copied', icon: 'check' }
      : state === 'failed'
        ? { cls: 'copy-btn copy-btn--failed', text: 'Press Ctrl+C', icon: 'error' }
        : { cls: 'copy-btn', text: label, icon: 'content_copy' }

  return (
    <button type="button" className={`${copyState.cls} ${className}`.trim()} onClick={copy}>
      <Icon name={copyState.icon} size={14} />
      {copyState.text}
    </button>
  )
}