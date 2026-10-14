import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RecommendationStatus } from '../api/types'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { PRESETS } from '../lib/presets'
import type { FormValues } from '../lib/validation'
import { makeCheckpoint, makeResponse, makeRoute, MISSING_CHECKPOINT } from '../test/fixtures'
import { AppHeader } from './AppHeader'
import { CheckpointsPage } from './CheckpointsPage'
import { CheckpointTable } from './CheckpointTable'
import { ForecastSlider, type OffsetSummary } from './ForecastSlider'
import { PlannerForm } from './PlannerForm'
import { RecommendationBanner } from './RecommendationBanner'
import { RiskBadge, RiskDot, RiskMilesBar } from './RiskBadge'
import { RouteCard } from './RouteCard'

vi.mock('../hooks/useMediaQuery', () => ({ useMediaQuery: vi.fn(() => true) }))
vi.mock('../lib/csv', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/csv')>()),
  downloadCsv: vi.fn(),
}))
import { downloadCsv } from '../lib/csv'

describe('risk labels', () => {
  it('shows level as text and a shape glyph, not colour alone', () => {
    render(
      <>
        <RiskBadge level="severe" />
        <RiskBadge level={null} />
        <RiskDot level="high" suffix=" risk" />
      </>,
    )
    expect(screen.getByText('Severe')).toBeInTheDocument()
    expect(screen.getByText('■')).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
    expect(screen.getByText('?')).toBeInTheDocument()
    expect(screen.getByText('High risk')).toBeInTheDocument()
    expect(screen.getByText('◆')).toBeInTheDocument()
  })

  it('describes risk miles including unknown for assistive tech', () => {
    render(<RiskMilesBar miles={{ low: 100, moderate: 0, high: 25, severe: 0, no_travel: 0, unknown: 50 }} />)
    expect(screen.getByRole('img', { name: /Unknown 50 mi/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /High 25 mi/ })).toBeInTheDocument()
  })
})

describe('RecommendationBanner', () => {
  const cases: [RecommendationStatus, string][] = [
    ['recommended', 'Route 1 is recommended'],
    ['recommended_incomplete_weather', 'Route 1 is recommended, but weather data is incomplete'],
    ['no_safe_route', 'No safe route for this departure'],
    ['insufficient_weather_data', 'Not enough weather data to recommend a route'],
  ]
  it.each(cases)('renders %s accurately and includes the backend explanation', (status, title) => {
    render(<RecommendationBanner data={makeResponse(status)} />)
    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.getByText(`Backend explanation for ${status}.`)).toBeInTheDocument()
  })

  it('names a route and its time trade-off only when the backend recommends one', () => {
    const { unmount } = render(<RecommendationBanner data={makeResponse('recommended')} />)
    expect(screen.getByText(/1,410 mi · 34 h 9 min/)).toBeInTheDocument()
    expect(screen.getByText('Fastest route')).toBeInTheDocument()
    unmount()
    for (const status of ['no_safe_route', 'insufficient_weather_data'] as const) {
      const view = render(<RecommendationBanner data={makeResponse(status)} />)
      expect(view.container.textContent).not.toMatch(/Route \d is recommended|Fastest route|vs fastest/)
      view.unmount()
    }
  })

  it('is honest when the recommended route is not the fastest', () => {
    const data = makeResponse('recommended')
    data.recommendation.recommended_route_id = 'route-2' // route-2 is 600 s slower in the fixture
    render(<RecommendationBanner data={data} />)
    expect(screen.getByRole('heading', { name: 'Route 2 is recommended' })).toBeInTheDocument()
    expect(screen.getByText('+10 min vs fastest')).toBeInTheDocument()
  })

  it('never calls missing weather safe', () => {
    render(<RecommendationBanner data={makeResponse('insufficient_weather_data')} />)
    expect(screen.getByText(/Missing weather is not safe weather/)).toBeInTheDocument()
  })
})

describe('RouteCard', () => {
  const card = (over: Partial<Parameters<typeof RouteCard>[0]> = {}) => (
    <RouteCard route={makeRoute(1)} selected={false} isFastest={false} onSelect={() => {}} {...over} />
  )

  it('is compact: big distance and drive time, one risk line, coverage', () => {
    render(card({ isFastest: true }))
    expect(screen.getByText('1,410')).toBeInTheDocument()
    expect(screen.getByText('33h 30m')).toBeInTheDocument()
    expect(screen.getByLabelText('Worst checkpoint risk')).toHaveTextContent('Moderate risk')
    expect(screen.getByText('100% coverage')).toBeInTheDocument()
    expect(screen.getByText(/Baseline route · Fastest/)).toBeInTheDocument()
    expect(screen.getByText('★ Recommended')).toBeInTheDocument()
  })

  it('keeps the detail one click away: arrival, average score, risk miles and the ranking explanation', () => {
    render(card())
    expect(screen.getByText('Risk details')).toBeInTheDocument()
    expect(screen.getByText('0.02 / 4')).toBeInTheDocument()
    expect(screen.getByText(/Ranked 1: test explanation/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Estimated miles by risk level/ })).toBeInTheDocument()
  })

  it('does not show a recommended badge for other routes, and explains ineligibility', () => {
    const route = makeRoute(2, {
      recommended: false,
      eligible: false,
      ineligible_reason: 'weather is known for only 23% of its miles (minimum 80%)',
      risk_summary: { ...makeRoute(2).risk_summary, weather_coverage_percent: 23, average_score: null, max_risk_level: null, miles: { low: 0, moderate: 0, high: 0, severe: 0, no_travel: 0, unknown: 1400 } },
    })
    render(card({ route }))
    expect(screen.queryByText('★ Recommended')).not.toBeInTheDocument()
    expect(screen.getByText('Not eligible')).toBeInTheDocument()
    expect(screen.getByText(/only 23% of its miles/)).toBeInTheDocument()
    expect(screen.getByText('No data')).toBeInTheDocument() // average score missing, not 0
    expect(screen.getByText('23% coverage')).toBeInTheDocument()
    expect(screen.getByLabelText('Worst checkpoint risk')).toHaveTextContent('Unknown risk')
  })

  it('selects the route from a keyboard-accessible button and reflects the selected state', async () => {
    const onSelect = vi.fn()
    const { rerender } = render(card({ route: makeRoute(2, { recommended: false }), onSelect }))
    await userEvent.click(screen.getByRole('button', { name: 'Show Route 2 on map' }))
    expect(onSelect).toHaveBeenCalledWith('route-2')
    expect(screen.getByRole('button', { name: 'Show Route 2 on map' })).toHaveTextContent('View route')
    rerender(card({ selected: true }))
    expect(screen.getByRole('button', { name: 'Showing Route 1 on map' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Showing Route 1 on map' })).toHaveTextContent('Viewing on map')
  })
})

describe('CheckpointTable', () => {
  const rows = [
    makeCheckpoint(0),
    MISSING_CHECKPOINT(1),
    makeCheckpoint(2, {
      weather_status: 'partial',
      weather_missing_reason: 'provider has no rain data for the hour of arrival',
      weather: { wind_speed_mph: 41, wind_gust_mph: 50, rain_in_per_hr: null, snow_in_per_hr: 0, wind_used_mph: 41 },
      risk: { combined: 'severe', wind: 'high', rain: null, snow: 'low', load_override: 'severe', reasons: [] },
    }),
  ]
  const table = (over: Partial<Parameters<typeof CheckpointTable>[0]> = {}) => (
    <CheckpointTable rows={rows} routeName="Route 1" windMetric="sustained" focusedIndex={null} onLocate={() => {}} {...over} />
  )

  it('renders missing weather as "No data" with the reason, never as zero', () => {
    render(table())
    const missingRow = screen.getAllByRole('row')[2]
    expect(within(missingRow).getAllByText('No data')).toHaveLength(4)
    expect(within(missingRow).getByText('Unavailable')).toBeInTheDocument()
    expect(within(missingRow).getByText(/beyond the forecast horizon/)).toBeInTheDocument()
    expect(within(missingRow).getAllByText('Unknown')).toHaveLength(4) // wind, rain, snow and combined
    expect(missingRow.textContent).not.toMatch(/\b0\.0+ (mph|in\/hr)/)
  })

  it('keeps partial observations and shows their gap, hazard levels and the load rule', () => {
    render(table())
    const row = screen.getAllByRole('row')[3]
    expect(within(row).getByText(/41\.0/)).toBeInTheDocument()
    expect(within(row).getByText('Partial')).toBeInTheDocument()
    expect(within(row).getByText(/no rain data/)).toBeInTheDocument()
    expect(within(row).getAllByText('Severe')).toHaveLength(2) // combined + load rule
    expect(within(row).getByText('High')).toBeInTheDocument() // wind hazard
    expect(within(row).getByText(/Load rule/)).toBeInTheDocument()
  })

  it('keeps Low quiet but available to screen readers, and shows no level for the non-basis wind column', () => {
    render(table())
    const first = screen.getAllByRole('row')[1]
    expect(within(first).getAllByText('Low').every((el) => el.className.includes('sr-only') || el.closest('td'))).toBe(true)
    expect(within(first).queryByText('Moderate')).not.toBeInTheDocument()
  })

  it('reports mile markers on click and marks which wind value drives the risk', async () => {
    const onLocate = vi.fn()
    const { rerender } = render(table({ onLocate }))
    await userEvent.click(screen.getByRole('button', { name: 'Locate mile 50 on map' }))
    expect(onLocate).toHaveBeenCalledWith(2) // mile 50 is checkpoint index 2
    expect(screen.getByRole('columnheader', { name: /Wind · used/ })).toBeInTheDocument()
    rerender(table({ windMetric: 'gust' }))
    expect(screen.getByRole('columnheader', { name: /Gusts · used/ })).toBeInTheDocument()
  })
})

describe('CheckpointsPage', () => {
  const data = () => {
    const d = makeResponse('recommended')
    d.routes[0] = { ...d.routes[0], checkpoints: [makeCheckpoint(0), MISSING_CHECKPOINT(1), makeCheckpoint(2)] }
    return d
  }
  const page = (over: Partial<Parameters<typeof CheckpointsPage>[0]> = {}) => (
    <CheckpointsPage data={data()} selectedId="route-1" onSelectRoute={() => {}} focusedIndex={null} onLocate={() => {}} onOpenPlanner={() => {}} {...over} />
  )

  beforeEach(() => {
    vi.mocked(useMediaQuery).mockReturnValue(true)
    vi.mocked(downloadCsv).mockClear()
  })

  it('without an assessment, points back to the planner instead of showing an empty table', async () => {
    const onOpenPlanner = vi.fn()
    render(page({ data: null, onOpenPlanner }))
    expect(screen.getByRole('heading', { name: 'No checkpoints yet' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Plan a trip/ }))
    expect(onOpenPlanner).toHaveBeenCalled()
  })

  it('shows the selected route, its sampled points and the departure context', () => {
    render(page())
    expect(screen.getByRole('heading', { name: 'Route 1 checkpoints' })).toBeInTheDocument()
    expect(screen.getByText(/3 sampled points · Estimated arrival and weather conditions/)).toBeInTheDocument()
    expect(screen.getByText(/Load 42,000 lb · every 25 mi · wind risk uses sustained wind/)).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(4)
  })

  it('switches route and filters to checkpoints above Low or with missing data', async () => {
    const onSelectRoute = vi.fn()
    render(page({ onSelectRoute }))
    await userEvent.click(screen.getByRole('radio', { name: 'Route 2' }))
    expect(onSelectRoute).toHaveBeenCalledWith('route-2')

    await userEvent.click(screen.getByRole('checkbox', { name: /Above low risk only \(1\)/ }))
    expect(screen.getAllByRole('row')).toHaveLength(2) // header + the one checkpoint with missing weather
  })

  it('locates a checkpoint on the map via the planner', async () => {
    const onLocate = vi.fn()
    render(page({ onLocate }))
    await userEvent.click(screen.getByRole('button', { name: 'Locate mile 50 on map' }))
    expect(onLocate).toHaveBeenCalledWith('route-1', 2)
  })

  it('exports the route as CSV with missing weather left blank, not zero', async () => {
    render(page())
    await userEvent.click(screen.getByRole('button', { name: /Export/ }))
    expect(downloadCsv).toHaveBeenCalledTimes(1)
    const [filename, csv] = vi.mocked(downloadCsv).mock.calls[0]
    expect(filename).toBe('route-1-checkpoints-2026-10-14.csv')
    const lines = csv.trim().split('\r\n')
    expect(lines[0]).toMatch(/^route,mile,eta_utc,latitude,longitude,wind_mph,gust_mph,rain_in_per_hr,snow_in_per_hr/)
    expect(lines).toHaveLength(4)
    const missing = lines[2].split(',')
    expect(missing.slice(5, 14)).toEqual(['', '', '', '', '', '', '', '', '']) // all weather and risk cells empty
    expect(lines[2]).toMatch(/unavailable/)
    expect(lines[1]).toMatch(/,8\.2,11\.6,0\.02,0,8\.2,low,low,low,low,,complete,$/)
  })

  it('uses stacked cards on phones instead of a wide table', () => {
    vi.mocked(useMediaQuery).mockReturnValue(false)
    render(page())
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Locate mile 25 on map' })).toHaveTextContent('Mile 25')
    expect(screen.getByText(/Weather unavailable:/)).toBeInTheDocument()
    expect(screen.getAllByText('No data').length).toBeGreaterThanOrEqual(4)
  })
})

describe('AppHeader', () => {
  it('shows the two pages, marks the current one, and navigates', async () => {
    const onNavigate = vi.fn()
    render(<AppHeader page="planner" onNavigate={onNavigate} />)
    const nav = within(screen.getByRole('navigation', { name: 'Pages' }))
    expect(nav.getByRole('link', { name: 'Route planner' })).toHaveAttribute('aria-current', 'page')
    expect(nav.getByRole('link', { name: 'Checkpoints' })).not.toHaveAttribute('aria-current')
    await userEvent.click(nav.getByRole('link', { name: 'Checkpoints' }))
    expect(onNavigate).toHaveBeenCalledWith('checkpoints')
  })
})

describe('PlannerForm', () => {
  const values: FormValues = { originLat: '', originLon: '', destLat: '', destLon: '', departureLocal: '2026-10-14T08:00', loadLb: '42000', interval: 25 }
  const form = (over: Partial<Parameters<typeof PlannerForm>[0]> = {}) => (
    <PlannerForm
      values={values}
      errors={{}}
      submitting={false}
      timeZone="UTC (UTC+00:00)"
      onChange={() => {}}
      onPreset={() => {}}
      onSubmit={() => {}}
      {...over}
    />
  )

  it('fills the trip from the Quick trip dropdown', async () => {
    const onPreset = vi.fn()
    render(form({ onPreset }))
    await userEvent.selectOptions(screen.getByLabelText('Quick trip'), 'chicago-atlanta')
    expect(onPreset).toHaveBeenCalledWith(PRESETS.find((p) => p.id === 'chicago-atlanta'))
  })

  it('names recognised places and reflects the matching quick trip', () => {
    const chicago = PRESETS[1].values
    render(form({ values: { ...values, ...chicago } }))
    expect(screen.getByLabelText('Quick trip')).toHaveValue('chicago-atlanta')
    expect(screen.getByText('Chicago')).toBeInTheDocument()
    expect(screen.getByText('Atlanta')).toBeInTheDocument()
  })

  it('labels unrecognised coordinates as custom rather than inventing a place name', () => {
    render(form({ values: { ...values, originLat: '10', originLon: '10', destLat: '11', destLon: '11' } }))
    expect(screen.getByLabelText('Quick trip')).toHaveValue('custom')
    expect(screen.getByText('Custom origin')).toBeInTheDocument()
    expect(screen.getByText('Custom destination')).toBeInTheDocument()
  })

  it('keeps checkpoint spacing behind a collapsed Advanced settings control', async () => {
    const onChange = vi.fn()
    const { container } = render(form({ onChange }))
    const details = container.querySelector('details')!
    expect(details).not.toHaveAttribute('open')
    expect(within(details).getByText('Advanced settings')).toBeInTheDocument()
    fireEvent.click(within(details).getByLabelText('50 mi'))
    expect(onChange).toHaveBeenCalledWith('interval', 50)
  })

  it('opens Advanced settings when the spacing has an error', () => {
    const { container } = render(form({ errors: { interval: 'Choose 10, 25 or 50 miles.' } }))
    expect(container.querySelector('details')).toHaveAttribute('open')
    expect(screen.getByText('Choose 10, 25 or 50 miles.')).toBeInTheDocument()
  })

  it('shows the load unit and disables the button while assessing', () => {
    const { rerender } = render(form())
    expect(screen.getByText('lb')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Assess routes' })).toBeEnabled()
    rerender(form({ submitting: true }))
    expect(screen.getByRole('button', { name: /Assessing routes/ })).toBeDisabled()
  })
})

describe('ForecastSlider (Explore departure times)', () => {
  const base = '2026-10-14T08:00:00-07:00'
  const summaries: OffsetSummary[] = [
    { offsetHours: 0, state: 'ok', status: 'recommended', recommendedRouteId: 'route-1', ageMinutes: 2 },
    { offsetHours: 24, state: 'ok', status: 'no_safe_route', recommendedRouteId: null, ageMinutes: 2 },
    { offsetHours: 36, state: 'stale', status: 'recommended', recommendedRouteId: 'route-2', ageMinutes: 45 },
    { offsetHours: 12, state: 'error', message: 'This departure could not be assessed.' },
  ]
  const props = (over: Partial<Parameters<typeof ForecastSlider>[0]> = {}) => ({
    baseDeparture: base,
    shownOffset: 0,
    loading: false,
    summaries,
    lastBatch: null,
    onCommit: () => {},
    ...over,
  })

  it('shows an already-assessed departure immediately, without waiting for the slider to settle', async () => {
    const onCommit = vi.fn()
    render(<ForecastSlider {...props({ onCommit })} />)
    await userEvent.click(screen.getByRole('button', { name: /^\+24 h/ }))
    expect(onCommit).toHaveBeenCalledWith(24)
  })

  it('waits for the slider to settle before requesting an unassessed departure', async () => {
    const onCommit = vi.fn()
    render(<ForecastSlider {...props({ onCommit })} />)
    const slider = screen.getByRole('slider')
    fireEvent.change(slider, { target: { value: '5' } })
    fireEvent.change(slider, { target: { value: '7' } })
    expect(onCommit).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('Not assessed yet')
    await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(1), { timeout: 2000 })
    expect(onCommit).toHaveBeenCalledWith(7)
  })

  it('does not present stale or failed departures as assessed', () => {
    const { rerender } = render(<ForecastSlider {...props({ shownOffset: 36 })} />)
    fireEvent.change(screen.getByRole('slider'), { target: { value: '36' } })
    expect(screen.getByRole('status')).toHaveTextContent(/too old to show as current/)
    fireEvent.change(screen.getByRole('slider'), { target: { value: '12' } })
    expect(screen.getByRole('status')).toHaveTextContent(/failed: This departure could not be assessed/)
    rerender(<ForecastSlider {...props({ loading: true })} />)
    expect(screen.getByRole('status')).toHaveTextContent('Assessing this departure')
  })

  it('shows every departure as a tab with its outcome, and marks which were actually assessed', () => {
    render(<ForecastSlider {...props()} />)
    expect(screen.getByTitle('+24 h: assessed')).toBeInTheDocument()
    expect(screen.getByTitle('+36 h: assessed, now stale')).toBeInTheDocument()
    expect(screen.getByTitle('+12 h: failed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^\+12 h\s*Failed - retry/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^\+36 h\s*Route 2 · stale, refresh/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^\+24 h\s*No safe route/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^\+6 h\s*Not assessed/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^As entered\s*Route 1/ })).toHaveAttribute('aria-current', 'true')
  })

  it('retries a failed departure from its tab', async () => {
    const onCommit = vi.fn()
    render(<ForecastSlider {...props({ onCommit })} />)
    await userEvent.click(screen.getByRole('button', { name: /^\+12 h\s*Failed - retry/ }))
    expect(onCommit).toHaveBeenCalledWith(12)
  })

  it('reports how the last request reused routes, and that weather is never estimated locally', () => {
    render(<ForecastSlider {...props({ lastBatch: { departures: 9, routeCache: 'miss', routingRequests: 4, weatherRequests: 4 } })} />)
    expect(screen.getByText(/Last request: 9 departures, routes planned once \(4 routing and 4 weather provider requests\)/)).toBeInTheDocument()
    expect(screen.getByText(/never estimated in your browser/)).toBeInTheDocument()
  })
})

describe('AppHeader: landing and app variants', () => {
  it('links the app pages to their own routes, and the brand to the landing page', async () => {
    const onNavigate = vi.fn()
    render(<AppHeader page="planner" onNavigate={onNavigate} />)
    const nav = within(screen.getByRole('navigation', { name: 'Pages' }))
    expect(nav.getByRole('link', { name: 'Route planner' })).toHaveAttribute('href', '#/planner')
    expect(nav.getByRole('link', { name: 'Checkpoints' })).toHaveAttribute('href', '#/checkpoints')
    await userEvent.click(screen.getByRole('link', { name: /Weather-Aware Routing, home/ }))
    expect(onNavigate).toHaveBeenCalledWith('home')
  })

  it('on the landing page shows section links and one primary action instead of the app navigation', async () => {
    const onNavigate = vi.fn()
    render(<AppHeader page="home" onNavigate={onNavigate} />)
    expect(screen.queryByRole('navigation', { name: 'Pages' })).not.toBeInTheDocument()
    const sections = within(screen.getByRole('navigation', { name: 'Sections' }))
    expect(sections.getByRole('link', { name: 'How it works' })).toHaveAttribute('href', '#how-it-works')
    expect(sections.getByRole('link', { name: 'Principles' })).toHaveAttribute('href', '#principles')
    expect(sections.getByRole('link', { name: 'Risk rules' })).toHaveAttribute('href', '#risk-rules')
    await userEvent.click(screen.getByRole('link', { name: /Open planner/ }))
    expect(onNavigate).toHaveBeenCalledWith('planner')
  })
})
