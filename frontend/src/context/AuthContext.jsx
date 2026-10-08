import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient.js'

const STORAGE_KEY = 'isLoggedIn'
const NAME_KEY = 'aiq.userName'

const AuthContext = createContext(null)

function nameOf(user) {
  const metaName = user?.user_metadata?.full_name
  if (typeof metaName === 'string' && metaName.trim()) return metaName.trim()
  return user?.email || ''
}

/**
 * Auth state, backed by Supabase when configured (VITE_SUPABASE_URL +
 * VITE_SUPABASE_ANON_KEY). Supabase persists its own session; the context
 * mirrors it so route guards re-render on sign-in/out (including sessions
 * restored on reload via onAuthStateChange).
 *
 * Without Supabase env vars the old prototype session applies instead: any
 * credentials pass and persistence is a single localStorage flag.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [authReady, setAuthReady] = useState(!supabase)

  const [prototypeAuthed, setPrototypeAuthed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const [prototypeName, setPrototypeName] = useState(() => {
    try {
      return localStorage.getItem(NAME_KEY) || ''
    } catch {
      return ''
    }
  })

  useEffect(() => {
    if (!supabase) return undefined
    let mounted = true
    supabase.auth
      .getSession()
      .then(({ data: { session } }) => {
        if (mounted) {
          setUser(session?.user ?? null)
          setAuthReady(true)
        }
      })
      .catch(() => {
        if (mounted) setAuthReady(true)
      })
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (mounted) setUser(session?.user ?? null)
    })
    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [])

  const login = useCallback(async (email, password) => {
    if (!supabase) {
      try {
        localStorage.setItem(STORAGE_KEY, 'true')
      } catch {
        // Storage unavailable (private mode) — session simply won't persist.
      }
      setPrototypeAuthed(true)
      return { ok: true }
    }
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    })
    if (error) return { ok: false, message: error.message }
    return { ok: true }
  }, [])

  const signup = useCallback(async (email, password, fullName) => {
    const name = fullName?.trim() || ''
    if (!supabase) {
      try {
        localStorage.setItem(STORAGE_KEY, 'true')
        if (name) localStorage.setItem(NAME_KEY, name)
      } catch {
        // Storage unavailable (private mode) — session simply won't persist.
      }
      if (name) setPrototypeName(name)
      setPrototypeAuthed(true)
      return { ok: true }
    }
    const { error } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: { data: { full_name: name } },
    })
    if (error) return { ok: false, message: error.message }
    return { ok: true }
  }, [])

  const logout = useCallback(async () => {
    if (supabase) {
      await supabase.auth.signOut()
      setUser(null)
      return
    }
    try {
      localStorage.removeItem(STORAGE_KEY)
      localStorage.removeItem(NAME_KEY)
    } catch {
      // Nothing to clean up.
    }
    setPrototypeName('')
    setPrototypeAuthed(false)
  }, [])

  const value = supabase
    ? {
        isAuthenticated: user !== null,
        userName: nameOf(user),
        user,
        authReady,
        login,
        signup,
        logout,
      }
    : {
        isAuthenticated: prototypeAuthed,
        userName: prototypeName,
        user: null,
        authReady: true,
        login,
        signup,
        logout,
      }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
