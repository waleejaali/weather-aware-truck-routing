import type { CSSProperties, ReactNode } from 'react'
import type { Page } from '../../hooks/useHashRoute'
import { riskMeta } from '../../lib/risk'
import { HAZARD_RULES, LOAD_RULES, RULE_LEVELS } from '../../lib/riskRules'
import { IconArrowRight, IconChevronDown, IconClock, IconLayers, IconNavigation, IconShield, IconSliders, IconTruck } from '../icons'
import { Reveal } from './Reveal'

interface Props {
  onNavigate: (page: Page) => void
}

// Real capture of the working planner (Chicago to Atlanta, 42,000 lb). See frontend/public/landing.
const PREVIEW = { src: '/landing/planner-preview.webp', width: 1440, height: 1720 }

const STEPS = [
  {
    title: 'Enter the trip',
    body: 'Origin, destination, departure time and load weight. Choose how often to check the weather: every 10, 25 or 50 miles.',
  },
  {
    title: 'We forecast each stop',
    body: "We estimate when you'll reach every checkpoint, then look up the hourly forecast for that moment, not the weather at departure.",
  },
  {
    title: 'Compare and decide',
    body: 'See each route’s risk mile by mile, why it ranks where it does, and how leaving later changes the picture.',
  },
]

const PRINCIPLES = [
  {
    Icon: IconClock,
    title: 'Weather at arrival time',
    body: "Each checkpoint is matched to your estimated arrival, so a storm that clears before you get there doesn't count against the route.",
  },
  {
    Icon: IconTruck,
    title: 'Your load changes the answer',
    body: 'Heavier trucks tolerate less wind. The same 40 mph wind is High for a light load and Severe above 40,000 lb.',
  },
  {
    Icon: IconShield,
    title: 'Missing data is never “safe”',
    body: "If the forecast doesn't cover enough of a route, it isn't recommended. Gaps are shown as gaps, never as zero.",
  },
  {
    Icon: IconSliders,
    title: 'Explore the next 48 hours',
    body: 'Step through departures up to two days out and see which route comes out ahead at each one.',
  },
]

function SectionHeading({ id, eyebrow, title, intro }: { id: string; eyebrow: string; title: string; intro?: string }) {
  return (
    <div className="max-w-2xl">
      <p className="eyebrow">{eyebrow}</p>
      <h2 id={id} className="mt-4 text-balance text-3xl font-bold leading-tight tracking-tight text-ink sm:text-4xl">
        {title}
      </h2>
      {intro ? <p className="mt-5 text-pretty text-base leading-relaxed text-muted sm:text-lg">{intro}</p> : null}
    </div>
  )
}

/** An anchor that navigates in-app without a page load, but still works as a real link (middle-click, copy). */
function PageLink({ page, onNavigate, className, children }: { page: Page; onNavigate: (p: Page) => void; className?: string; children: ReactNode }) {
  const href = page === 'home' ? '#/' : `#/${page}`
  return (
    <a
      href={href}
      className={className}
      onClick={(e) => {
        e.preventDefault()
        onNavigate(page)
      }}
    >
      {children}
    </a>
  )
}

const wrap = 'mx-auto w-full max-w-[72rem] px-5 sm:px-8'
const section = 'scroll-mt-20 border-t border-line py-20 sm:py-28'

export function LandingPage({ onNavigate }: Props) {
  return (
    <div>
      {/* 1. Hero */}
      <section aria-labelledby="hero-heading" className="pt-16 sm:pt-24">
        <div className={`${wrap} text-center`}>
          <p className="eyebrow enter" style={{ '--d': '0ms' } as CSSProperties}>
            Weather risk for truck routes
          </p>
          <h1
            id="hero-heading"
            className="enter mx-auto mt-6 max-w-4xl text-balance text-[clamp(2.25rem,5.6vw,4rem)] font-bold leading-[1.06] tracking-tight text-ink"
            style={{ '--d': '80ms' } as CSSProperties}
          >
            Plan around the <span className="text-accent">weather</span> you’ll actually meet.
          </h1>
          <p className="enter mx-auto mt-7 max-w-2xl text-pretty text-lg leading-relaxed text-muted sm:text-xl" style={{ '--d': '170ms' } as CSSProperties}>
            Compare up to three truck routes using the forecast for the hour you’ll reach each point, adjusted for your load. Know which route is
            safest to run, and when.
          </p>
          <div className="enter mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-4" style={{ '--d': '260ms' } as CSSProperties}>
            <PageLink page="planner" onNavigate={onNavigate} className="btn-primary group min-h-[3.25rem] px-8">
              Plan a route
              <IconArrowRight size={18} className="transition-transform duration-300 group-hover:translate-x-1" />
            </PageLink>
            <a href="#how-it-works" className="group inline-flex items-center gap-2 rounded-lg px-1 py-2 text-sm font-semibold text-muted transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent">
              See how it works
              <IconChevronDown size={16} className="transition-transform duration-300 group-hover:translate-y-0.5" />
            </a>
          </div>
          <p className="enter mt-5 text-sm text-faint" style={{ '--d': '330ms' } as CSSProperties}>
            No account needed. Forecasts by Open-Meteo, routing by OpenRouteService.
          </p>
        </div>

        <figure className="enter relative mx-auto mt-16 w-full max-w-[68rem] px-5 sm:mt-20 sm:px-8" style={{ '--d': '420ms' } as CSSProperties}>
          <div className="preview-halo" aria-hidden="true" />
          <div className="preview-fade">
            <div className="preview-frame">
              <img
                src={PREVIEW.src}
                width={PREVIEW.width}
                height={PREVIEW.height}
                alt="The route planner showing a Chicago to Atlanta trip: trip details on the left, a risk-coloured map of the recommended route on the right, and the recommendation below."
                decoding="async"
                fetchPriority="high"
                className="block h-auto w-full"
              />
            </div>
          </div>
          <figcaption className="mt-5 text-center text-xs text-faint">A real assessment: Chicago to Atlanta, 42,000 lb, checkpoints every 50 miles.</figcaption>
        </figure>
      </section>

      {/* 2. How it works */}
      <section id="how-it-works" aria-labelledby="how-heading" className={section}>
        <div className={wrap}>
          <Reveal>
            <SectionHeading id="how-heading" eyebrow="How it works" title="From trip details to a decision, in three steps." />
          </Reveal>
          <ol className="mt-16 grid gap-12 md:grid-cols-3 md:gap-10">
            {STEPS.map((step, i) => (
              <Reveal key={step.title} as="li" delay={i * 130}>
                <div className="relative h-px bg-line" aria-hidden="true">
                  <div className="draw-line absolute inset-0 bg-accent" />
                </div>
                <p className="mt-6 text-sm font-semibold tabular-nums text-accent">{String(i + 1).padStart(2, '0')}</p>
                <h3 className="mt-3 text-xl font-semibold text-ink">{step.title}</h3>
                <p className="mt-3 leading-relaxed text-muted">{step.body}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* 3. Principles */}
      <section id="principles" aria-labelledby="principles-heading" className={section}>
        <div className={wrap}>
          <Reveal>
            <SectionHeading
              id="principles-heading"
              eyebrow="Principles"
              title="Built to be trusted, not just to look confident."
              intro="A route recommendation is only useful if you can see what it's based on. These are the choices behind every result."
            />
          </Reveal>
          <ul className="mt-16 grid gap-5 md:grid-cols-2">
            {PRINCIPLES.map(({ Icon, title, body }, i) => (
              <Reveal key={title} as="li" delay={(i % 2) * 110 + Math.floor(i / 2) * 90}>
                <article className="lift h-full rounded-2xl border border-line p-7 sm:p-9">
                  <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-surface-2 text-accent">
                    <Icon size={20} />
                  </span>
                  <h3 className="mt-6 text-xl font-semibold text-ink">{title}</h3>
                  <p className="mt-3 leading-relaxed text-muted">{body}</p>
                </article>
              </Reveal>
            ))}
          </ul>
        </div>
      </section>

      {/* 4. Risk rules */}
      <section id="risk-rules" aria-labelledby="rules-heading" className={section}>
        <div className={wrap}>
          <Reveal>
            <SectionHeading
              id="rules-heading"
              eyebrow="Risk rules"
              title="Clear rules, in the open."
              intro="Every checkpoint is classified with these thresholds, and the worst hazard sets its level. Nothing is hidden behind a score."
            />
          </Reveal>

          <div className="mt-16 space-y-12">
            {HAZARD_RULES.map((rule) => (
              <Reveal key={rule.key} as="div">
                <section aria-labelledby={`rule-${rule.key}`}>
                  <h3 id={`rule-${rule.key}`} className="flex items-baseline gap-2 text-lg font-semibold text-ink">
                    {rule.label}
                    <span className="text-sm font-normal text-faint">{rule.unit}</span>
                  </h3>
                  <ol className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
                    {RULE_LEVELS.map((level, i) => {
                      const meta = riskMeta(level)
                      return (
                        <li key={level} className="rounded-xl border border-line px-4 pb-4 pt-0 last:col-span-2 sm:last:col-span-1">
                          <span
                            className="fill-bar -mx-4 mb-4 block h-1 rounded-t-xl"
                            style={{ background: meta.color, '--i': i } as CSSProperties}
                            aria-hidden="true"
                          />
                          <p className="flex items-center gap-1.5 text-sm font-medium text-ink">
                            <span aria-hidden="true" style={{ color: meta.color }} className="text-[11px] leading-none">
                              {meta.symbol}
                            </span>
                            {meta.label}
                          </p>
                          <p className="mt-2 text-sm tabular-nums text-muted">{rule.bands[i]}</p>
                        </li>
                      )
                    })}
                  </ol>
                </section>
              </Reveal>
            ))}

            <Reveal>
              <div className="rounded-2xl border border-line bg-surface p-7 sm:p-9">
                <h3 className="flex items-center gap-2.5 text-lg font-semibold text-ink">
                  <IconLayers size={18} className="text-accent" />
                  Load rules
                </h3>
                <p className="mt-2 text-sm text-muted">Applied on top of the thresholds above; they can only raise a level, never lower it.</p>
                <ul className="mt-5 space-y-3">
                  {LOAD_RULES.map((rule) => (
                    <li key={rule} className="flex gap-3 text-muted">
                      <span aria-hidden="true" className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                      {rule}
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Closing call to action */}
      <section aria-labelledby="cta-heading" className="border-t border-line py-20 sm:py-28">
        <Reveal className={`${wrap} text-center`}>
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand text-on-brand">
            <IconNavigation size={22} />
          </span>
          <h2 id="cta-heading" className="mx-auto mt-8 max-w-2xl text-balance text-3xl font-bold leading-tight tracking-tight text-ink sm:text-4xl">
            See what the forecast says about your next trip.
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-lg text-muted">Enter a trip and compare your routes in a few seconds.</p>
          <PageLink page="planner" onNavigate={onNavigate} className="btn-primary group mt-10 min-h-[3.25rem] px-8">
            Open the planner
            <IconArrowRight size={18} className="transition-transform duration-300 group-hover:translate-x-1" />
          </PageLink>
        </Reveal>
      </section>

      {/* Footer */}
      <footer className="border-t border-line">
        <div className={`${wrap} flex flex-col gap-8 py-12 sm:flex-row sm:items-start sm:justify-between`}>
          <div className="max-w-sm">
            <p className="text-base font-bold text-ink">
              Weather-Aware <span className="text-accent">Routing</span>
            </p>
            <p className="mt-2 text-sm text-faint">Forecast-based insights for truck routes. Recommendations are not a guarantee of safety.</p>
          </div>
          <nav aria-label="Footer" className="flex gap-x-8 gap-y-3 text-sm">
            <PageLink page="planner" onNavigate={onNavigate} className="text-muted hover:text-ink">
              Route planner
            </PageLink>
            <PageLink page="checkpoints" onNavigate={onNavigate} className="text-muted hover:text-ink">
              Checkpoints
            </PageLink>
            <a href="#risk-rules" className="text-muted hover:text-ink">
              Risk rules
            </a>
          </nav>
        </div>
        <div className={`${wrap} border-t border-line py-6 text-xs text-faint`}>
          <a className="text-muted underline" href="https://open-meteo.com/" target="_blank" rel="noreferrer">
            Weather data by Open-Meteo.com
          </a>{' '}
          (
          <a className="text-muted underline" href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
            CC BY 4.0
          </a>
          ). Routing by OpenRouteService. Map tiles &copy; OpenStreetMap contributors.
        </div>
      </footer>
    </div>
  )
}
