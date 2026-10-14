import type { Page } from '../hooks/useHashRoute'
import { IconNavigation } from './icons'

const LINKS: { page: Page; label: string; href: string }[] = [
  { page: 'planner', label: 'Route planner', href: '#/' },
  { page: 'checkpoints', label: 'Checkpoints', href: '#/checkpoints' },
]

/** Brand mark plus the two pages. Links are real anchors, so they work with the keyboard, middle-click and back button. */
export function AppHeader({ page, onNavigate }: { page: Page; onNavigate: (page: Page) => void }) {
  return (
    <header className="sticky top-0 z-[1100] border-b border-line bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex max-w-[96rem] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-4 sm:px-8">
        <a href="#/" onClick={(e) => { e.preventDefault(); onNavigate('planner') }} className="flex items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand text-on-brand">
            <IconNavigation size={22} />
          </span>
          <span className="leading-tight">
            <span className="block text-lg font-bold tracking-tight text-ink sm:text-xl">
              Weather-Aware <span className="text-accent">Routing</span>
            </span>
            <span className="eyebrow block !text-[10px] !tracking-[0.18em]">Truck route intelligence</span>
          </span>
        </a>

        <nav aria-label="Pages" className="flex w-full gap-1 rounded-xl border border-line bg-surface p-1 sm:w-auto">
          {LINKS.map((link) => (
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
