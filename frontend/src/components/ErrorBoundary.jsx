import { Component } from 'react'

/**
 * Root error boundary. A render-time crash (bad prop, failed API payload)
 * must not unmount the whole React tree and leave a blank page — this catches
 * it and offers a retry / escape hatch instead.
 */
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Unhandled UI error:', error, info)
  }

  render() {
    const { error } = this.state
    if (error) {
      return (
        <div
          role="alert"
          style={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            padding: '24px',
            textAlign: 'center',
            background: '#0d1117',
            color: '#e6edf3',
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          <h1 style={{ fontSize: '20px', margin: 0 }}>Something went wrong</h1>
          <p style={{ color: '#8b949e', maxWidth: '560px', margin: 0 }}>
            {String(error?.message ?? error)}
          </p>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                border: '1px solid #30363d',
                background: '#21262d',
                color: '#e6edf3',
                cursor: 'pointer',
              }}
            >
              Try again
            </button>
            <button
              type="button"
              onClick={() => window.location.assign('/')}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                border: '1px solid #30363d',
                background: '#0d1117',
                color: '#e6edf3',
                cursor: 'pointer',
              }}
            >
              Go home
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
