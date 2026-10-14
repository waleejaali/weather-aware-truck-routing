import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { assessBatch } from './api/batch'
import { ApiError } from './api/routes'
import type { BatchRequest, RecommendationStatus } from './api/types'
import { PREFETCH_OFFSETS, STALE_AFTER_MS } from './hooks/useAssessment'
import { makeBatch } from './test/fixtures'

// jsdom cannot render Leaflet; the map's props are exposed through a stub instead.
vi.mock('./components/MapView', () => ({
  MapView: (props: { selectedId: string | null; recommendedId: string | null; routes: unknown[]; loading: boolean }) => (
    <div
      data-testid="map"
      data-selected={props.selectedId ?? 'none'}
      data-recommended={props.recommendedId ?? 'none'}
      data-routes={props.routes.length}
      data-loading={String(props.loading)}
    />
  ),
}))
vi.mock('./api/batch', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api/batch')>()),
  assessBatch: vi.fn(),
}))

const batch = vi.mocked(assessBatch)
type StatusFor = (index: number) => RecommendationStatus | 'error'

/** Answer every batch request with a well-formed response whose statuses come from `statusFor`. */
function serve(statusFor: StatusFor = () => 'recommended') {
  batch.mockImplementation(async (request: BatchRequest) => makeBatch(request, statusFor))
}

async function fillAndSubmit() {
  await userEvent.click(screen.getByRole('button', { name: 'Los Angeles → Dallas' }))
  await userEvent.click(screen.getByRole('button', { name: 'Assess Routes' }))
}

const HOUR = 3_600_000
const at = (request: BatchRequest, i: number) => new Date(request.departure_datetimes[i]).getTime()

beforeEach(() => {
  batch.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('App: planning a trip', () => {
  it('starts with an empty state and an enabled Assess button', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Plan a weather-aware route' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Assess Routes' })).toBeEnabled()
    expect(screen.getByTestId('map')).toHaveAttribute('data-routes', '0')
  })

  it('validates on the client and shows inline errors without calling the API or alerting', async () => {
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {})
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Assess Routes' }))
    expect(batch).not.toHaveBeenCalled()
    expect(alert).not.toHaveBeenCalled()
    expect(screen.getAllByText(/Enter a (latitude|longitude)/).length).toBe(4)
    expect(screen.getByLabelText('Latitude', { selector: '#origin-lat' })).toHaveAttribute('aria-invalid', 'true')
    await waitFor(() => expect(document.getElementById('origin-lat')).toHaveFocus())
  })

  it('sends ONE batch request with the exact schema and a bounded set of departures, then renders all routes', async () => {
    serve()
    render(<App />)
    await fillAndSubmit()
    await waitFor(() => expect(batch).toHaveBeenCalledTimes(1))

    const request = batch.mock.calls[0][0]
    expect(Object.keys(request).sort()).toEqual(['checkpoint_interval_miles', 'departure_datetimes', 'destination', 'load_lb', 'origin'])
    expect(request.origin).toEqual({ latitude: 34.0522, longitude: -118.2437 })
    expect(request.destination).toEqual({ latitude: 32.7767, longitude: -96.797 })
    expect(request.load_lb).toBe(42000)
    expect(request.checkpoint_interval_miles).toBe(25)
    expect(request.departure_datetimes).toHaveLength(PREFETCH_OFFSETS.length)
    expect(request.departure_datetimes.length).toBeLessThanOrEqual(12) // the backend's batch limit
    expect(request.departure_datetimes[0]).toMatch(/^\d{4}-\d{2}-\d{2}T08:00:00[+-]\d{2}:\d{2}$/)
    PREFETCH_OFFSETS.forEach((hours, i) => expect(at(request, i) - at(request, 0)).toBe(hours * HOUR))

    expect(await screen.findByRole('heading', { name: '3 candidate routes' })).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(3)
    expect(screen.getByRole('heading', { name: 'Recommended route' })).toBeInTheDocument()
    expect(screen.getByTestId('map')).toHaveAttribute('data-recommended', 'route-1')
    expect(screen.getByTestId('map')).toHaveAttribute('data-selected', 'route-1')
    expect(screen.getAllByText('★ Recommended')).toHaveLength(1)
  })

  it('selects another route for the map and checkpoint table', async () => {
    serve()
    render(<App />)
    await fillAndSubmit()
    await screen.findByRole('heading', { name: '3 candidate routes' })
    await userEvent.click(screen.getByRole('button', { name: 'Show Route 2 on map' }))
    expect(screen.getByTestId('map')).toHaveAttribute('data-selected', 'route-2')
    expect(screen.getByRole('region', { name: 'Route 2 checkpoints' })).toBeInTheDocument()
    expect(screen.getByTestId('map')).toHaveAttribute('data-recommended', 'route-1')
  })

  it.each<[RecommendationStatus, string]>([
    ['no_safe_route', 'No safe route for this departure'],
    ['insufficient_weather_data', 'Not enough weather data to recommend a route'],
  ])('does not highlight any recommended route for %s', async (status, title) => {
    serve(() => status)
    render(<App />)
    await fillAndSubmit()
    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.queryByText('★ Recommended')).not.toBeInTheDocument()
    expect(screen.getByTestId('map')).toHaveAttribute('data-recommended', 'none')
    expect(screen.getByText('No route is recommended, so none is highlighted.')).toBeInTheDocument()
  })

  it('puts backend validation errors on the matching form fields', async () => {
    batch.mockRejectedValue(new ApiError('validation', 'The request is invalid.', { status: 400, fields: { load_lb: ['Load must not exceed 150,000 lb.'] } }))
    render(<App />)
    await fillAndSubmit()
    expect(await screen.findByText('Load must not exceed 150,000 lb.')).toBeInTheDocument()
    expect(screen.getByLabelText('Load weight (lb)')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('disables the button while assessing and shows the map as loading', async () => {
    let finish: () => void = () => {}
    batch.mockImplementation(
      (request) =>
        new Promise((resolve) => {
          finish = () => resolve(makeBatch(request))
        }),
    )
    render(<App />)
    await fillAndSubmit()
    const button = await screen.findByRole('button', { name: /Assessing routes/ })
    expect(button).toBeDisabled()
    expect(screen.getByTestId('map')).toHaveAttribute('data-loading', 'true')
    finish()
    expect(await screen.findByRole('button', { name: 'Assess Routes' })).toBeEnabled()
  })

  it('shows the attribution, method limits and how many provider requests the batch needed', async () => {
    serve()
    render(<App />)
    await fillAndSubmit()
    await screen.findByRole('heading', { name: '3 candidate routes' })
    expect(screen.getByRole('link', { name: 'Weather data by Open-Meteo.com' })).toHaveAttribute('href', 'https://open-meteo.com/')
    expect(screen.getByText(/How this was calculated · 25-mile checkpoints · sustained wind · 80% minimum coverage/)).toBeInTheDocument()
    expect(screen.getByText(/Last request: 9 departures, routes planned once \(4 routing and 4 weather provider requests\)/)).toBeInTheDocument()
  })
})

describe('App: provider failures', () => {
  it('shows a retryable error for a failed batch, no fake results, and retries the same full request', async () => {
    batch.mockRejectedValueOnce(new ApiError('provider', 'The weather service returned an error.', { status: 502 }))
    serve()
    render(<App />)
    await fillAndSubmit()

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('A routing or weather service is unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /candidate route/ })).not.toBeInTheDocument()

    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: '3 candidate routes' })).toBeInTheDocument()
    expect(batch).toHaveBeenCalledTimes(2)
    expect(batch.mock.calls[1][0]).toEqual(batch.mock.calls[0][0]) // same departures, same trip
  })
})

describe('App: forecast slider with the batch endpoint', () => {
  const noSafeAt24: StatusFor = (i) => (PREFETCH_OFFSETS[i] === 24 ? 'no_safe_route' : 'recommended')

  async function submitted(statusFor: StatusFor = noSafeAt24) {
    serve(statusFor)
    render(<App />)
    await fillAndSubmit()
    await screen.findByRole('heading', { name: '3 candidate routes' })
  }

  it('shows every prefetched departure without another API call', async () => {
    await submitted()
    await userEvent.click(screen.getByRole('button', { name: '+24 h' }))
    expect(await screen.findByRole('heading', { name: 'No safe route for this departure' })).toBeInTheDocument()
    expect(screen.getByTestId('map')).toHaveAttribute('data-recommended', 'none')
    await userEvent.click(screen.getByRole('button', { name: '+6 h' }))
    expect(await screen.findByRole('heading', { name: 'Recommended route' })).toBeInTheDocument()
    expect(batch).toHaveBeenCalledTimes(1) // 9 departures, one request; moving the slider costs nothing
  })

  it('lists which departures were really assessed, with their own statuses', async () => {
    await submitted()
    expect(screen.getByRole('button', { name: /\+24 h\s*No safe route/ })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Recommended · Route 1/ }).length).toBe(PREFETCH_OFFSETS.length - 1)
    expect(screen.getByTitle('+24 h: assessed')).toBeInTheDocument()
    expect(screen.queryByTitle('+7 h: assessed')).not.toBeInTheDocument() // never assessed, so not marked
  })

  it('requests a single new departure for an offset that was not prefetched', async () => {
    await submitted()
    fireEvent.change(screen.getByRole('slider'), { target: { value: '7' } })
    expect(screen.getByText(/Not assessed yet/)).toBeInTheDocument()
    await waitFor(() => expect(batch).toHaveBeenCalledTimes(2), { timeout: 3000 })

    const first = batch.mock.calls[0][0]
    const second = batch.mock.calls[1][0]
    expect(second.departure_datetimes).toHaveLength(1)
    expect(at(second, 0) - at(first, 0)).toBe(7 * HOUR)
    expect({ ...second, departure_datetimes: [] }).toEqual({ ...first, departure_datetimes: [] }) // same trip, only the time differs
    expect(await screen.findByTitle('+7 h: assessed')).toBeInTheDocument()
  })

  it('does not show an old assessment as current: it is re-requested', async () => {
    await submitted()
    const real = Date.now()
    vi.spyOn(Date, 'now').mockReturnValue(real + STALE_AFTER_MS + 60_000)
    await userEvent.click(screen.getByRole('button', { name: '+6 h' }))
    await waitFor(() => expect(batch).toHaveBeenCalledTimes(2))
    const [first, refreshed] = [batch.mock.calls[0][0], batch.mock.calls[1][0]]
    expect(refreshed.departure_datetimes).toHaveLength(1)
    expect(at(refreshed, 0) - at(first, 0)).toBe(6 * HOUR)
  })

  it('keeps a failed departure visible, marked as failed, and retries only that departure', async () => {
    await submitted((i) => (PREFETCH_OFFSETS[i] === 12 ? 'error' : 'recommended'))
    expect(screen.getByTitle('+12 h: failed')).toBeInTheDocument()
    const chip = screen.getByRole('button', { name: /\+12 h\s*Failed - retry/ })

    serve() // the retry succeeds
    await userEvent.click(chip)
    await waitFor(() => expect(batch).toHaveBeenCalledTimes(2))
    expect(batch.mock.calls[1][0].departure_datetimes).toHaveLength(1)
    expect(await screen.findByTitle('+12 h: assessed')).toBeInTheDocument()
    expect(screen.queryByTitle('+12 h: failed')).not.toBeInTheDocument()
  })

  it('shows an error, not stale weather, when a requested departure fails', async () => {
    await submitted()
    batch.mockImplementation(async (request) => makeBatch(request, () => 'error'))
    fireEvent.change(screen.getByRole('slider'), { target: { value: '7' } })
    const alert = await screen.findByRole('alert', {}, { timeout: 3000 })
    expect(within(alert).getByText('This departure could not be assessed.')).toBeInTheDocument()
    expect(screen.getByTitle('+7 h: failed')).toBeInTheDocument()
    expect(screen.queryByTitle('+7 h: assessed')).not.toBeInTheDocument()
  })

  it('offers a refresh when the displayed assessment gets old, and refreshing requests that departure again', async () => {
    serve()
    // Fake only the interval timer so the clock-driven "now" can be advanced without freezing user events.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    render(<App />)
    await fillAndSubmit()
    await screen.findByRole('heading', { name: '3 candidate routes' })
    expect(screen.queryByText(/more than 30 minutes old/)).not.toBeInTheDocument()

    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + STALE_AFTER_MS + 60_000)
    act(() => {
      vi.advanceTimersByTime(31_000)
    })
    expect(screen.getByText(/more than 30 minutes old/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /As entered\s*Recommended · Route 1 · stale, refresh/ })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(batch).toHaveBeenCalledTimes(2))
    const [first, refreshed] = [batch.mock.calls[0][0], batch.mock.calls[1][0]]
    expect(refreshed.departure_datetimes).toEqual([first.departure_datetimes[0]]) // the same departure, requested again
    await waitFor(() => expect(screen.queryByText(/more than 30 minutes old/)).not.toBeInTheDocument())
  })
})
