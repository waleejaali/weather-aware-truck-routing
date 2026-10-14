import { useEffect, useRef, useState, type RefObject } from 'react'

/**
 * True once the element has scrolled into view (and stays true), for scroll-reveal animations.
 * Without IntersectionObserver (old browsers, tests) content is shown immediately rather than hidden forever.
 */
export function useInView<T extends Element>(rootMargin = '0px 0px -12% 0px'): [RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    const node = ref.current
    if (inView || !node) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true)
          observer.disconnect()
        }
      },
      { rootMargin, threshold: 0.05 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [inView, rootMargin])

  return [ref, inView]
}
