import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { fetchHealth, HEALTH_POLL_MS } from '../lib/api.js'
import { readStrategies } from '../lib/storage.js'
import Icon from './Icon.jsx'

function useBackendHealth() {
  const [state, setState] = useState('checking')

  useEffect(() => {
    let cancelled = false
    let timer = null

    async function probe() {
      try {
        await fetchHealth()
        if (!cancelled) setState('online')
      } catch {
        if (!cancelled) setState('offline')
      } finally {
        if (!cancelled) timer = setTimeout(probe, HEALTH_POLL_MS)
      }
    }

    probe()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  return state
}

function useStrategyCount() {
  // Strategies are created or removed on other routes, so a committed
  // navigation is the signal to re-read the local registry. `useLocation().key`
  // changes on every navigation and works with a plain <BrowserRouter>,
  // unlike `useNavigation` which requires a data router.
  const location = useLocation()
  const [count, setCount] = useState(() => readStrategies().length)

  useEffect(() => {
    setCount(readStrategies().length)
  }, [location.key])

  return count
}

const HEALTH_COPY = {
  checking: 'Checking backend',
  online: 'Backend online',
  offline: 'Backend unreachable',
}

function HealthIndicator({ state }) {
  return (
    <span
      className={`health health--${state}`}
      title={
        state === 'offline'
          ? 'The API on port 8000 is not responding. Start the backend, then this turns green.'
          : HEALTH_COPY[state]
      }
    >
      <span className="health__dot" aria-hidden="true" />
      {HEALTH_COPY[state]}
    </span>
  )
}

/**
 * Persistent chrome for every route. Only the header lives here; each route
 * renders its own page so the shell has no knowledge of strategy ids.
 *
 * The app bar is deliberately plain: it is the constant the marketing landing
 * page sits under, and the landing page supplies its own sub-navigation.
 */
export default function AppShell() {
  const health = useBackendHealth()
  const strategyCount = useStrategyCount()
  const { pathname } = useLocation()
  // Chat owns its own scroll container so the composer stays pinned to the
  // viewport; every other page scrolls as one document.
  const fixedMain = pathname === '/chat'

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className="app-shell__header">
        <div className="app-shell__bar">
          <div className="brand">
            <span className="brand__mark" aria-hidden="true">
              <Icon name="ssid_chart" size={20} />
            </span>
            <span className="brand__text">
              <span className="brand__name">Quant Strategy Assistant</span>
              <span className="brand__disclaimer">
                Educational prototype. Paper trading only. No guaranteed returns.
              </span>
            </span>
          </div>

          <div className="header-right">
            <HealthIndicator state={health} />
            <nav className="main-nav" aria-label="Main">
              <NavLink
                to="/"
                end
                className={({ isActive }) => `main-nav__link${isActive ? ' main-nav__link--active' : ''}`}
              >
                <Icon name="dashboard" size={17} />
                Overview
              </NavLink>
              <NavLink
                to="/chat"
                className={({ isActive }) => `main-nav__link${isActive ? ' main-nav__link--active' : ''}`}
              >
                <Icon name="forum" size={17} />
                Studio
              </NavLink>
              <NavLink
                to="/strategies"
                className={({ isActive }) => `main-nav__link${isActive ? ' main-nav__link--active' : ''}`}
              >
                <Icon name="grid_view" size={17} />
                Strategies
                {strategyCount > 0 && <span className="main-nav__count">{strategyCount}</span>}
              </NavLink>
            </nav>
          </div>
        </div>
      </header>

      <main
        className={`app-shell__main${fixedMain ? ' app-shell__main--fixed' : ''}`}
        id="main"
        tabIndex={-1}
      >
        <Outlet />
      </main>
    </div>
  )
}