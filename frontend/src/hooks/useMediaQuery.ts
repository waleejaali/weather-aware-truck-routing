import { useEffect, useState } from 'react'

/** Whether a CSS media query matches. Falls back to `fallback` where matchMedia is unavailable (tests, SSR). */
export function useMediaQuery(query: string, fallback = true): boolean {
  const supported = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
  const [matches, setMatches] = useState(() => (supported ? window.matchMedia(query).matches : fallback))

  useEffect(() => {
    if (!supported) return
    const media = window.matchMedia(query)
    const onChange = () => setMatches(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [query, supported])

  return matches
}
