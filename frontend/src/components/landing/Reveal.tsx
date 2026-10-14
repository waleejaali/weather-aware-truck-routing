import type { CSSProperties, ElementType, ReactNode } from 'react'
import { useInView } from '../../hooks/useInView'

interface Props {
  children: ReactNode
  /** Extra delay in ms, to stagger siblings. */
  delay?: number
  className?: string
  as?: ElementType
}

/** Fades and lifts its children into place the first time they scroll into view. */
export function Reveal({ children, delay = 0, className = '', as: Tag = 'div' }: Props) {
  const [ref, shown] = useInView<HTMLElement>()
  return (
    <Tag ref={ref} className={`reveal ${className}`} data-revealed={shown} style={{ '--reveal-delay': `${delay}ms` } as CSSProperties}>
      {children}
    </Tag>
  )
}
