let toastContainer = null
let toastTimeout = null

function ensureContainer() {
  if (toastContainer) return toastContainer
  toastContainer = document.createElement('div')
  toastContainer.id = 'toast-container'
  toastContainer.className = 'toast-container'
  document.body.appendChild(toastContainer)
  return toastContainer
}

function showToast(message, { type = 'info', duration = 3000 } = {}) {
  const container = ensureContainer()
  const toast = document.createElement('div')
  toast.className = `toast toast--${type}`
  toast.setAttribute('role', 'alert')
  toast.setAttribute('aria-live', 'polite')
  toast.textContent = message

  container.appendChild(toast)

  // Animate in
  requestAnimationFrame(() => {
    toast.classList.add('toast--visible')
  })

  // Auto-remove
  const timeout = setTimeout(() => {
    toast.classList.remove('toast--visible')
    toast.addEventListener('transitionend', () => toast.remove(), { once: true })
  }, duration)

  // Pause on hover
  toast.addEventListener('mouseenter', () => clearTimeout(timeout))
  toast.addEventListener('mouseleave', () => {
    const newTimeout = setTimeout(() => {
      toast.classList.remove('toast--visible')
      toast.addEventListener('transitionend', () => toast.remove(), { once: true })
    }, 1000)
  })

  return () => {
    clearTimeout(timeout)
    toast.classList.remove('toast--visible')
    toast.addEventListener('transitionend', () => toast.remove(), { once: true })
  }
}

export { showToast }