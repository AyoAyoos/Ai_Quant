import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * Route guard: unauthenticated visits bounce to /welcome with the attempted
 * location saved in state so login can send the user back afterwards.
 */
export default function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/welcome" replace state={{ from: location }} />
  }

  return children
}
