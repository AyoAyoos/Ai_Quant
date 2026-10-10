import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { clearActiveUserData, setActiveUserId } from '../lib/storage.js'

/** Single local user (auth removed). */
const LOCAL_SCOPE_ID = 'local'
const STORAGE_KEY = 'isLoggedIn'
const NAME_KEY = 'aiq.userName'

/** The one fixed credential that logs in. Shown as a hint on the login page. */
export const FIXED_EMAIL = 'admin@local'
export const FIXED_PASSWORD = 'admin'
const FIXED_NAME = 'Admin'

const AuthContext = createContext(null)

/**
 * Dummy auth: no providers, no tokens. login() accepts only the fixed
 * credential pair; persistence is a localStorage flag.
 */
export function AuthProvider({ children }) {
  const [authed, setAuthed] = useState(() => {
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

  useEffect(() => {
    setActiveUserId(authed ? LOCAL_SCOPE_ID : null)
  }, [authed])

  const login = useCallback(async (email, password) => {
    const emailOk =
      typeof email === 'string' && email.trim().toLowerCase() === FIXED_EMAIL
    const passOk = password === FIXED_PASSWORD
    if (!emailOk || !passOk) {
      return { ok: false, message: `Use ${FIXED_EMAIL} / ${FIXED_PASSWORD}.` }
    }
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
      localStorage.setItem(NAME_KEY, FIXED_NAME)
    } catch {
      // Storage unavailable — session simply won't persist.
    }
    setUserName(FIXED_NAME)
    setAuthed(true)
    return { ok: true }
  }, [])

  const logout = useCallback(async () => {
    // Wipe the local browser cache first so the next login starts clean.
    clearActiveUserData()
    try {
      localStorage.removeItem(STORAGE_KEY)
      localStorage.removeItem(NAME_KEY)
    } catch {
      // Nothing to clean up.
    }
    setUserName('')
    setAuthed(false)
  }, [])

  // Stubs kept so old imports don't break; auth UI no longer calls them.
  const signup = useCallback(async () => ({ ok: false, message: 'Sign-up is disabled.' }), [])
  const verifySignupOtp = useCallback(async () => ({ ok: false }), [])
  const resendSignupOtp = useCallback(async () => ({ ok: false }), [])

  const value = {
    isAuthenticated: authed,
    userName,
    user: authed ? { email: FIXED_EMAIL, name: FIXED_NAME } : null,
    authReady: true,
    login,
    signup,
    verifySignupOtp,
    resendSignupOtp,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
