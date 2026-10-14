import { useEffect, useState } from 'react'

/** The current time in ms, refreshed on an interval, so age-based UI (stale results) updates by itself. */
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])
  return now
}
