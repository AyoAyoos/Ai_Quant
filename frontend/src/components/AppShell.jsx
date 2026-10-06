import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { readStrategies } from '../lib/storage.js'
import Icon from './Icon.jsx'

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

const NAV = [
  { to: '/', label: 'Overview', icon: 'grid_view', end: true },
  { to: '/studio', label: 'Studio', icon: 'forum', end: false },
  { to: '/strategies', label: 'Strategies', icon: 'dashboard', end: false, count: true },
  { to: '/backtests', label: 'Backtesting', icon: 'timeline', end: false },
  { to: '/analytics', label: 'Analytics', icon: 'calculate', end: false },
  { to: '/paper-trading', label: 'Paper Trading', icon: 'verified', end: false },
]

const NAV_SECONDARY = [
  { to: '/settings', label: 'Settings', icon: 'security', end: false },
  { to: '/docs', label: 'Documentation', icon: 'article', end: false },
]

/**
 * Persistent chrome for every route — 7 pages + documentation.
 *
 * PAGE SPLIT ONLY: this shell adds navigation between the page wrappers. It
 * has no knowledge of strategy ids, makes no API call except the registry
 * count, and changes no button, workflow or calculation anywhere.
 */
export default function AppShell() {
  const strategyCount = useStrategyCount()
  const { pathname } = useLocation()
  // Studio owns its own scroll container so the composer stays pinned to the
  // viewport; every other page scrolls as one document. /chat is the legacy
  // alias of /studio and behaves the same.
  const fixedMain = pathname === '/studio' || pathname === '/chat'

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
            <nav className="main-nav" aria-label="Main">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `main-nav__link${isActive || (item.to === '/studio' && pathname === '/chat') ? ' main-nav__link--active' : ''}`
                  }
                >
                  <Icon name={item.icon} size={17} />
                  {item.label}
                  {item.count && strategyCount > 0 && (
                    <span className="main-nav__count">{strategyCount}</span>
                  )}
                </NavLink>
              ))}
            </nav>
            <nav className="main-nav" aria-label="Secondary">
              {NAV_SECONDARY.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `main-nav__link${isActive ? ' main-nav__link--active' : ''}`
                  }
                >
                  <Icon name={item.icon} size={17} />
                  {item.label}
                </NavLink>
              ))}
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
