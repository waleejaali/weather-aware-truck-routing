import { useCallback, useEffect, useState } from 'react'

export type Page = 'home' | 'planner' | 'checkpoints'

const HASH: Record<Page, string> = { home: '#/', planner: '#/planner', checkpoints: '#/checkpoints' }

/**
 * Anything that is not an app page is the landing page. That includes in-page anchors such as "#how-it-works",
 * so smooth-scrolling links on the landing page never navigate away from it.
 */
function current(): Page {
  const hash = window.location.hash
  if (hash === HASH.planner) return 'planner'
  if (hash === HASH.checkpoints) return 'checkpoints'
  return 'home'
}

/** Tiny hash router for the three pages: no dependency, and the browser's back button works. */
export function useHashRoute(): [Page, (page: Page) => void] {
  const [page, setPage] = useState<Page>(current)

  useEffect(() => {
    const onChange = () => setPage(current())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = useCallback((next: Page) => {
    window.location.hash = HASH[next]
    setPage(next)
  }, [])

  return [page, navigate]
}
