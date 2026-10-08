import { createContext, useCallback, useContext, useState } from 'react'

const STORAGE_KEY = 'isLoggedIn'
const NAME_KEY = 'aiq.userName'

const AuthContext = createContext(null)

/**
 * Frontend-prototype auth state. Any credentials pass; persistence is a
 * single localStorage flag so a reload keeps the session, plus the display
 * name captured at account creation for the sidebar profile.
 */
export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const [userName, setUserName] = useState(() => {
    try {
      return localStorage.getItem(NAME_KEY) || ''
    } catch {
      return ''
    }
  })

  const login = useCallback((email, password, fullName) => {
    void email
    void password
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
      // Sign-in has no name field: keep whatever name is already stored.
      if (fullName && fullName.trim()) {
        const name = fullName.trim()
        localStorage.setItem(NAME_KEY, name)
        setUserName(name)
      }
    } catch {
      // Storage unavailable (private mode) — session simply won't persist.
    }
    setIsAuthenticated(true)
  }, [])

  const logout = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY)
      localStorage.removeItem(NAME_KEY)
    } catch {
      // Nothing to clean up.
    }
    setUserName('')
    setIsAuthenticated(false)
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, userName, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
