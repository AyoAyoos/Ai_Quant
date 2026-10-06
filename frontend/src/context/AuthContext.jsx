import { createContext, useCallback, useContext, useState } from 'react'

const STORAGE_KEY = 'isLoggedIn'

const AuthContext = createContext(null)

/**
 * Frontend-prototype auth state. Any credentials pass; persistence is a
 * single localStorage flag so a reload keeps the session.
 */
export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const login = useCallback((email, password) => {
    void email
    void password
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
    } catch {
      // Storage unavailable (private mode) — session simply won't persist.
    }
    setIsAuthenticated(true)
  }, [])

  const logout = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // Nothing to clean up.
    }
    setIsAuthenticated(false)
  }, [])

  return <AuthContext.Provider value={{ isAuthenticated, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
