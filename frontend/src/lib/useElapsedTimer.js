import { useEffect, useState } from 'react'

/**
 * Ticks once a second while `running` is true and resets the moment it stops,
 * so a finished request never leaves a stale timer on screen.
 */
export function useElapsedTimer(running) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    if (!running) {
      setSeconds(0)
      return undefined
    }
    setSeconds(0)
    const id = setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => clearInterval(id)
  }, [running])

  return seconds
}