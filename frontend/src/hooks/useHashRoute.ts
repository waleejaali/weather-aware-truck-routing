import { useCallback, useEffect, useState } from 'react'

export type Page = 'planner' | 'checkpoints'

const HASH: Record<Page, string> = { planner: '#/', checkpoints: '#/checkpoints' }

function current(): Page {
  return window.location.hash === HASH.checkpoints ? 'checkpoints' : 'planner'
}

/** Tiny hash router for the two pages: no dependency, and the browser's back button works. */
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
