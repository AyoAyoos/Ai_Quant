import { Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell.jsx'
import ApprovalPage from './pages/ApprovalPage.jsx'
import BacktestPage from './pages/BacktestPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import DeploymentPage from './pages/DeploymentPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import StrategiesPage from './pages/StrategiesPage.jsx'
import StrategyOverviewPage from './pages/StrategyOverviewPage.jsx'

/**
 * One file that is nothing but routes — each screen lives in src/pages so the
 * task-per-page split is visible in the router itself.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<ChatPage />} />
        <Route path="strategies" element={<StrategiesPage />} />
        <Route path="strategies/:id" element={<StrategyOverviewPage />} />
        <Route path="strategies/:id/backtest" element={<BacktestPage />} />
        <Route path="strategies/:id/approval" element={<ApprovalPage />} />
        <Route path="strategies/:id/deployment" element={<DeploymentPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}