import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { ColorBy } from '../api/types'
import { riskMeta } from '../lib/risk'
import { makeCheckpoint, makeRoute } from '../test/fixtures'
import { MapView } from './MapView'

// jsdom cannot run Leaflet, so react-leaflet is replaced by elements that expose exactly what MapView hands to it.
const fitBounds = vi.fn()
vi.mock('react-leaflet', () => {
  const json = (value: unknown) => JSON.stringify(value)
  return {
    MapContainer: ({ children }: { children?: ReactNode }) => <div data-testid="map">{children}</div>,
    TileLayer: () => null,
    Tooltip: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
    Popup: ({ children }: { children?: ReactNode }) => <div data-testid="popup">{children}</div>,
    useMap: () => ({ fitBounds, panTo: vi.fn() }),
    Polyline: ({ positions, pathOptions, interactive }: { positions: unknown; pathOptions: { color: string; dashArray?: string }; interactive?: boolean }) => (
      <div data-testid="polyline" data-positions={json(positions)} data-color={pathOptions.color} data-dash={pathOptions.dashArray ?? ''} data-interactive={String(interactive ?? true)} />
    ),
    CircleMarker: ({ center, pathOptions, children }: { center: unknown; pathOptions: { fillColor: string }; children?: ReactNode }) => (
      <div data-testid="marker" data-center={json(center)} data-fill={pathOptions.fillColor}>
        {children}
      </div>
    ),
  }
})

const noop = () => {}
function renderMap(over: Partial<Parameters<typeof MapView>[0]> = {}) {
  const routes = [makeRoute(1), makeRoute(2, { geometry: { type: 'LineString', coordinates: [[-118.2, 34.0], [-100.5, 36.1], [-96.8, 32.8]] } })]
  return render(
    <MapView
      routes={routes}
      selectedId="route-1"
      recommendedId="route-1"
      colorBy="combined"
      origin={[34.0522, -118.2437]}
      destination={[32.7767, -96.797]}
      focus={null}
      fitKey="trip-1"
      loading={false}
      onSelectRoute={noop}
      onCheckpointClick={noop}
      {...over}
    />,
  )
}

const polylines = (c: HTMLElement) => [...c.querySelectorAll('[data-testid="polyline"]')] as HTMLElement[]
const markers = (c: HTMLElement) => [...c.querySelectorAll('[data-testid="marker"]')] as HTMLElement[]
const positionsOf = (el: HTMLElement) => JSON.parse(el.dataset.positions!) as [number, number][]

describe('MapView geometry', () => {
  it('draws backend GeoJSON [lon, lat] as Leaflet [lat, lon] for every candidate route', () => {
    const { container } = renderMap()
    const drawn = polylines(container).map(positionsOf)
    // route-2 is an unselected route, drawn as one polyline using its full geometry
    expect(drawn).toContainEqual([[34.0, -118.2], [36.1, -100.5], [32.8, -96.8]])
    // the selected route's outline spans its whole geometry, latitude first
    expect(drawn).toContainEqual([[34.0522, -118.2437], [33.5, -110], [32.7767, -96.797]])
    for (const path of drawn) {
      for (const [lat, lon] of path) {
        expect(lat).toBeGreaterThan(30)
        expect(lat).toBeLessThan(40)
        expect(lon).toBeLessThan(-90) // continental US longitudes are the large negative numbers
      }
    }
  })

  it('places each checkpoint marker at the backend latitude and longitude, in that order', () => {
    const route = makeRoute(1, { checkpoints: [makeCheckpoint(0, { latitude: 34.05, longitude: -118.24 }), makeCheckpoint(1, { latitude: 33.1, longitude: -105.5 })] })
    const { container } = renderMap({ routes: [route] })
    const centers = markers(container).map((m) => JSON.parse(m.dataset.center!))
    expect(centers).toContainEqual([34.05, -118.24])
    expect(centers).toContainEqual([33.1, -105.5])
    expect(centers).toContainEqual([34.0522, -118.2437]) // the origin pin
    expect(centers).toContainEqual([32.7767, -96.797]) // the destination pin
  })

  it('fits the map to all route geometry once per trip, not on every re-render', () => {
    fitBounds.mockClear()
    const { rerender } = renderMap({ fitKey: 'trip-1' })
    expect(fitBounds).toHaveBeenCalledTimes(1)
    const [[south, west], [north, east]] = fitBounds.mock.calls[0][0]
    expect([south, north]).toEqual([32.7767, 36.1])
    expect([west, east]).toEqual([-118.2437, -96.797])
    rerender(
      <MapView routes={[makeRoute(1)]} selectedId="route-1" recommendedId="route-1" colorBy="wind" origin={null} destination={null} focus={null} fitKey="trip-1" loading={false} onSelectRoute={noop} onCheckpointClick={noop} />,
    )
    expect(fitBounds).toHaveBeenCalledTimes(1)
  })
})

describe('MapView risk colouring', () => {
  const route = makeRoute(1, {
    checkpoints: [
      makeCheckpoint(0, { risk: { combined: 'severe', wind: 'low', rain: 'severe', snow: 'moderate', load_override: null, reasons: [] } }),
      makeCheckpoint(1, { risk: { combined: 'high', wind: 'high', rain: 'low', snow: 'low', load_override: null, reasons: [] } }),
      makeCheckpoint(2, { risk: { combined: null, wind: null, rain: null, snow: null, load_override: null, reasons: [] }, weather_status: 'unavailable' }),
    ],
  })
  const fills = (mode: ColorBy) => markers(renderMap({ routes: [route], colorBy: mode }).container).map((m) => m.dataset.fill).slice(0, 3)

  it.each([
    ['combined', ['severe', 'high', null]],
    ['wind', ['low', 'high', null]],
    ['rain', ['severe', 'low', null]],
    ['snow', ['moderate', 'low', null]],
  ] as const)('colours checkpoints by %s risk, and unknown data as unknown', (mode, expected) => {
    expect(fills(mode)).toEqual(expected.map((level) => riskMeta(level).color))
  })

  it('draws a dashed segment for stretches with no weather data, never a risk colour', () => {
    const { container } = renderMap({ routes: [route], colorBy: 'combined' })
    const unknownColor = riskMeta(null).color
    const dashedUnknown = polylines(container).filter((p) => p.dataset.color === unknownColor && p.dataset.dash !== '')
    expect(dashedUnknown.length).toBe(1)
  })

  it('marks the recommended route distinctly from the alternatives', () => {
    const { container } = renderMap({ selectedId: null })
    const colors = polylines(container).map((p) => p.dataset.color)
    expect(new Set(colors).size).toBe(2) // recommended colour + alternative colour
  })
})

describe('MapView popups', () => {
  it('shows ETA, each measurement with its risk, the load rule and any missing-data reason', () => {
    const route = makeRoute(1, {
      checkpoints: [
        makeCheckpoint(0, {
          weather_status: 'partial',
          weather_missing_reason: 'provider has no snow data for the hour of arrival',
          weather: { wind_speed_mph: 41.5, wind_gust_mph: 52, rain_in_per_hr: 0.31, snow_in_per_hr: null, wind_used_mph: 41.5 },
          risk: { combined: 'severe', wind: 'high', rain: 'high', snow: null, load_override: 'severe', reasons: [] },
        }),
      ],
    })
    const { getByTestId } = renderMap({ routes: [route] })
    const popup = getByTestId('popup')
    expect(popup).toHaveTextContent('Route 1 · mile 0')
    expect(popup).toHaveTextContent(/ETA/)
    expect(popup).toHaveTextContent('41.5')
    expect(popup).toHaveTextContent('0.31')
    expect(popup).toHaveTextContent('Load rule')
    expect(popup).toHaveTextContent('Missing data: provider has no snow data for the hour of arrival')
    expect(popup.textContent).not.toMatch(/Snow\s*0(\.0+)?\s*in\/hr/) // missing snow is not shown as zero
  })
})

describe('MapView with partially missing weather', () => {
  const unknown = riskMeta(null).color
  const cp = (index: number, over: Parameters<typeof makeCheckpoint>[1]) => ({ ...makeCheckpoint(index, over), distance_miles: index * 50 })
  const partialRoute = (missing: 'wind' | 'rain' | 'snow') =>
    makeRoute(1, {
      distance_miles: 100,
      checkpoints: [
        cp(0, {}),
        cp(1, {
          weather_status: 'partial',
          weather_missing_reason: `provider has no ${missing} data for the hour of arrival`,
          weather: {
            wind_speed_mph: missing === 'wind' ? null : 12,
            wind_gust_mph: 15,
            rain_in_per_hr: missing === 'rain' ? null : 0,
            snow_in_per_hr: missing === 'snow' ? null : 0,
            wind_used_mph: missing === 'wind' ? null : 12,
          },
          risk: { combined: 'low', wind: missing === 'wind' ? null : 'low', rain: missing === 'rain' ? null : 'low', snow: missing === 'snow' ? null : 'low', load_override: null, reasons: [] },
        }),
        cp(2, {}),
      ],
    })

  it.each(['wind', 'rain', 'snow'] as const)('does not paint a checkpoint with missing %s as a known Low', (missing) => {
    const { container } = renderMap({ routes: [partialRoute(missing)], colorBy: 'combined' })
    const fills = markers(container).map((m) => m.dataset.fill).slice(0, 3)
    expect(fills).toEqual([riskMeta('low').color, unknown, riskMeta('low').color])
    const dashedUnknown = polylines(container).filter((p) => p.dataset.color === unknown && p.dataset.dash !== '')
    expect(dashedUnknown).toHaveLength(1) // the stretch the partial checkpoint stands for
  })

  it.each(['wind', 'rain', 'snow'] as const)('popup keeps measured values, names the missing %s, and says the level is unconfirmed', (missing) => {
    const { getAllByTestId } = renderMap({ routes: [partialRoute(missing)] })
    const popup = getAllByTestId('popup')[1]
    expect(popup).toHaveTextContent(`Not fully known: ${missing} missing`)
    expect(popup).toHaveTextContent(/Combined:\s*\S*\s*Unknown/)
    expect(popup).toHaveTextContent('Measured values alone read Low, which is not confirmed')
    expect(popup).toHaveTextContent(`Missing data: provider has no ${missing} data`)
    expect(popup).toHaveTextContent('No data') // the missing field is labelled, not zero
    if (missing !== 'wind') expect(popup).toHaveTextContent('12.0') // the measured wind stays visible
    if (missing !== 'rain') expect(popup).toHaveTextContent(/Rain\s*0\.00/) // an observed zero is rendered as zero
  })

  it('a complete checkpoint with observed zeros is a known Low, with no uncertainty text', () => {
    const route = makeRoute(1, { checkpoints: [makeCheckpoint(0, { weather: { wind_speed_mph: 0, wind_gust_mph: 0, rain_in_per_hr: 0, snow_in_per_hr: 0, wind_used_mph: 0 } })] })
    const { container, getByTestId } = renderMap({ routes: [route] })
    expect(markers(container)[0].dataset.fill).toBe(riskMeta('low').color)
    expect(getByTestId('popup')).not.toHaveTextContent('Not fully known')
    expect(getByTestId('popup')).toHaveTextContent(/Combined:\s*\S*\s*Low/)
  })

  it('shows a partial checkpoint that is already No Travel as No Travel, flagged as incomplete', () => {
    const route = makeRoute(1, {
      checkpoints: [
        makeCheckpoint(0, {
          weather_status: 'partial',
          weather_missing_reason: 'provider has no snow data for the hour of arrival',
          weather: { wind_speed_mph: 60, wind_gust_mph: 70, rain_in_per_hr: 0, snow_in_per_hr: null, wind_used_mph: 60 },
          risk: { combined: 'no_travel', wind: 'no_travel', rain: 'low', snow: null, load_override: null, reasons: [] },
        }),
      ],
    })
    const { container, getByTestId } = renderMap({ routes: [route] })
    expect(markers(container)[0].dataset.fill).toBe(riskMeta('no_travel').color)
    expect(getByTestId('popup')).toHaveTextContent('Not fully known: snow missing')
  })
})
