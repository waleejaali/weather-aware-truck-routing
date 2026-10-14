import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HAZARD_RULES, LOAD_RULES } from '../../lib/riskRules'
import { LandingPage } from './LandingPage'
import { Reveal } from './Reveal'

afterEach(() => vi.unstubAllGlobals())

describe('LandingPage', () => {
  const page = (onNavigate = vi.fn()) => {
    render(<LandingPage onNavigate={onNavigate} />)
    return onNavigate
  }

  it('leads with one clear promise and one primary action', () => {
    page()
    expect(screen.getByRole('heading', { level: 1, name: /Plan around the weather you’ll actually meet\./ })).toBeInTheDocument()
    expect(screen.getByText(/forecast for the hour you’ll reach each point, adjusted for your load/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Plan a route/ })).toHaveAttribute('href', '#/planner')
  })

  it('sends the primary call to action to the planner without a page load', async () => {
    const onNavigate = page()
    await userEvent.click(screen.getByRole('link', { name: /Plan a route/ }))
    expect(onNavigate).toHaveBeenCalledWith('planner')
  })

  it('has the closing call to action and footer links go to the app pages', async () => {
    const onNavigate = page()
    await userEvent.click(screen.getByRole('link', { name: /Open the planner/ }))
    expect(onNavigate).toHaveBeenLastCalledWith('planner')
    const footer = within(screen.getByRole('navigation', { name: 'Footer' }))
    await userEvent.click(footer.getByRole('link', { name: 'Checkpoints' }))
    expect(onNavigate).toHaveBeenLastCalledWith('checkpoints')
  })

  it('shows a real product screenshot, described honestly', () => {
    page()
    const img = screen.getByRole('img', { name: /route planner showing a Chicago to Atlanta trip/ })
    expect(img).toHaveAttribute('src', '/landing/planner-preview.webp')
    expect(img).toHaveAttribute('width')
    expect(img).toHaveAttribute('height') // reserved space: no layout shift while it loads
    expect(screen.getByText(/A real assessment: Chicago to Atlanta, 42,000 lb, checkpoints every 50 miles\./)).toBeInTheDocument()
  })

  it('has three focused content sections plus the closing call to action', () => {
    page()
    expect(screen.getByRole('heading', { name: 'From trip details to a decision, in three steps.' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Built to be trusted, not just to look confident.' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Clear rules, in the open.' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'See what the forecast says about your next trip.' })).toBeInTheDocument()
    expect(document.getElementById('how-it-works')).toBeInTheDocument()
    expect(document.getElementById('principles')).toBeInTheDocument()
    expect(document.getElementById('risk-rules')).toBeInTheDocument()
  })

  it('explains the three steps and the four principles, with no invented numbers or endorsements', () => {
    const { container } = render(<LandingPage onNavigate={() => {}} />)
    expect(within(document.getElementById('how-it-works')!).getAllByRole('listitem')).toHaveLength(3)
    expect(within(document.getElementById('principles')!).getAllByRole('article')).toHaveLength(4)
    expect(screen.getByText('Weather at arrival time')).toBeInTheDocument()
    expect(screen.getByText('Missing data is never “safe”')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/testimonial|trusted by|customers|★★|\d+\+? (drivers|fleets|users)/i)
  })

  it('shows the real thresholds, exactly as the backend applies them', () => {
    page()
    // These literals are the assignment's rules: lower bounds inclusive, rain/snow Severe upper bound inclusive.
    const expected: Record<string, string[]> = {
      Wind: ['< 25', '25 to < 35', '35 to < 45', '45 to < 55', '≥ 55'],
      Rain: ['< 0.10', '0.10 to < 0.25', '0.25 to < 0.50', '0.50 to 1.00', '> 1.00'],
      Snow: ['< 0.5', '0.5 to < 1.0', '1.0 to < 2.0', '2.0 to 3.0', '> 3.0'],
    }
    for (const rule of HAZARD_RULES) {
      const section = screen.getByRole('region', { name: new RegExp(`^${rule.label}`) })
      const items = within(section).getAllByRole('listitem')
      expect(items).toHaveLength(5)
      expect(items.map((li) => li.textContent)).toEqual(
        ['Low', 'Moderate', 'High', 'Severe', 'No Travel'].map((label, i) => expect.stringContaining(label + expected[rule.label][i])),
      )
    }
    expect(LOAD_RULES.join(' ')).toMatch(/55 mph or more is No Travel for any load/)
    expect(LOAD_RULES.join(' ')).toMatch(/45 to 54 mph with a load over 30,000 lb is No Travel/)
    expect(LOAD_RULES.join(' ')).toMatch(/35 to 44 mph with a load over 40,000 lb is Severe/)
    expect(screen.getByText(/can only raise a level, never lower it/)).toBeInTheDocument()
  })

  it('uses text and shapes for every risk level, not colour alone', () => {
    page()
    const wind = screen.getByRole('region', { name: /^Wind/ })
    expect(within(wind).getByText('■')).toBeInTheDocument() // Severe
    expect(within(wind).getByText('✕')).toBeInTheDocument() // No Travel
  })
})

describe('Reveal (scroll animation)', () => {
  class FakeObserver {
    static instances: FakeObserver[] = []
    callback: IntersectionObserverCallback
    constructor(callback: IntersectionObserverCallback) {
      this.callback = callback
      FakeObserver.instances.push(this)
    }
    observe() {}
    disconnect() {}
  }

  it('stays hidden until it scrolls into view, then reveals once', () => {
    FakeObserver.instances = []
    vi.stubGlobal('IntersectionObserver', FakeObserver)
    render(<Reveal delay={120}>hello</Reveal>)
    const node = screen.getByText('hello')
    expect(node).toHaveAttribute('data-revealed', 'false')
    expect(node.style.getPropertyValue('--reveal-delay')).toBe('120ms')

    act(() => {
      FakeObserver.instances[0].callback([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver)
    })
    expect(node).toHaveAttribute('data-revealed', 'false') // off-screen callbacks do nothing

    act(() => {
      FakeObserver.instances[0].callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
    })
    expect(node).toHaveAttribute('data-revealed', 'true')
  })

  it('shows content immediately where IntersectionObserver does not exist, instead of hiding it forever', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    render(<Reveal>visible</Reveal>)
    expect(screen.getByText('visible')).toHaveAttribute('data-revealed', 'true')
  })
})
