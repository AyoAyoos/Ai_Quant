import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * Route guard: unauthenticated visits bounce to /login with the attempted
 * location saved in state so login can send the user back afterwards.
 */
export default function ProtectedRoute({ children }) {
  const { isAuthenticated, authReady } = useAuth()
  const location = useLocation()

  // Supabase restores its session asynchronously on reload: hold the guard
  // until auth is resolved so a valid session never flashes to /login.
  if (!authReady) {
    return null
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return children
}
