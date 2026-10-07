import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { readStrategies } from '../lib/storage.js'
import { useAuth } from '../context/AuthContext.jsx'
import Icon from './Icon.jsx'
import LineSidebar from './LineSidebar.jsx'

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

const SIDEBAR_ITEMS = [
  { label: 'Dashboard', to: '/dashboard', icon: 'grid_view', end: true },
  {
    label: 'Studio',
    to: '/studio',
    icon: 'forum',
    match: ['/studio', '/chat', '/studio/builder'],
  },
  { label: 'Builder', to: '/studio/builder', icon: 'build' },
  { label: 'Strategies', to: '/strategies', icon: 'dashboard', match: ['/strategies'] },
  { label: 'Backtesting', to: '/backtests', icon: 'timeline' },
  { label: 'Analytics', to: '/analytics', icon: 'calculate' },
  { label: 'Paper Trading', to: '/paper-trading', icon: 'verified' },
  { label: 'Settings', to: '/settings', icon: 'security' },
]

/**
 * Persistent chrome: top bar + (guarded pages) fixed left sidebar.
 *
 * Top bar: favicon + "AI Quant" left, Login/Logout right, deep purple.
 * The old horizontal pill nav is gone; guarded pages navigate via the
 * left LineSidebar and render untouched in the right content container.
 */
export default function AppShell() {
  const strategyCount = useStrategyCount()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { isAuthenticated, logout } = useAuth()
  // Studio owns its own scroll container so the composer stays pinned to the
  // viewport; every other page scrolls as one document. /chat is the legacy
  // alias of /studio and behaves the same.
  const fixedMain = pathname === '/studio' || pathname === '/chat'
  // The login view keeps only the minimalist brand bar so the auth art owns focus.
  const isLogin = pathname === '/login'
  const [navOpen, setNavOpen] = useState(false)

  const items = SIDEBAR_ITEMS.map((item) =>
    item.label === 'Strategies' ? { ...item, badge: strategyCount } : item,
  )

  const isActiveItem = (item) => {
    if (item.end) return pathname === item.to
    if (Array.isArray(item.match) && item.match.length > 0) {
      return item.match.some((p) => (p === '/' ? pathname === '/' : pathname.startsWith(p)))
    }
    if (!item.to) return false
    return pathname === item.to || pathname.startsWith(`${item.to}/`)
  }

  const activeMatches = items.filter(isActiveItem)
  // Longest route wins so /studio/builder titles Builder, not Studio.
  const activeItem =
    activeMatches.sort((a, b) => (b.to || '').length - (a.to || '').length)[0] || {}
  const activeLabel = activeItem.label || ''

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className="app-shell__header">
        <div className={`app-shell__bar${isLogin ? ' app-shell__bar--auth' : ' app-shell__bar--app'}`}>
          <div className="app-shell__bar-left">
            {!isLogin && (
              <button
                className="nav-toggle"
                type="button"
                onClick={() => setNavOpen((open) => !open)}
                aria-expanded={navOpen}
                aria-controls="app-sidebar"
                aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
              >
                <Icon name={navOpen ? 'close' : 'menu'} size={22} />
              </button>
            )}
            <Link className="brand-auth" to="/" aria-label="AI Quant home">
              <img className="brand-auth__logo" src="/favicon.svg" alt="" width={30} height={30} />
              <span className="brand-auth__name">AI Quant</span>
            </Link>
          </div>
          {!isLogin && activeLabel && (
            <span className="app-shell__title" aria-live="polite">
              {activeLabel}
            </span>
          )}
          {isAuthenticated ? (
            <button
              className="login-btn login-btn--app"
              type="button"
              onClick={() => {
                logout()
                navigate('/', { replace: true })
              }}
            >
              Logout
            </button>
          ) : (
            !isLogin && (
              <Link className="login-btn login-btn--app" to="/login">
                Login
              </Link>
            )
          )}
        </div>
      </header>

      {isLogin ? (
        <main className="app-shell__main" id="main" tabIndex={-1}>
          <Outlet />
        </main>
      ) : (
        <div className="app-shell__body">
          <LineSidebar
            id="app-sidebar"
            items={items}
            defaultActive={0}
            accentColor="#AF719D"
            markerColor="#8B639B"
            textColor="#403D88"
            fontSize={1.1}
            itemGap={12}
            markerGap={10}
            markerLength={40}
            maxShift={20}
            proximityRadius={100}
            showIndex={false}
            showMarker={false}
            smoothing={100}
            tickScale={0.5}
            scaleTick={false}
            falloff="smooth"
            open={navOpen}
            onNavigate={() => setNavOpen(false)}
            onItemClick={(index, label) => {
              // TODO: Hook this up to your routing logic (e.g., react-router useNavigate)
              // Routing is handled via each item's `to`; this is the analytics hook.
              if (typeof window !== 'undefined' && window.console) {
                window.console.debug('[sidebar]', index, label)
              }
            }}
          />
          <main
            className={`app-shell__main${fixedMain ? ' app-shell__main--fixed' : ''}`}
            id="main"
            tabIndex={-1}
          >
            <Outlet />
          </main>
        </div>
      )}
    </div>
  )
}
