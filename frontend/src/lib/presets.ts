import type { FormValues } from './validation'

export interface TripPreset {
  name: string
  values: Pick<FormValues, 'originLat' | 'originLon' | 'destLat' | 'destLon'>
}

export const PRESETS: TripPreset[] = [
  { name: 'Los Angeles → Dallas', values: { originLat: '34.0522', originLon: '-118.2437', destLat: '32.7767', destLon: '-96.7970' } },
  { name: 'Chicago → Atlanta', values: { originLat: '41.8781', originLon: '-87.6298', destLat: '33.7490', destLon: '-84.3880' } },
  { name: 'Denver → Kansas City', values: { originLat: '39.7392', originLon: '-104.9903', destLat: '39.0997', destLon: '-94.5786' } },
]
