import type { FormValues } from './validation'

export interface TripPreset {
  id: string
  name: string
  originName: string
  destName: string
  values: Pick<FormValues, 'originLat' | 'originLon' | 'destLat' | 'destLon'>
}

// City-centre coordinates for convenience only; the assessment itself is always computed live.
export const PRESETS: TripPreset[] = [
  {
    id: 'la-dallas',
    name: 'Los Angeles → Dallas',
    originName: 'Los Angeles',
    destName: 'Dallas',
    values: { originLat: '34.0522', originLon: '-118.2437', destLat: '32.7767', destLon: '-96.7970' },
  },
  {
    id: 'chicago-atlanta',
    name: 'Chicago → Atlanta',
    originName: 'Chicago',
    destName: 'Atlanta',
    values: { originLat: '41.8781', originLon: '-87.6298', destLat: '33.7490', destLon: '-84.3880' },
  },
  {
    id: 'denver-kc',
    name: 'Denver → Kansas City',
    originName: 'Denver',
    destName: 'Kansas City',
    values: { originLat: '39.7392', originLon: '-104.9903', destLat: '39.0997', destLon: '-94.5786' },
  },
]

const same = (a: string, b: string) => {
  const x = Number(a)
  const y = Number(b)
  return a.trim() !== '' && b.trim() !== '' && Number.isFinite(x) && Number.isFinite(y) && Math.abs(x - y) < 1e-6
}

type Coords = Pick<FormValues, 'originLat' | 'originLon' | 'destLat' | 'destLon'>

/** The preset whose four coordinates equal the current form values, if any. */
export function presetFor(v: Coords): TripPreset | undefined {
  return PRESETS.find(
    (p) =>
      same(p.values.originLat, v.originLat) &&
      same(p.values.originLon, v.originLon) &&
      same(p.values.destLat, v.destLat) &&
      same(p.values.destLon, v.destLon),
  )
}

/** A friendly place name for a coordinate pair that matches a preset endpoint. */
export function placeName(lat: string, lon: string): string | undefined {
  for (const p of PRESETS) {
    if (same(p.values.originLat, lat) && same(p.values.originLon, lon)) return p.originName
    if (same(p.values.destLat, lat) && same(p.values.destLon, lon)) return p.destName
  }
  return undefined
}
