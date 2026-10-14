import { useEffect, useState } from 'react'
import type { Page } from '../hooks/useHashRoute'
import { IconArrowRight, IconNavigation } from './icons'

const APP_LINKS: { page: Page; label: string; href: string }[] = [
  { page: 'planner', label: 'Route planner', href: '#/planner' },
  { page: 'checkpoints', label: 'Checkpoints', href: '#/checkpoints' },
]

const SITE_LINKS = [
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Principles', href: '#principles' },
  { label: 'Risk rules', href: '#risk-rules' },
]

function Brand({ onNavigate }: { onNavigate: (page: Page) => void }) {
  return (
    <a
      href="#/"
      onClick={(e) => {
        e.preventDefault()
        onNavigate('home')
      }}
      aria-label="Weather-Aware Routing, home"
      className="flex items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand text-on-brand sm:h-11 sm:w-11">
        <IconNavigation size={22} />
      </span>
      <span className="leading-tight">
        <span className="block whitespace-nowrap text-[15px] font-bold tracking-tight text-ink sm:text-xl">
          Weather-Aware <span className="text-accent">Routing</span>
        </span>
        <span className="eyebrow hidden !text-[10px] !tracking-[0.18em] min-[430px]:block">Truck route intelligence</span>
      </span>
    </a>
  )
}

/**
 * Landing page: brand, in-page links and one primary action. App pages: brand and the two pages.
 * Links are real anchors, so they work with the keyboard, middle-click and the back button.
 */
export function AppHeader({ page, onNavigate }: { page: Page; onNavigate: (page: Page) => void }) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  if (page === 'home') {
    return (
      <header
        className={`sticky top-0 z-[1100] border-b backdrop-blur transition-colors duration-300 ${
          scrolled ? 'border-line bg-canvas/85' : 'border-transparent bg-transparent'
        }`}
      >
        <div className="mx-auto flex max-w-[72rem] items-center justify-between gap-4 px-5 py-4 sm:gap-6 sm:px-8">
          <Brand onNavigate={onNavigate} />
          <nav aria-label="Sections" className="hidden items-center gap-8 md:flex">
            {SITE_LINKS.map((link) => (
              <a key={link.href} href={link.href} className="rounded text-sm font-medium text-muted transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent">
                {link.label}
              </a>
            ))}
          </nav>
          <a
            href="#/planner"
            onClick={(e) => {
              e.preventDefault()
              onNavigate('planner')
            }}
            className="btn-primary group min-h-[2.75rem] shrink-0 whitespace-nowrap !px-4 !text-sm sm:!px-5"
          >
            <span className="sm:hidden">Planner</span>
            <span className="hidden sm:inline">Open planner</span>
            <IconArrowRight size={16} className="hidden transition-transform duration-300 group-hover:translate-x-0.5 sm:block" />
          </a>
        </div>
      </header>
    )
  }

  return (
    <header className="sticky top-0 z-[1100] border-b border-line bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex max-w-[96rem] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-4 sm:px-8">
        <Brand onNavigate={onNavigate} />
        <nav aria-label="Pages" className="flex w-full gap-1 rounded-xl border border-line bg-surface p-1 sm:w-auto">
          {APP_LINKS.map((link) => (
            <a
              key={link.page}
              href={link.href}
              aria-current={page === link.page ? 'page' : undefined}
              onClick={(e) => {
                e.preventDefault()
                onNavigate(link.page)
              }}
              className={`flex-1 rounded-lg px-4 py-2 text-center text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent sm:flex-none ${
                page === link.page ? 'bg-surface-2 text-ink' : 'text-muted hover:text-ink'
              }`}
            >
              {link.label}
            </a>
          ))}
        </nav>
      </div>
    </header>
  )
}
