import { NavLink } from 'react-router-dom'

const TABS = [
  { key: '', label: 'Overview' },
  { key: 'backtest', label: 'Backtest' },
  { key: 'approval', label: 'Approval' },
  { key: 'deployment', label: 'Deployment' },
]

/**
 * Sub-navigation for one strategy's task pages.
 * Every tab is always reachable — pages explain why an action does not apply
 * at the current status instead of the link disappearing.
 */
export default function StrategyTabs({ strategyId }) {
  return (
    <nav className="main-nav" aria-label="Strategy sections" style={{ width: 'fit-content', maxWidth: '100%' }}>
      {TABS.map((tab) => {
        const to = tab.key ? `/strategies/${strategyId}/${tab.key}` : `/strategies/${strategyId}`
        return (
          <NavLink
            key={tab.key || 'overview'}
            to={to}
            end={tab.key === ''}
            className={({ isActive }) => `main-nav__link${isActive ? ' main-nav__link--active' : ''}`}
          >
            {tab.label}
          </NavLink>
        )
      })}
    </nav>
  )
}