import { Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import AnalyticsPage from './pages/AnalyticsPage.jsx'
import ApprovalPage from './pages/ApprovalPage.jsx'
import BacktestPage from './pages/BacktestPage.jsx'
import BacktestsHubPage from './pages/BacktestsHubPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import DeploymentPage from './pages/DeploymentPage.jsx'
import DocsPage from './pages/DocsPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import OverviewPage from './pages/OverviewPage.jsx'
import PaperTradingHubPage from './pages/PaperTradingHubPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import StrategiesPage from './pages/StrategiesPage.jsx'
import StrategyOverviewPage from './pages/StrategyOverviewPage.jsx'
import LandingPage from './pages/LandingPage.jsx'
import StrategyBuilderPage from './pages/StrategyBuilderPage.jsx'

/**
 * Route map for the 7-page split — UI ORGANIZATION ONLY.
 *
 *   /welcome           Public landing page (pre-login entry)
 *   /login             Public login page (redirects back after sign-in)
 *   /                  Overview / Dashboard (quick system overview, guarded)
 *   /studio + /chat    AI Strategy Studio (same ChatPage; /chat kept as alias)
 *   /strategies        Strategies library (unchanged)
 *   /backtests         Backtesting hub (links into per-strategy backtest pages)
 *   /analytics         Analytics (reads cached runs, recalculates nothing)
 *   /paper-trading     Paper Trading hub (aggregates deployment histories)
 *   /settings          Settings / System (config + system info)
 *   /docs              Documentation (existing landing content, verbatim)
 *
 * Per-strategy task pages (/strategies/:id, /backtest, /approval, /deployment)
 * are untouched — same components, same API calls, same logic.
 */
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="welcome" element={<LandingPage />} />
        {/* Public shell branch: login keeps the header, no nav, no guard. */}
        <Route element={<AppShell />} path="/">
          <Route path="login" element={<LoginPage />} />
        </Route>
        {/* Guarded shell branch: dashboard + every app page needs login. */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
          path="/"
        >
          <Route index element={<OverviewPage />} />
          <Route path="studio" element={<ChatPage />} />
          <Route path="studio/builder" element={<StrategyBuilderPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="strategies" element={<StrategiesPage />} />
          <Route path="strategies/:id" element={<StrategyOverviewPage />} />
          <Route path="strategies/:id/backtest" element={<BacktestPage />} />
          <Route path="strategies/:id/approval" element={<ApprovalPage />} />
          <Route path="strategies/:id/deployment" element={<DeploymentPage />} />
          <Route path="backtests" element={<BacktestsHubPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="paper-trading" element={<PaperTradingHubPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="docs" element={<DocsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
