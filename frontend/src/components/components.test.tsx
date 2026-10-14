import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RecommendationStatus } from '../api/types'
import { makeCheckpoint, makeResponse, makeRoute, MISSING_CHECKPOINT } from '../test/fixtures'
import { CheckpointTable } from './CheckpointTable'
import { ForecastSlider, type OffsetSummary } from './ForecastSlider'
import { RecommendationBanner } from './RecommendationBanner'
import { RiskBadge, RiskMilesBar } from './RiskBadge'
import { RouteCard } from './RouteCard'

describe('RiskBadge', () => {
  it('shows level as text and a shape glyph, not colour alone', () => {
    render(
      <>
        <RiskBadge level="severe" />
        <RiskBadge level={null} />
      </>,
    )
    expect(screen.getByText('Severe')).toBeInTheDocument()
    expect(screen.getByText('■')).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('describes risk miles including unknown for assistive tech', () => {
    render(<RiskMilesBar miles={{ low: 100, moderate: 0, high: 25, severe: 0, no_travel: 0, unknown: 50 }} />)
    expect(screen.getByRole('img', { name: /Unknown 50 mi/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /High 25 mi/ })).toBeInTheDocument()
  })
})

describe('RecommendationBanner statuses', () => {
  const cases: [RecommendationStatus, RegExp][] = [
    ['recommended', /^Recommended route$/],
    ['recommended_incomplete_weather', /Recommended, but weather data is incomplete/],
    ['no_safe_route', /No safe route for this departure/],
    ['insufficient_weather_data', /Not enough weather data to recommend a route/],
  ]
  it.each(cases)('renders %s accurately and includes the backend explanation', (status, title) => {
    const data = makeResponse(status)
    render(<RecommendationBanner data={data} />)
    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.getByText(`Backend explanation for ${status}.`)).toBeInTheDocument()
  })

  it('names a recommended route only when the backend recommends one', () => {
    const { unmount } = render(<RecommendationBanner data={makeResponse('recommended')} />)
    expect(screen.getByText(/Route 1: 1,410 mi/)).toBeInTheDocument()
    unmount()
    for (const status of ['no_safe_route', 'insufficient_weather_data'] as const) {
      const view = render(<RecommendationBanner data={makeResponse(status)} />)
      expect(view.container.textContent).not.toMatch(/Route 1: /)
      view.unmount()
    }
  })

  it('never calls missing weather safe', () => {
    render(<RecommendationBanner data={makeResponse('insufficient_weather_data')} />)
    expect(screen.getByText(/Missing weather is not safe weather/)).toBeInTheDocument()
  })
})

describe('RouteCard', () => {
  it('marks only the recommended route and shows the ranking explanation', () => {
    const route = makeRoute(1)
    render(<RouteCard route={route} selected={false} onSelect={() => {}} />)
    expect(screen.getByText(/Recommended/)).toBeInTheDocument()
    expect(screen.getByText(/Ranked 1: test explanation/)).toBeInTheDocument()
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('0.02 / 4')).toBeInTheDocument()
  })

  it('does not show a recommended badge for other routes, and explains ineligibility', () => {
    const route = makeRoute(2, {
      recommended: false,
      eligible: false,
      ineligible_reason: 'weather is known for only 23% of its miles (minimum 80%)',
      risk_summary: { ...makeRoute(2).risk_summary, weather_coverage_percent: 23, average_score: null, max_risk_level: null, miles: { low: 0, moderate: 0, high: 0, severe: 0, no_travel: 0, unknown: 1400 } },
    })
    render(<RouteCard route={route} selected={false} onSelect={() => {}} />)
    expect(screen.queryByText(/★ Recommended/)).not.toBeInTheDocument()
    expect(screen.getByText('Not eligible')).toBeInTheDocument()
    expect(screen.getByText(/only 23% of its miles/)).toBeInTheDocument()
    expect(screen.getByText('No data')).toBeInTheDocument() // average score is missing, not 0
    expect(screen.getByText('23%')).toBeInTheDocument()
  })

  it('selects the route from the keyboard-accessible button', async () => {
    const onSelect = vi.fn()
    render(<RouteCard route={makeRoute(2, { recommended: false })} selected={false} onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: 'Show Route 2 on map' }))
    expect(onSelect).toHaveBeenCalledWith('route-2')
  })

  it('reflects the selected state', () => {
    render(<RouteCard route={makeRoute(1)} selected onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: 'Showing Route 1 on map' })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('CheckpointTable', () => {
  const route = makeRoute(1, {
    checkpoints: [
      makeCheckpoint(0),
      MISSING_CHECKPOINT(1),
      makeCheckpoint(2, {
        weather_status: 'partial',
        weather_missing_reason: 'provider has no rain data for the hour of arrival',
        weather: { wind_speed_mph: 41, wind_gust_mph: 50, rain_in_per_hr: null, snow_in_per_hr: 0, wind_used_mph: 41 },
        risk: { combined: 'severe', wind: 'high', rain: null, snow: 'low', load_override: 'severe', reasons: [] },
      }),
    ],
  })

  it('renders missing weather as "No data" with the reason, never as zero', () => {
    render(<CheckpointTable route={route} windMetric="sustained" focusedIndex={null} onFocus={() => {}} />)
    const rows = screen.getAllByRole('row')
    const missingRow = rows[2]
    expect(within(missingRow).getAllByText('No data')).toHaveLength(4)
    expect(within(missingRow).getByText('Unavailable')).toBeInTheDocument()
    expect(within(missingRow).getByText(/beyond the forecast horizon/)).toBeInTheDocument()
    expect(within(missingRow).getAllByText('Unknown')).toHaveLength(4) // wind, rain, snow and combined are all unknown
    expect(missingRow.textContent).not.toMatch(/\b0\.0+ (mph|in\/hr)/)
  })

  it('keeps partial observations and shows their gap, hazard levels and the load rule', () => {
    render(<CheckpointTable route={route} windMetric="sustained" focusedIndex={null} onFocus={() => {}} />)
    const row = screen.getAllByRole('row')[3]
    expect(within(row).getByText(/41\.0/)).toBeInTheDocument()
    expect(within(row).getByText('Partial')).toBeInTheDocument()
    expect(within(row).getByText(/no rain data/)).toBeInTheDocument()
    expect(within(row).getAllByText('Severe').length).toBeGreaterThanOrEqual(2) // combined + load rule
    expect(within(row).getByText(/Load rule/)).toBeInTheDocument()
  })

  it('filters to checkpoints above Low or with missing data, and reports mile markers on click', async () => {
    const onFocus = vi.fn()
    render(<CheckpointTable route={route} windMetric="sustained" focusedIndex={null} onFocus={onFocus} />)
    expect(screen.getAllByRole('row')).toHaveLength(4) // header + 3
    await userEvent.click(screen.getByRole('checkbox', { name: /Only above Low or missing data \(2\)/ }))
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2
    await userEvent.click(screen.getByRole('button', { name: 'Locate mile 50 on map' }))
    expect(onFocus).toHaveBeenCalledWith(2) // mile 50 is checkpoint index 2
  })

  it('marks which wind value drives the risk', () => {
    const { rerender } = render(<CheckpointTable route={route} windMetric="sustained" focusedIndex={null} onFocus={() => {}} />)
    expect(screen.getByRole('columnheader', { name: /Wind ✓ used/ })).toBeInTheDocument()
    rerender(<CheckpointTable route={route} windMetric="gust" focusedIndex={null} onFocus={() => {}} />)
    expect(screen.getByRole('columnheader', { name: /Gusts ✓ used/ })).toBeInTheDocument()
  })
})

describe('ForecastSlider', () => {
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
    await userEvent.click(screen.getByRole('button', { name: '+24 h' }))
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

  it('marks which offsets were actually assessed, stale or failed, and labels the chips', () => {
    render(<ForecastSlider {...props()} />)
    expect(screen.getByTitle('+24 h: assessed')).toBeInTheDocument()
    expect(screen.getByTitle('+36 h: assessed, now stale')).toBeInTheDocument()
    expect(screen.getByTitle('+12 h: failed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\+12 h\s*Failed - retry/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\+36 h\s*Recommended · Route 2 · stale, refresh/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\+24 h\s*No safe route/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /As entered\s*Recommended · Route 1/ })).toHaveAttribute('aria-current', 'true')
  })

  it('retries a failed departure from its chip', async () => {
    const onCommit = vi.fn()
    render(<ForecastSlider {...props({ onCommit })} />)
    await userEvent.click(screen.getByRole('button', { name: /\+12 h\s*Failed - retry/ }))
    expect(onCommit).toHaveBeenCalledWith(12)
  })

  it('reports how the last request reused routes, and that weather is never estimated locally', () => {
    render(<ForecastSlider {...props({ lastBatch: { departures: 9, routeCache: 'miss', routingRequests: 4, weatherRequests: 4 } })} />)
    expect(screen.getByText(/Last request: 9 departures, routes planned once \(4 routing and 4 weather provider requests\)/)).toBeInTheDocument()
    expect(screen.getByText(/never estimated in your browser/)).toBeInTheDocument()
  })
})
