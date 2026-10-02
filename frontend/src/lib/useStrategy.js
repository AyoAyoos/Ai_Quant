import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchStrategy, isNetworkError, isNotFound } from './api.js'
import { getCachedBacktest } from './storage.js'

/**
 * Loads GET /strategies/{id} and exposes `refresh()`.
 *
 * The live detail response is the source of truth for status, so every gate
 * action calls refresh() afterwards instead of patching local state.
 */
export function useStrategyDetail(strategyId) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(Boolean(strategyId))
  const [error, setError] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const refresh = useCallback(async () => {
    if (!strategyId) {
      setLoading(false)
      return null
    }
    try {
      const data = await fetchStrategy(strategyId)
      if (!alive.current) return data
      setDetail(data)
      setError(null)
      setNotFound(false)
      return data
    } catch (err) {
      if (!alive.current) return null
      setError(err)
      setNotFound(isNotFound(err))
      return null
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [strategyId])

  useEffect(() => {
    setDetail(null)
    setNotFound(false)
    setError(null)
    setLoading(Boolean(strategyId))
    refresh()
  }, [strategyId, refresh])

  return {
    detail,
    status: detail?.status ?? null,
    loading,
    error,
    notFound,
    networkError: isNetworkError(error),
    refresh,
  }
}

/**
 * The last backtest response cached in this browser, plus its local run time.
 * The backend exposes no endpoint to read stored results back, so this is the
 * only way to show a previous run without re-running it.
 */
export function useCachedBacktest(strategyId) {
  const [entry, setEntry] = useState(() => getCachedBacktest(strategyId))

  useEffect(() => {
    setEntry(getCachedBacktest(strategyId))
  }, [strategyId])

  return entry
}