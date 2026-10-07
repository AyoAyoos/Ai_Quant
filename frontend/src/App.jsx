import { Navigate, Route, Routes } from 'react-router-dom'
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
 * Route map — ENTRY FLOW ONLY.
 *
 *   /                  Public landing page (pre-login entry, always first)
 *   /welcome           Legacy alias of / (redirects)
 *   /login             Public login page (redirects to dashboard when signed in)
 *   /dashboard         Overview / Dashboard (guarded, post-login home)
 *   /studio            AI Strategy Studio (public, no login required)
 *   /chat              AI Strategy Studio alias (guarded)
 *   /strategies        Strategies library (public, no login required)
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
        {/* Public entry: landing is always first, even for signed-in users. */}
        <Route path="/" element={<LandingPage />} />
        <Route path="welcome" element={<Navigate to="/" replace />} />
        {/* Public shell branch: login, studio + strategies need no guard. */}
        <Route element={<AppShell />} path="/">
          <Route path="login" element={<LoginPage />} />
          <Route path="studio" element={<ChatPage />} />
          <Route path="strategies" element={<StrategiesPage />} />
        </Route>
        {/* Guarded shell branch: dashboard + remaining app pages need login. */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
          path="/"
        >
          <Route path="dashboard" element={<OverviewPage />} />
          <Route path="studio/builder" element={<StrategyBuilderPage />} />
          <Route path="chat" element={<ChatPage />} />
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
