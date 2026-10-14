import { describe, expect, it } from 'vitest'
import { boundsOf, cumulativeFractions, haversineMeters, riskSegments, toLatLng } from './geo'
import { formatDuration, formatIsoWithOffset, localInputToIso, shiftIsoByHours } from './time'
import { mapServerFieldErrors, validateForm, type FormValues } from './validation'
import { makeCheckpoint, makeRoute, MISSING_CHECKPOINT } from '../test/fixtures'

const validValues: FormValues = {
  originLat: '34.0522',
  originLon: '-118.2437',
  destLat: '32.7767',
  destLon: '-96.7970',
  departureLocal: '2026-10-14T08:00',
  loadLb: '42000',
  interval: 25,
}

describe('time helpers', () => {
  it('formats ISO strings with explicit offsets, including negative and half-hour zones', () => {
    const instant = new Date('2026-10-14T15:00:00Z')
    expect(formatIsoWithOffset(instant, -420)).toBe('2026-10-14T08:00:00-07:00')
    expect(formatIsoWithOffset(instant, 0)).toBe('2026-10-14T15:00:00+00:00')
    expect(formatIsoWithOffset(instant, 330)).toBe('2026-10-14T20:30:00+05:30')
    expect(formatIsoWithOffset(instant, -570)).toBe('2026-10-14T05:30:00-09:30')
  })

  it('turns a datetime-local value into ISO 8601 with the browser offset', () => {
    const iso = localInputToIso('2026-10-14T08:00')
    expect(iso).toMatch(/^2026-10-14T08:00:00[+-]\d{2}:\d{2}$/)
    expect(Number.isNaN(new Date(iso!).getTime())).toBe(false)
  })

  it('rejects malformed or non-existent local times', () => {
    expect(localInputToIso('')).toBeNull()
    expect(localInputToIso('tomorrow')).toBeNull()
    expect(localInputToIso('2026-10-14')).toBeNull()
    expect(localInputToIso('2026-02-30T08:00')).toBeNull()
    expect(localInputToIso('2026-13-01T08:00')).toBeNull()
  })

  it('shifts a departure by whole hours without changing the instant arithmetic', () => {
    const base = '2026-10-14T08:00:00-07:00'
    const shifted = shiftIsoByHours(base, 24)
    expect(new Date(shifted).getTime() - new Date(base).getTime()).toBe(24 * 3_600_000)
    expect(shifted).toMatch(/[+-]\d{2}:\d{2}$/)
  })

  it('formats durations', () => {
    expect(formatDuration(119_340)).toBe('33 h 9 min')
    expect(formatDuration(1_800)).toBe('30 min')
  })
})

describe('validateForm and request construction', () => {
  it('builds exactly the request body the backend expects', () => {
    const result = validateForm(validValues)
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(Object.keys(result.request).sort()).toEqual(
      ['checkpoint_interval_miles', 'departure_datetime', 'destination', 'load_lb', 'origin'],
    )
    expect(result.request.origin).toEqual({ latitude: 34.0522, longitude: -118.2437 })
    expect(result.request.destination).toEqual({ latitude: 32.7767, longitude: -96.797 })
    expect(result.request.load_lb).toBe(42000)
    expect(result.request.checkpoint_interval_miles).toBe(25)
    expect(result.request.departure_datetime).toMatch(/^2026-10-14T08:00:00[+-]\d{2}:\d{2}$/)
  })

  it('accepts the three supported intervals only', () => {
    for (const interval of [10, 25, 50] as const) expect(validateForm({ ...validValues, interval }).ok).toBe(true)
    const bad = validateForm({ ...validValues, interval: 30 as unknown as 25 })
    expect(bad.ok).toBe(false)
  })

  it('reports field errors for bad coordinates, load and departure', () => {
    const result = validateForm({
      ...validValues,
      originLat: '91',
      originLon: 'abc',
      destLat: '',
      loadLb: '0',
      departureLocal: '',
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.errors.originLat).toMatch(/-90 and 90/)
    expect(result.errors.originLon).toMatch(/number/)
    expect(result.errors.destLat).toMatch(/number/)
    expect(result.errors.loadLb).toMatch(/greater than 0/)
    expect(result.errors.departureLocal).toBeDefined()
  })

  it('rejects load above the backend limit, longitude out of range and identical points', () => {
    expect(validateForm({ ...validValues, loadLb: '150001' }).ok).toBe(false)
    expect(validateForm({ ...validValues, loadLb: '150000' }).ok).toBe(true)
    const lon = validateForm({ ...validValues, destLon: '181' })
    expect(!lon.ok && lon.errors.destLon).toMatch(/-180 and 180/)
    const same = validateForm({ ...validValues, destLat: validValues.originLat, destLon: validValues.originLon })
    expect(!same.ok && same.errors.destLat).toMatch(/100 m/)
  })

  it('does not accept NaN-like or infinite numbers', () => {
    expect(validateForm({ ...validValues, loadLb: 'NaN' }).ok).toBe(false)
    expect(validateForm({ ...validValues, loadLb: 'Infinity' }).ok).toBe(false)
  })

  it('maps backend dotted field errors back onto form fields', () => {
    const { errors, unmapped } = mapServerFieldErrors({
      'origin.latitude': ['Latitude must be between -90 and 90.'],
      load_lb: ['Load must be greater than 0.'],
      departure_datetime: ['Include a UTC offset.'],
      destination: ['Destination must be at least 100 m from the origin.'],
      body: ['Invalid data.'],
    })
    expect(errors.originLat).toMatch(/-90/)
    expect(errors.loadLb).toMatch(/greater than 0/)
    expect(errors.departureLocal).toMatch(/offset/)
    expect(errors.destLat).toMatch(/100 m/)
    expect(unmapped).toEqual(['body: Invalid data.'])
  })
})

describe('geometry helpers', () => {
  it('converts GeoJSON [lon, lat] to Leaflet [lat, lon]', () => {
    expect(toLatLng([[-118.2437, 34.0522]])).toEqual([[34.0522, -118.2437]])
  })

  it('measures great-circle distance', () => {
    expect(haversineMeters([34.0522, -118.2437], [32.7767, -96.797]) / 1000).toBeCloseTo(1990, -1)
  })

  it('computes cumulative fractions from 0 to 1', () => {
    const f = cumulativeFractions([[0, 0], [0, 1], [0, 3]])
    expect(f[0]).toBe(0)
    expect(f[1]).toBeCloseTo(1 / 3, 2)
    expect(f[2]).toBe(1)
  })

  it('bounds paths', () => {
    expect(boundsOf([[[1, 2], [3, -4]], [[0, 5]]])).toEqual([[0, -4], [3, 5]])
    expect(boundsOf([])).toBeNull()
  })

  describe('riskSegments', () => {
    const route = makeRoute(1, {
      distance_miles: 100,
      geometry: { type: 'LineString', coordinates: [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]] },
      checkpoints: [
        makeCheckpoint(0, { distance_miles: 0, risk: { combined: 'low', wind: 'low', rain: 'low', snow: 'low', load_override: null, reasons: [] } }),
        makeCheckpoint(1, { distance_miles: 50, risk: { combined: 'severe', wind: 'high', rain: 'low', snow: 'low', load_override: null, reasons: [] } }),
        MISSING_CHECKPOINT(2),
      ].map((c, i) => ({ ...c, distance_miles: [0, 50, 100][i] })),
    })

    it('yields one contiguous segment per checkpoint covering the whole route', () => {
      const segments = riskSegments(route, 'combined')
      expect(segments).toHaveLength(3)
      expect(segments[0].positions[0]).toEqual([0, 0])
      expect(segments[2].positions[segments[2].positions.length - 1]).toEqual([0, 4])
      for (let i = 1; i < segments.length; i++) {
        expect(segments[i].positions[0]).toEqual(segments[i - 1].positions[segments[i - 1].positions.length - 1])
      }
      expect(segments.every((s) => s.positions.length >= 2)).toBe(true)
    })

    it('splits at the halfway points between checkpoints (the backend segment convention)', () => {
      const segments = riskSegments(route, 'combined')
      // Checkpoints at mile 0, 50, 100 -> boundaries at 25 and 75 -> longitudes 1 and 3.
      expect(segments[0].positions[segments[0].positions.length - 1][1]).toBeCloseTo(1, 1)
      expect(segments[1].positions[segments[1].positions.length - 1][1]).toBeCloseTo(3, 1)
    })

    it('uses the selected hazard for colour and null for missing data', () => {
      expect(riskSegments(route, 'combined').map((s) => s.level)).toEqual(['low', 'severe', null])
      expect(riskSegments(route, 'wind').map((s) => s.level)).toEqual(['low', 'high', null])
    })
  })
})

describe('formatting stays honest about missing data', () => {
  it('has no placeholder zeros in the missing-data fixture', () => {
    const c = MISSING_CHECKPOINT(0)
    expect(Object.values(c.weather).every((v) => v === null)).toBe(true)
  })
})
