/**
 * Supabase client for the QuantNiti frontend.
 *
 * Requires deploy-time env vars (see .env.example):
 *   VITE_SUPABASE_URL
 *   VITE_SUPABASE_ANON_KEY
 */
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = normalizeSupabaseUrl(import.meta.env.VITE_SUPABASE_URL)
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

/**
 * Reduce any pasted value to the bare project origin
 * (https://<ref>.supabase.co). The dashboard also shows the REST endpoint
 * (.../rest/v1); using that here makes supabase-js build doubled paths and
 * every call fails with "Invalid path specified in request URL" (PGRST125).
 */
function normalizeSupabaseUrl(raw) {
  if (!raw) return raw
  const trimmed = raw.trim()
  const withoutPath = trimmed.replace(/^(https?:\/\/[^/]+).*/, '$1')
  if (withoutPath !== trimmed) {
    console.warn(
      'VITE_SUPABASE_URL should be the bare project URL (no /rest/v1 path); using',
      withoutPath,
    )
  }
  return withoutPath
}

/**
 * Null when the env vars are missing (local prototype mode): AuthContext
 * falls back to its localStorage session and the app stays usable.
 */
export const supabase =
  supabaseUrl && supabaseAnonKey ? createClient(supabaseUrl, supabaseAnonKey) : null

if (!supabase) {
  console.warn(
    'Supabase is not configured: set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY. Using prototype auth.',
  )
}

/** Refresh when the cached JWT expires within this window. */
const REFRESH_MARGIN_MS = 60_000

/**
 * Current Supabase JWT, refreshing it first when expired or near expiry.
 * Returns null when logged out / unconfigured / refresh fails — callers
 * must treat null as "prompt re-login", never send it as a dead Bearer.
 */
export async function getValidAccessToken() {
  if (!supabase) return null
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session?.access_token) return null
  const expiresAtMs =
    typeof session.expires_at === 'number' ? session.expires_at * 1000 : null
  if (expiresAtMs === null || expiresAtMs - Date.now() > REFRESH_MARGIN_MS) {
    return session.access_token
  }
  try {
    const { data, error } = await supabase.auth.refreshSession()
    if (error) {
      console.warn('Supabase session refresh failed:', error.message)
      return session.access_token
    }
    return data?.session?.access_token ?? session.access_token
  } catch (err) {
    console.warn('Supabase session refresh threw:', err?.message || err)
    return session.access_token
  }
}

/** Force a refresh regardless of expiry (single-retry path in api.js). */
export async function refreshAccessToken() {
  if (!supabase) return null
  try {
    const { data, error } = await supabase.auth.refreshSession()
    if (error) return null
    return data?.session?.access_token ?? null
  } catch {
    return null
  }
}

/** Current Supabase JWT, or null when logged out / unconfigured. */
export async function getAccessToken() {
  return getValidAccessToken()
}
