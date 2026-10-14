import { CHECKPOINT_INTERVALS, type AssessRequest, type CheckpointInterval } from '../api/types'
import { haversineMeters } from './geo'
import { localInputToIso } from './time'

export const MAX_LOAD_LB = 150_000
export const MIN_TRIP_SEPARATION_M = 100

export interface FormValues {
  originLat: string
  originLon: string
  destLat: string
  destLon: string
  departureLocal: string
  loadLb: string
  interval: CheckpointInterval
}

export type FormField = keyof FormValues
export type FormErrors = Partial<Record<FormField, string>>

export type ValidationResult = { ok: true; request: AssessRequest } | { ok: false; errors: FormErrors }

function parseNumber(text: string): number | null {
  const trimmed = text.trim()
  if (trimmed === '') return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : null
}

function checkCoordinate(
  latText: string,
  lonText: string,
  latField: FormField,
  lonField: FormField,
  errors: FormErrors,
): [number, number] | null {
  const lat = parseNumber(latText)
  const lon = parseNumber(lonText)
  if (lat === null) errors[latField] = 'Enter a latitude as a number, e.g. 34.0522.'
  else if (lat < -90 || lat > 90) errors[latField] = 'Latitude must be between -90 and 90.'
  if (lon === null) errors[lonField] = 'Enter a longitude as a number, e.g. -118.2437.'
  else if (lon < -180 || lon > 180) errors[lonField] = 'Longitude must be between -180 and 180.'
  return lat !== null && lon !== null && !errors[latField] && !errors[lonField] ? [lat, lon] : null
}

export function validateForm(values: FormValues): ValidationResult {
  const errors: FormErrors = {}
  const origin = checkCoordinate(values.originLat, values.originLon, 'originLat', 'originLon', errors)
  const destination = checkCoordinate(values.destLat, values.destLon, 'destLat', 'destLon', errors)
  if (origin && destination && haversineMeters(origin, destination) < MIN_TRIP_SEPARATION_M) {
    errors.destLat = 'Destination must be at least 100 m from the origin.'
  }

  const departure = localInputToIso(values.departureLocal)
  if (departure === null) errors.departureLocal = 'Choose a valid departure date and time.'

  const load = parseNumber(values.loadLb)
  if (load === null) errors.loadLb = 'Enter the load weight in pounds.'
  else if (load <= 0) errors.loadLb = 'Load must be greater than 0 lb.'
  else if (load > MAX_LOAD_LB) errors.loadLb = `Load must not exceed ${MAX_LOAD_LB.toLocaleString('en-US')} lb.`

  if (!CHECKPOINT_INTERVALS.includes(values.interval)) errors.interval = 'Choose 10, 25 or 50 miles.'

  if (Object.keys(errors).length > 0 || !origin || !destination || departure === null || load === null) {
    return { ok: false, errors }
  }
  return {
    ok: true,
    request: {
      origin: { latitude: origin[0], longitude: origin[1] },
      destination: { latitude: destination[0], longitude: destination[1] },
      departure_datetime: departure,
      load_lb: load,
      checkpoint_interval_miles: values.interval,
    },
  }
}

const SERVER_FIELD_MAP: Record<string, FormField> = {
  'origin.latitude': 'originLat',
  'origin.longitude': 'originLon',
  'destination.latitude': 'destLat',
  'destination.longitude': 'destLon',
  destination: 'destLat',
  origin: 'originLat',
  departure_datetime: 'departureLocal',
  load_lb: 'loadLb',
  checkpoint_interval_miles: 'interval',
}

export function mapServerFieldErrors(fields: Record<string, string[]>): {
  errors: FormErrors
  unmapped: string[]
} {
  const errors: FormErrors = {}
  const unmapped: string[] = []
  for (const [key, messages] of Object.entries(fields)) {
    const target = SERVER_FIELD_MAP[key]
    if (target) errors[target] = messages.join(' ')
    else unmapped.push(`${key}: ${messages.join(' ')}`)
  }
  return { errors, unmapped }
}
