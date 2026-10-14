import { describe, expect, it } from 'vitest'
import type { Checkpoint, RiskKey } from '../api/types'
import { makeCheckpoint, makeRoute } from '../test/fixtures'
import { confidentLevel, isLowerBound, missingMeasurements } from './checkpoints'
import { riskSegments } from './geo'

type Missing = 'wind' | 'rain' | 'snow'

/** A checkpoint like the backend sends it when one measurement is absent: known hazards keep their level. */
function partial(missing: Missing, combined: RiskKey | null = 'low', over: Partial<Checkpoint> = {}): Checkpoint {
  return makeCheckpoint(0, {
    weather_status: 'partial',
    weather_missing_reason: `provider has no ${missing} data for the hour of arrival`,
    weather: {
      wind_speed_mph: missing === 'wind' ? null : 8,
      wind_gust_mph: missing === 'wind' ? null : 12,
      rain_in_per_hr: missing === 'rain' ? null : 0,
      snow_in_per_hr: missing === 'snow' ? null : 0,
      wind_used_mph: missing === 'wind' ? null : 8,
    },
    risk: {
      combined,
      wind: missing === 'wind' ? null : 'low',
      rain: missing === 'rain' ? null : 'low',
      snow: missing === 'snow' ? null : 'low',
      load_override: null,
      reasons: [],
    },
    ...over,
  })
}

describe('missingMeasurements', () => {
  it.each(['wind', 'rain', 'snow'] as const)('names a missing %s measurement and nothing else', (m) => {
    expect(missingMeasurements(partial(m))).toEqual([m])
  })

  it('treats observed zeros as present, not missing', () => {
    const c = makeCheckpoint(0, { weather: { wind_speed_mph: 0, wind_gust_mph: 0, rain_in_per_hr: 0, snow_in_per_hr: 0, wind_used_mph: 0 } })
    expect(missingMeasurements(c)).toEqual([])
    expect(confidentLevel(c)).toBe('low') // a genuine 0 is a known Low
  })

  it('lists several gaps together', () => {
    const c = partial('rain', 'low', { weather: { wind_speed_mph: null, wind_gust_mph: null, rain_in_per_hr: null, snow_in_per_hr: 0, wind_used_mph: null } })
    expect(missingMeasurements(c)).toEqual(['wind', 'rain'])
  })
})

describe('confidentLevel: a combined level with something missing is only a lower bound', () => {
  it.each(['wind', 'rain', 'snow'] as const)('does not present Low as known when %s is missing', (m) => {
    expect(confidentLevel(partial(m, 'low'))).toBeNull()
    expect(isLowerBound(partial(m, 'low'))).toBe(true)
  })

  it('does the same for Moderate and High', () => {
    expect(confidentLevel(partial('snow', 'moderate'))).toBeNull()
    expect(confidentLevel(partial('snow', 'high'))).toBeNull()
  })

  it('keeps Severe and No Travel visible, since missing data cannot make them safer', () => {
    expect(confidentLevel(partial('rain', 'severe'))).toBe('severe')
    expect(confidentLevel(partial('rain', 'no_travel'))).toBe('no_travel')
  })

  it('leaves complete checkpoints and single-hazard modes exact', () => {
    expect(confidentLevel(makeCheckpoint(0))).toBe('low')
    const c = partial('wind', 'low')
    expect(confidentLevel(c, 'rain')).toBe('low') // rain itself was measured
    expect(confidentLevel(c, 'snow')).toBe('low')
    expect(confidentLevel(c, 'wind')).toBeNull() // wind itself was not
  })

  it('an unavailable checkpoint stays unknown', () => {
    const none = { combined: null, wind: null, rain: null, snow: null, load_override: null, reasons: [] }
    expect(confidentLevel(makeCheckpoint(0, { weather_status: 'unavailable', risk: none }))).toBeNull()
  })
})

describe('riskSegments with partial data', () => {
  const route = makeRoute(1, {
    distance_miles: 100,
    geometry: { type: 'LineString', coordinates: [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]] },
    checkpoints: [
      { ...makeCheckpoint(0), distance_miles: 0 },
      { ...partial('wind', 'low'), index: 1, distance_miles: 50 },
      { ...partial('snow', 'severe'), index: 2, distance_miles: 100 },
    ],
  })

  it('draws the partial stretch as unknown (null) in combined mode, and a fully measured one normally', () => {
    expect(riskSegments(route, 'combined').map((s) => s.level)).toEqual(['low', null, 'severe'])
  })

  it('still colours by a hazard that was measured at the partial checkpoint', () => {
    expect(riskSegments(route, 'rain').map((s) => s.level)).toEqual(['low', 'low', 'low'])
    expect(riskSegments(route, 'wind').map((s) => s.level)).toEqual(['low', null, 'low'])
  })
})
